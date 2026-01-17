import json
import csv
import datetime
import http.client
import time
import hashlib
import logging
import os
import sys
import codecs

CONFIG_PATH = 'config.json'
CUSTOMERS_PATH = 'data/input/customers.csv'
ORDERS_PATH = 'data/input/orders.csv'
PROCESSED_PATH = 'data/output/processed.csv'
SUMMARY_PATH = 'data/output/summary.txt'
IDEMPOTENCY_PATH = 'data/output/idempotency.json'
CHECKSUMS_PATH = 'data/output/checksums.txt'
LOG_PATH = 'logs/run.log'

def setup_logging():
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format='%(asctime)sZ %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    logging.Formatter.converter = time.gmtime

def log(message):
    print(message)
    logging.info(message)

class AutomationBot:
    def __init__(self):
        self.config = self.load_config()
        self.customers = self.load_customers()
        self.idempotency_registry = self.load_idempotency_registry()
        self.processed_records = []
        self.stats = {
            "total_read": 0,
            "success": 0,
            "business_error": 0,
            "system_error": 0,
            "skipped": 0,
            "reasons": {},
            "currency_totals": {}
        }
        self.seen_in_run = set()

    def load_config(self):
        required_keys = {
            "api_host": str,
            "api_port": int,
            "retry_attempts": int,
            "retry_backoff_ms": int,
            "allowed_currencies": list,
            "business_date_window_days": int,
            "report_decimal_places": int
        }
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
            
            for key, expected_type in required_keys.items():
                if key not in config:
                    raise ValueError(f"Missing config key: {key}")
                if not isinstance(config[key], expected_type):
                    raise TypeError(f"Incorrect type for {key}: expected {expected_type}")
            return config
        except Exception as e:
            print(f"Config Error: {e}")
            sys.exit(1)

    def load_customers(self):
        customers = {}
        try:
            with open(CUSTOMERS_PATH, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    customers[row['CustomerID']] = row
            return customers
        except Exception as e:
            log(f"SYSTEM_ERR:Failed to load customers: {e}")
            sys.exit(1)

    def load_idempotency_registry(self):
        if os.path.exists(IDEMPOTENCY_PATH):
            try:
                with open(IDEMPOTENCY_PATH, 'r') as f:
                    data = json.load(f)
                    return {f"{item['order_id']}_{item['business_date']}" for item in data.get('processed', [])}
            except Exception as e:
                log(f"SYSTEM_ERR:Failed to load idempotency registry: {e}")
                sys.exit(1)
        return set()

    def save_idempotency_registry(self):
        processed_list = []
        for item in self.idempotency_registry:
            oid, bdate = item.split('_')
            processed_list.append({"order_id": oid, "business_date": bdate})
        
        with open(IDEMPOTENCY_PATH, 'w') as f:
            json.dump({"processed": processed_list}, f, indent=2)

    def validate_order(self, row):
        key = f"{row['OrderID']}_{row['BusinessDate']}"
        if key in self.seen_in_run:
            return False, "duplicate_in_run"
        self.seen_in_run.add(key)

        if key in self.idempotency_registry:
            return False, "SKIP:already_processed"

        try:
            amount = float(row['Amount'])
            if amount <= 0:
                return False, "amount_invalid"
        except ValueError:
            return False, "amount_format_invalid"

        if row['Currency'] not in self.config['allowed_currencies']:
            return False, "currency_invalid"

        email = row['Email']
        if '@' not in email or '.' not in email.split('@')[-1]:
            return False, "email_invalid"

        cust = self.customers.get(row['CustomerID'])
        if not cust or cust['Status'] != 'Active':
            return False, "customer_inactive"

        try:
            b_date = datetime.datetime.strptime(row['BusinessDate'], '%Y-%m-%d').date()
            today = datetime.datetime.utcnow().date()
            delta = abs((b_date - today).days)
            if delta > self.config['business_date_window_days']:
                return False, "date_window_exceeded"
        except ValueError:
            return False, "date_format_invalid"

        return True, "valid"

    def call_api(self, order_data):
        host = self.config['api_host']
        port = self.config['api_port']
        retries = self.config['retry_attempts']
        backoff = self.config['retry_backoff_ms'] / 1000.0

        for attempt in range(1, retries + 2):
            try:
                conn = http.client.HTTPConnection(host, port, timeout=5)
                headers = {'Content-type': 'application/json'}
                json_data = json.dumps(order_data)
                conn.request('POST', '/api/orders', json_data, headers)
                response = conn.getresponse()
                data = response.read().decode()
                conn.close()

                if response.status in (200, 201):
                    return True, "success"
                elif response.status == 422:
                    return False, "api_validation_error"
                else:
                    if response.status >= 500:
                        raise Exception(f"Server Error {response.status}")
                    return False, f"api_error_{response.status}"

            except (Exception, ConnectionRefusedError, socket.timeout) as e:
                if attempt <= retries:
                    log(f"RETRY:{attempt}/{retries}:sleep={backoff}")
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    return False, f"system_error: {str(e)}"
        return False, "system_error_exhausted"

    def process(self):
        log(f"START {json.dumps(self.config)}")
        
        try:
            with open(ORDERS_PATH, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, skipinitialspace=True)
                for row in reader:
                    self.stats['total_read'] += 1
                    
                    row = {k: v.strip() if v else v for k, v in row.items()}
                    
                    is_valid, reason = self.validate_order(row)
                    
                    if reason == "SKIP:already_processed":
                        self.stats['skipped'] += 1
                        log(f"SKIP:already_processed OrderID={row['OrderID']}")
                        self.processed_records.append({
                            "OrderID": row['OrderID'],
                            "BusinessDate": row['BusinessDate'],
                            "Status": "skipped",
                            "Message": "Already processed",
                            "TimestampUTC": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                        })
                        continue

                    if not is_valid:
                        self.stats['business_error'] += 1
                        self.stats['reasons'][reason] = self.stats['reasons'].get(reason, 0) + 1
                        log(f"BUSINESS_ERR:{reason} OrderID={row['OrderID']}")
                        self.processed_records.append({
                            "OrderID": row['OrderID'],
                            "BusinessDate": row['BusinessDate'],
                            "Status": "business_error",
                            "Message": reason,
                            "TimestampUTC": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                        })
                        continue

                    success, api_reason = self.call_api(row)
                    
                    if success:
                        self.stats['success'] += 1
                        log(f"SUCCESS OrderID={row['OrderID']}")
                        
                        key = f"{row['OrderID']}_{row['BusinessDate']}"
                        self.idempotency_registry.add(key)
                        self.save_idempotency_registry()

                        curr = row['Currency']
                        amt = float(row['Amount'])
                        self.stats['currency_totals'][curr] = self.stats['currency_totals'].get(curr, 0) + amt

                        self.processed_records.append({
                            "OrderID": row['OrderID'],
                            "BusinessDate": row['BusinessDate'],
                            "Status": "success",
                            "Message": "Created",
                            "TimestampUTC": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                        })
                    elif "system_error" in api_reason:
                        self.stats['system_error'] += 1
                        log(f"SYSTEM_ERR:{api_reason} OrderID={row['OrderID']}")
                        self.processed_records.append({
                            "OrderID": row['OrderID'],
                            "BusinessDate": row['BusinessDate'],
                            "Status": "system_error",
                            "Message": api_reason,
                            "TimestampUTC": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                        })
                    else:
                        self.stats['business_error'] += 1
                        self.stats['reasons'][api_reason] = self.stats['reasons'].get(api_reason, 0) + 1
                        log(f"BUSINESS_ERR:{api_reason} OrderID={row['OrderID']}")
                        self.processed_records.append({
                            "OrderID": row['OrderID'],
                            "BusinessDate": row['BusinessDate'],
                            "Status": "business_error",
                            "Message": api_reason,
                            "TimestampUTC": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
                        })

        except Exception as e:
            log(f"SYSTEM_ERR:Unexpected error during processing: {e}")
        
        self.write_outputs()
        log(f"END Success={self.stats['success']} Skipped={self.stats['skipped']} Errors={self.stats['business_error'] + self.stats['system_error']}")

    def write_outputs(self):
        self.processed_records.sort(key=lambda x: (x['BusinessDate'], x['OrderID']))
        
        with open(PROCESSED_PATH, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["OrderID", "BusinessDate", "Status", "Message", "TimestampUTC"], lineterminator='\n')
            writer.writeheader()
            writer.writerows(self.processed_records)

        with open(SUMMARY_PATH, 'w') as f:
            f.write(f"Total rows read: {self.stats['total_read']}\n")
            f.write(f"Success count: {self.stats['success']}\n")
            f.write(f"Business error count: {self.stats['business_error']}\n")
            for reason, count in self.stats['reasons'].items():
                f.write(f"  - {reason}: {count}\n")
            f.write(f"System error count: {self.stats['system_error']}\n")
            f.write(f"Skipped (idempotent) count: {self.stats['skipped']}\n")
            
            rate = (self.stats['success'] / self.stats['total_read'] * 100) if self.stats['total_read'] > 0 else 0
            f.write(f"Success rate (%): {rate:.2f}%\n")
            
            f.write("\nTotals by currency:\n")
            for curr, total in self.stats['currency_totals'].items():
                f.write(f"  {curr}: {total:.{self.config['report_decimal_places']}f}\n")
            
            f.write("\nConfig snapshot:\n")
            f.write(json.dumps(self.config, indent=2))

        with open(CHECKSUMS_PATH, 'w') as f:
            for path in [PROCESSED_PATH, SUMMARY_PATH, IDEMPOTENCY_PATH]:
                if os.path.exists(path):
                    with open(path, 'rb') as file_to_hash:
                        digest = hashlib.sha256(file_to_hash.read()).hexdigest()
                        filename = os.path.basename(path)
                        f.write(f"sha256({filename})={digest}\n")

if __name__ == "__main__":
    os.makedirs('data/output', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    setup_logging()
    bot = AutomationBot()
    bot.process()
