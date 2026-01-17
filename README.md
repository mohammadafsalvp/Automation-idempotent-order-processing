# Automation Engineering – Idempotent Order Processing (Offline)

## 📌 Overview
This project implements a **robust, idempotent automation pipeline** for processing orders and customers under strict constraints:
- **Air-gapped environment**
- **Python 3 (standard library only)**
- **Offline local mock REST API**

The automation ingests CSV files, applies business validations, safely creates orders via an API, and generates **deterministic, audit-ready outputs**.  
It is designed to be **safe to re-run** without creating duplicate transactions.The solution is fully compatible with air-gapped Linux environments and relies exclusively on the Python standard library.


## 🖥️ Execution Environment & Constraints

This automation was designed and implemented under the following strict constraints:

- **Operating System:** Air-gapped RHEL 9.4
- **Language:** Python 3
- **Dependencies:** Python standard library only (no external packages)
- **Network:** No internet access (offline execution)
- **API:** Local mock REST API allowed

All functionality, including validation, retries, logging, idempotency, and reporting, was implemented without relying on third-party libraries or external services.

## 🛠️ Key Objectives
- Build a **config-driven automation**
- Enforce **idempotency** across runs
- Clean separation of **business errors vs system errors**
- Produce **deterministic outputs** for audit and verification
- Operate fully **offline** with no external dependencies

---

## ⚙️ Technology Stack
- **Python 3**
- Python Standard Library only (`csv`, `json`, `http.client`, `datetime`, `hashlib`, `logging`)
- Local mock REST API (offline)
- CSV-based input/output

---

## 📂 Project Structure
scripts/
├── app.py # Local mock REST API
└── bot.py # Automation bot

data/
├── input/
│ ├── orders.csv
│ └── customers.csv
└── output/
├── processed.csv
├── summary.txt
├── idempotency.json
├── checksums.txt
└── api_store.json

logs/
└── run.log

config.json
README_REPORT.md


---

## 📥 Inputs

### orders.csv
Columns:
- `OrderID`
- `CustomerID`
- `Amount`
- `Currency`
- `Email`
- `BusinessDate` (YYYY-MM-DD, UTC)

Notes:
- BOM, whitespace, and empty-line tolerant
- Duplicate detection within the same run

### customers.csv
Columns:
- `CustomerID`
- `CustomerName`
- `Status` (Active / Inactive)

---

## ⚙️ Configuration (config.json)
All runtime behavior is controlled via configuration.

```json
{
  "api_host": "127.0.0.1",
  "api_port": 8080,
  "retry_attempts": 3,
  "retry_backoff_ms": 1000,
  "allowed_currencies": ["USD", "EUR", "AED"],
  "business_date_window_days": 7,
  "report_decimal_places": 2
}

