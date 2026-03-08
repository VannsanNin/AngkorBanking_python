# Banking Management System (PyQt + QSS)

Desktop banking manager built with Python, PyQt5, and QSS styling.

## Project Structure

```text
.
├─ data/
│  └─ banking.db
├─ src/
│  └─ angkor_banking/
│     ├─ app.py
│     ├─ __init__.py
│     ├─ __main__.py
│     ├─ operations/
│     └─ assets/
│        ├─ styles/
│        └─ styles.qss
└─ main.py
```

## Features

1. `create_user_account()`
2. `check_user_account()`
3. `deposit_money()`
4. `widrawal_money()`
5. `trainsfer_money()`
6. `update_user_information()`
7. `delete_user_account()`

Data is stored in `data/banking.db` (legacy root `banking.db` is still recognized).

## Setup

```bash
python -m venv .venv
pip install -r requirements.txt
pip install -e .
```

Activate the virtual environment:

PowerShell:

```powershell
. .\.venv\Scripts\Activate.ps1
```

Bash:

```bash
source .venv/bin/activate
```

## Run

```bash
python main.py
```

Or run as a module:

```bash
python -m angkor_banking
```

Or use console command:

```bash
angkor-banking
```

## Notes

- New accounts use a random 10-digit account number.
- PIN must be exactly 4 digits.
- Account deletion requires the balance to be `0.00`.
