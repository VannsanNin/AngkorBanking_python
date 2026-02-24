# Banking Management System (PyQt + QSS)

Desktop banking manager built with Python, PyQt5, and QSS styling.

## Features

1. `create_user_account()`
2. `check_user_account()`
3. `deposit_money()`
4. `widrawal_money()`
5. `trainsfer_money()`
6. `update_user_information()`
7. `delete_user_account()`

Data is stored in a local SQLite database file: `banking.db`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Notes

- New accounts use a random 10-digit account number.
- PIN must be exactly 4 digits.
- Account deletion requires the balance to be `0.00`.
