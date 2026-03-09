# Angkor Banking Project - Step-by-Step Explanation Guide

This file is for explaining the project to students in class.

## 1. Learning Goal

By the end of this lesson, students should understand:

1. How a Python desktop app is structured (`main.py` -> `src/angkor_banking/app.py`).
2. How SQLite is used for storing accounts.
3. How business logic is separated into operation files.
4. How input validation and security checks (PIN + lock) work.
5. How each banking feature changes data in the database.

## 2. Quick Setup (for demo)

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python main.py
```

Tell students:
- The GUI opens with Dashboard and menu actions.
- Data is saved in `data/banking.db` (or old `banking.db` if it already exists).

## 3. Explain the Architecture First

Use this order:

1. `main.py`
- Adds `src` into `sys.path`.
- Imports `main` from `angkor_banking.app`.
- Starts the app.

2. `src/angkor_banking/app.py`
- Contains `BankingSystem` (database + core methods).
- Contains `BankingApp` (PyQt UI).
- Connects button clicks to handlers (`_handle_create_account`, `_handle_transfer`, etc.).

3. `src/angkor_banking/operations/*.py`
- Each file has one business operation:
  `create_account.py`, `check_account.py`, `deposit.py`, `withdrawal.py`, `transfer.py`, `update_account.py`, `delete_account.py`.
- This separation makes code easier to read and maintain.

## 4. Step-by-Step Classroom Demo Flow

Follow this exact sequence in the GUI:

1. Create Account
- Fill all required fields.
- Use valid dates and 4-digit PIN.
- Explain that account number is generated randomly (10 digits).

2. Check Account
- Enter account number + PIN.
- Show account details and ID card status (`Active`, `Expired`, `Invalid Date`, `Unknown`).

3. Deposit
- Enter account number and amount.
- Explain validation: amount must be numeric and > 0.

4. Withdraw
- Enter account number, PIN, amount.
- Explain PIN verification and insufficient balance check.

5. Transfer
- Enter source account + PIN + destination account + amount.
- Explain transaction behavior:
  source decrease + destination increase in one safe DB transaction.

6. Update Account
- First preview account with account/ID + PIN.
- Then update selected fields.
- Explain duplicate checks (phone, email, ID card number) and date consistency checks.

7. Delete Account
- Enter account number + PIN + confirm checkbox.
- Explain rule: account can be deleted only when balance is `0.00`.

## 5. Important Validation Rules to Explain

Students should remember these rules:

1. Account number must be 10 digits (spaces/hyphens are normalized).
2. PIN must be exactly 4 digits.
3. After 3 wrong PIN attempts, account is locked for 5 minutes.
4. Amount for deposit/withdraw/transfer must be > 0.
5. ID card expiry date must be after issue date.
6. Phone, email, and ID card number must be unique per account.
7. Delete requires zero balance.

## 6. Database Concepts to Highlight

In table `accounts`, key fields include:

- `account_number` (unique)
- `pin_hash` (hashed, not plain PIN)
- `balance`
- `failed_pin_attempts`
- `pin_locked_until`
- user profile fields (name, phone, email, address, ID card, career, status)

Teaching point:
- Security is improved by storing `pin_hash` using SHA-256.
- Lockout logic protects against PIN guessing.

## 7. Code Walkthrough Map (fast reference)

Use this when students ask "where is this logic?":

1. Create account logic -> `src/angkor_banking/operations/create_account.py`
2. Check account logic -> `src/angkor_banking/operations/check_account.py`
3. Deposit logic -> `src/angkor_banking/operations/deposit.py`
4. Withdraw logic -> `src/angkor_banking/operations/withdrawal.py`
5. Transfer logic -> `src/angkor_banking/operations/transfer.py`
6. Update logic -> `src/angkor_banking/operations/update_account.py`
7. Delete logic -> `src/angkor_banking/operations/delete_account.py`
8. UI button handlers -> `src/angkor_banking/app.py`

## 8. Suggested 45-Minute Teaching Plan

1. 0-5 min: Project purpose and run app.
2. 5-15 min: Architecture (`main.py`, `app.py`, `operations`).
3. 15-30 min: Live demo (create -> check -> deposit -> withdraw -> transfer).
4. 30-40 min: Update + delete with validation/error scenarios.
5. 40-45 min: Q&A + small student exercise.

## 9. Student Practice Tasks

Give students these tasks:

1. Trigger and explain one validation error in each menu.
2. Add one new rule (example: minimum opening balance).
3. Add a transaction history table and record deposit/withdraw/transfer.
4. Add a search by full name in dashboard.
