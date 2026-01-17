# Automation Task #2 - Project Report

## Overview
Hi there! This is the documentation for the automation bot I built. The goal was to create a reliable system that reads orders, checks if they are valid, and sends them to a local API. It's designed to be safe to run multiple times (idempotent) and handles errors gracefully.

## How It Works

### The Parts
1.  **The API (`scripts/app.py`)**: Think of this as the "server". It listens for new orders and saves them. It remembers what it has seen so it doesn't create duplicates.
2.  **The Bot (`scripts/bot.py`)**: This is the "worker". It reads your CSV files, makes sure the data looks good, and then talks to the API to place the orders.

### Key Features
-   **Smart Skipping**: If you run the bot twice, it won't double-charge or double-process orders it already finished.
-   **Safety Checks**: It checks everything before sending:
    -   Is the amount a positive number?
    -   Is the currency allowed (USD, EUR, AED)?
    -   Is the email valid?
    -   Is the customer active?
    -   Is the date within the last week? (Must be YYYY-MM-DD)
-   **Retry Logic**: If the server blips or the network is flaky, the bot waits a bit and tries again automatically.

## How to Run It
It's super simple. Just follow these steps in your terminal:

1.  **Start the API**:
    ```bash
    python3 scripts/app.py &
    ```
    (This runs it in the background).

2.  **Run the Bot**:
    ```bash
    python3 scripts/bot.py
    ```

3.  **Check the Results**:
    Head over to the `data/output/` folder. You'll find:
    -   `processed.csv`: A detailed list of what happened to every order.
    -   `summary.txt`: A quick stats report (success rates, totals, etc.).

## File Structure
-   `scripts/`: Where the Python code lives.
-   `data/input/`: Drop your `orders.csv` and `customers.csv` here.
-   `data/output/`: Where the results land.
-   `logs/`: Detailed logs if you need to debug something.
-   `config.json`: Change settings here (like retry attempts or allowed currencies) without touching code.

## Notes
-   I assumed "Business Date" means we compare it to today's UTC date.
-   If an order is a duplicate *within the same file*, the bot marks it as an error.
-   If an order was *already processed* in a previous run, the bot just skips it to be safe.


