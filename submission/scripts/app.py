import http.server
import socketserver
import json
import os
import datetime
import sys

CONFIG_PATH = 'config.json'
STORE_PATH = 'data/output/api_store.json'

def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def load_store():
    if os.path.exists(STORE_PATH):
        try:
            with open(STORE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_store(store):
    with open(STORE_PATH, 'w') as f:
        json.dump(store, f, indent=2)

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/orders':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                order_data = json.loads(post_data)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return

            required_fields = ['OrderID', 'BusinessDate', 'Amount', 'Currency', 'Email', 'CustomerID']
            if not all(field in order_data for field in required_fields):
                self.send_error(400, "Missing required fields")
                return

            try:
                amount = float(order_data['Amount'])
                if amount <= 0:
                    self.send_error(422, "Amount must be greater than 0")
                    return
            except ValueError:
                self.send_error(422, "Invalid amount format")
                return

            store = load_store()
            key = f"{order_data['OrderID']}_{order_data['BusinessDate']}"

            if key in store:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "exists", "order": store[key]}).encode('utf-8'))
                return

            store[key] = order_data
            save_store(store)

            self.send_response(201)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "created", "order": order_data}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path.startswith('/api/orders/'):
            order_id = self.path.split('/')[-1]
            store = load_store()
            
            found_orders = [v for k, v in store.items() if v['OrderID'] == order_id]
            
            if found_orders:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(found_orders[-1]).encode('utf-8'))
            else:
                self.send_error(404, "Order not found")
        else:
            self.send_error(404, "Not Found")

def run():
    config = load_config()
    host = config.get('api_host', '127.0.0.1')
    port = config.get('api_port', 8080)
    
    server_address = (host, port)
    httpd = http.server.HTTPServer(server_address, RequestHandler)
    print(f"Starting mock API on {host}:{port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    print("Stopping mock API...")

if __name__ == '__main__':
    run()
