import hashlib
import os
import random
import sqlite3
import sys
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class BankingSystem:
    def __init__(self, db_path="banking.db"):
        self.db_path = db_path
        self._initialize_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_number TEXT UNIQUE NOT NULL,
                    full_name TEXT NOT NULL,
                    phone TEXT,
                    email TEXT,
                    address TEXT,
                    pin_hash TEXT NOT NULL,
                    balance REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _hash_pin(pin):
        return hashlib.sha256(pin.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_pin(pin):
        return pin.isdigit() and len(pin) == 4

    def _generate_account_number(self):
        with self._connect() as conn:
            while True:
                account_number = "".join(str(random.randint(0, 9)) for _ in range(10))
                existing = conn.execute(
                    "SELECT 1 FROM accounts WHERE account_number = ?", (account_number,)
                ).fetchone()
                if not existing:
                    return account_number

    def create_user_account(
        self, full_name, phone, email, address, pin, opening_balance=0.0
    ):
        full_name = full_name.strip()
        if not full_name:
            return {"success": False, "message": "Full name is required."}
        if not self._validate_pin(pin):
            return {"success": False, "message": "PIN must be exactly 4 digits."}
        try:
            opening_balance = float(opening_balance)
        except (TypeError, ValueError):
            return {"success": False, "message": "Opening balance must be numeric."}
        if opening_balance < 0:
            return {"success": False, "message": "Opening balance cannot be negative."}

        account_number = self._generate_account_number()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts (
                    account_number, full_name, phone, email, address, pin_hash, balance, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_number,
                    full_name,
                    phone.strip(),
                    email.strip(),
                    address.strip(),
                    self._hash_pin(pin),
                    opening_balance,
                    created_at,
                ),
            )

        return {
            "success": True,
            "message": f"Account created successfully. Account Number: {account_number}",
            "data": {"account_number": account_number},
        }

    def check_user_account(self, account_number, pin=None):
        account_number = account_number.strip()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT account_number, full_name, phone, email, address, balance, created_at, pin_hash
                FROM accounts
                WHERE account_number = ?
                """,
                (account_number,),
            ).fetchone()

        if not row:
            return {"success": False, "message": "Account not found."}
        if pin and self._hash_pin(pin) != row[7]:
            return {"success": False, "message": "Invalid PIN."}

        data = {
            "account_number": row[0],
            "full_name": row[1],
            "phone": row[2],
            "email": row[3],
            "address": row[4],
            "balance": row[5],
            "created_at": row[6],
        }
        return {"success": True, "message": "Account found.", "data": data}

    def deposit_money(self, account_number, amount):
        account_number = account_number.strip()
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"success": False, "message": "Deposit amount must be numeric."}
        if amount <= 0:
            return {"success": False, "message": "Deposit amount must be greater than zero."}

        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE accounts SET balance = balance + ? WHERE account_number = ?",
                (amount, account_number),
            )
            if cursor.rowcount == 0:
                return {"success": False, "message": "Account not found."}

            new_balance = conn.execute(
                "SELECT balance FROM accounts WHERE account_number = ?", (account_number,)
            ).fetchone()[0]

        return {
            "success": True,
            "message": f"Deposit successful. New balance: ${new_balance:,.2f}",
            "data": {"balance": new_balance},
        }

    def widrawal_money(self, account_number, pin, amount):
        account_number = account_number.strip()
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"success": False, "message": "Withdrawal amount must be numeric."}
        if amount <= 0:
            return {
                "success": False,
                "message": "Withdrawal amount must be greater than zero.",
            }

        pin_hash = self._hash_pin(pin)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT balance FROM accounts WHERE account_number = ? AND pin_hash = ?",
                (account_number, pin_hash),
            ).fetchone()
            if not row:
                return {"success": False, "message": "Invalid account number or PIN."}

            current_balance = row[0]
            if current_balance < amount:
                return {"success": False, "message": "Insufficient balance."}

            conn.execute(
                "UPDATE accounts SET balance = balance - ? WHERE account_number = ?",
                (amount, account_number),
            )
            new_balance = current_balance - amount

        return {
            "success": True,
            "message": f"Withdrawal successful. New balance: ${new_balance:,.2f}",
            "data": {"balance": new_balance},
        }

    def trainsfer_money(self, from_account, from_pin, to_account, amount):
        from_account = from_account.strip()
        to_account = to_account.strip()
        if from_account == to_account:
            return {"success": False, "message": "Source and destination accounts must differ."}
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"success": False, "message": "Transfer amount must be numeric."}
        if amount <= 0:
            return {"success": False, "message": "Transfer amount must be greater than zero."}

        pin_hash = self._hash_pin(from_pin)
        with self._connect() as conn:
            try:
                conn.execute("BEGIN")
                source = conn.execute(
                    "SELECT balance FROM accounts WHERE account_number = ? AND pin_hash = ?",
                    (from_account, pin_hash),
                ).fetchone()
                if not source:
                    conn.execute("ROLLBACK")
                    return {"success": False, "message": "Invalid source account number or PIN."}

                target = conn.execute(
                    "SELECT balance FROM accounts WHERE account_number = ?", (to_account,)
                ).fetchone()
                if not target:
                    conn.execute("ROLLBACK")
                    return {"success": False, "message": "Destination account not found."}

                if source[0] < amount:
                    conn.execute("ROLLBACK")
                    return {"success": False, "message": "Insufficient source balance."}

                conn.execute(
                    "UPDATE accounts SET balance = balance - ? WHERE account_number = ?",
                    (amount, from_account),
                )
                conn.execute(
                    "UPDATE accounts SET balance = balance + ? WHERE account_number = ?",
                    (amount, to_account),
                )
                conn.execute("COMMIT")
            except sqlite3.Error:
                conn.execute("ROLLBACK")
                return {"success": False, "message": "Transfer failed due to a database error."}

            source_balance = conn.execute(
                "SELECT balance FROM accounts WHERE account_number = ?", (from_account,)
            ).fetchone()[0]
            destination_balance = conn.execute(
                "SELECT balance FROM accounts WHERE account_number = ?", (to_account,)
            ).fetchone()[0]

        return {
            "success": True,
            "message": "Transfer successful.",
            "data": {
                "source_balance": source_balance,
                "destination_balance": destination_balance,
            },
        }

    def update_user_information(
        self, account_number, pin, full_name=None, phone=None, email=None, address=None
    ):
        account_number = account_number.strip()
        pin_hash = self._hash_pin(pin)

        updates = {}
        if full_name is not None and full_name.strip():
            updates["full_name"] = full_name.strip()
        if phone is not None and phone.strip():
            updates["phone"] = phone.strip()
        if email is not None and email.strip():
            updates["email"] = email.strip()
        if address is not None and address.strip():
            updates["address"] = address.strip()

        if not updates:
            return {"success": False, "message": "Provide at least one field to update."}

        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM accounts WHERE account_number = ? AND pin_hash = ?",
                (account_number, pin_hash),
            ).fetchone()
            if not exists:
                return {"success": False, "message": "Invalid account number or PIN."}

            set_clause = ", ".join(f"{field} = ?" for field in updates.keys())
            params = list(updates.values()) + [account_number]
            conn.execute(
                f"UPDATE accounts SET {set_clause} WHERE account_number = ?",  # nosec B608
                params,
            )

        return self.check_user_account(account_number, pin)

    def delete_user_account(self, account_number, pin):
        account_number = account_number.strip()
        pin_hash = self._hash_pin(pin)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT balance FROM accounts WHERE account_number = ? AND pin_hash = ?",
                (account_number, pin_hash),
            ).fetchone()
            if not row:
                return {"success": False, "message": "Invalid account number or PIN."}
            if row[0] != 0:
                return {
                    "success": False,
                    "message": "Account balance must be 0.00 before deletion.",
                }

            conn.execute("DELETE FROM accounts WHERE account_number = ?", (account_number,))
        return {"success": True, "message": "Account deleted successfully."}


class BankingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bank = BankingSystem()
        self.setWindowTitle("Banking Management System")
        self.setMinimumSize(980, 720)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        title = QLabel("Banking Management System")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Manage customer accounts, transactions, and updates")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignCenter)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_account_tab(), "Create Account")
        self.tabs.addTab(self._check_account_tab(), "Check Account")
        self.tabs.addTab(self._deposit_tab(), "Deposit")
        self.tabs.addTab(self._withdrawal_tab(), "Withdrawal")
        self.tabs.addTab(self._transfer_tab(), "Transfer")
        self.tabs.addTab(self._update_tab(), "Update Info")
        self.tabs.addTab(self._delete_tab(), "Delete Account")

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setPlaceholderText("Operation logs appear here...")
        self.activity_log.setMaximumHeight(170)

        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)
        root_layout.addWidget(self.tabs, 1)
        root_layout.addWidget(QLabel("Activity Log"))
        root_layout.addWidget(self.activity_log)

        self.setCentralWidget(root)

    def _form_shell(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)
        form.setHorizontalSpacing(24)

        status = QLabel("")
        status.setObjectName("statusLabel")
        status.setWordWrap(True)

        layout.addLayout(form)
        return tab, layout, form, status

    def _create_account_tab(self):
        tab, layout, form, status = self._form_shell()
        self.create_name = QLineEdit()
        self.create_phone = QLineEdit()
        self.create_email = QLineEdit()
        self.create_address = QLineEdit()
        self.create_pin = QLineEdit()
        self.create_pin.setEchoMode(QLineEdit.Password)
        self.create_opening_balance = QLineEdit("0")

        form.addRow("Full Name:", self.create_name)
        form.addRow("Phone:", self.create_phone)
        form.addRow("Email:", self.create_email)
        form.addRow("Address:", self.create_address)
        form.addRow("4-Digit PIN:", self.create_pin)
        form.addRow("Opening Balance:", self.create_opening_balance)

        action = QPushButton("Create Account")
        action.clicked.connect(lambda: self._handle_create_account(status))

        layout.addWidget(action)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _check_account_tab(self):
        tab, layout, form, status = self._form_shell()
        self.check_account_number = QLineEdit()
        self.check_pin = QLineEdit()
        self.check_pin.setEchoMode(QLineEdit.Password)
        self.check_result = QTextEdit()
        self.check_result.setReadOnly(True)
        self.check_result.setPlaceholderText("Account details will appear here.")

        form.addRow("Account Number:", self.check_account_number)
        form.addRow("PIN (optional):", self.check_pin)

        action = QPushButton("Check Account")
        action.clicked.connect(lambda: self._handle_check_account(status))

        layout.addWidget(action)
        layout.addWidget(status)
        layout.addWidget(self.check_result)
        return tab

    def _deposit_tab(self):
        tab, layout, form, status = self._form_shell()
        self.deposit_account = QLineEdit()
        self.deposit_amount = QLineEdit()

        form.addRow("Account Number:", self.deposit_account)
        form.addRow("Amount:", self.deposit_amount)

        action = QPushButton("Deposit")
        action.clicked.connect(lambda: self._handle_deposit(status))

        layout.addWidget(action)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _withdrawal_tab(self):
        tab, layout, form, status = self._form_shell()
        self.withdraw_account = QLineEdit()
        self.withdraw_pin = QLineEdit()
        self.withdraw_pin.setEchoMode(QLineEdit.Password)
        self.withdraw_amount = QLineEdit()

        form.addRow("Account Number:", self.withdraw_account)
        form.addRow("PIN:", self.withdraw_pin)
        form.addRow("Amount:", self.withdraw_amount)

        action = QPushButton("Withdraw")
        action.clicked.connect(lambda: self._handle_withdrawal(status))

        layout.addWidget(action)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _transfer_tab(self):
        tab, layout, form, status = self._form_shell()
        self.transfer_from_account = QLineEdit()
        self.transfer_pin = QLineEdit()
        self.transfer_pin.setEchoMode(QLineEdit.Password)
        self.transfer_to_account = QLineEdit()
        self.transfer_amount = QLineEdit()

        form.addRow("From Account:", self.transfer_from_account)
        form.addRow("From PIN:", self.transfer_pin)
        form.addRow("To Account:", self.transfer_to_account)
        form.addRow("Amount:", self.transfer_amount)

        action = QPushButton("Transfer")
        action.clicked.connect(lambda: self._handle_transfer(status))

        layout.addWidget(action)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _update_tab(self):
        tab, layout, form, status = self._form_shell()
        self.update_account = QLineEdit()
        self.update_pin = QLineEdit()
        self.update_pin.setEchoMode(QLineEdit.Password)
        self.update_name = QLineEdit()
        self.update_phone = QLineEdit()
        self.update_email = QLineEdit()
        self.update_address = QLineEdit()
        note = QLabel("Leave any field blank to keep the existing value.")
        note.setObjectName("noteLabel")

        form.addRow("Account Number:", self.update_account)
        form.addRow("PIN:", self.update_pin)
        form.addRow("New Full Name:", self.update_name)
        form.addRow("New Phone:", self.update_phone)
        form.addRow("New Email:", self.update_email)
        form.addRow("New Address:", self.update_address)

        action = QPushButton("Update Information")
        action.clicked.connect(lambda: self._handle_update(status))

        layout.addWidget(note)
        layout.addWidget(action)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _delete_tab(self):
        tab, layout, form, status = self._form_shell()
        self.delete_account = QLineEdit()
        self.delete_pin = QLineEdit()
        self.delete_pin.setEchoMode(QLineEdit.Password)
        self.delete_confirm = QCheckBox("I confirm this account should be deleted.")

        form.addRow("Account Number:", self.delete_account)
        form.addRow("PIN:", self.delete_pin)

        action_row = QHBoxLayout()
        action = QPushButton("Delete Account")
        action.clicked.connect(lambda: self._handle_delete(status))
        action_row.addWidget(self.delete_confirm)
        action_row.addStretch()
        action_row.addWidget(action)

        layout.addLayout(action_row)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _set_status(self, label, result):
        message = result.get("message", "")
        success = result.get("success", False)
        label.setText(message)
        label.setProperty("status", "ok" if success else "error")
        label.style().unpolish(label)
        label.style().polish(label)
        self._log(message, success)

    def _log(self, message, success):
        stamp = datetime.now().strftime("%H:%M:%S")
        level = "INFO" if success else "ERROR"
        self.activity_log.append(f"[{stamp}] {level} - {message}")

    def _handle_create_account(self, status_label):
        result = self.bank.create_user_account(
            full_name=self.create_name.text(),
            phone=self.create_phone.text(),
            email=self.create_email.text(),
            address=self.create_address.text(),
            pin=self.create_pin.text(),
            opening_balance=self.create_opening_balance.text(),
        )
        self._set_status(status_label, result)
        if result.get("success"):
            account_number = result["data"]["account_number"]
            QMessageBox.information(
                self,
                "Account Created",
                f"Account was created successfully.\nAccount Number: {account_number}",
            )

    def _handle_check_account(self, status_label):
        pin = self.check_pin.text().strip() or None
        result = self.bank.check_user_account(self.check_account_number.text(), pin=pin)
        self._set_status(status_label, result)
        if result.get("success"):
            data = result["data"]
            details = (
                f"Account Number : {data['account_number']}\n"
                f"Name           : {data['full_name']}\n"
                f"Phone          : {data['phone'] or '-'}\n"
                f"Email          : {data['email'] or '-'}\n"
                f"Address        : {data['address'] or '-'}\n"
                f"Balance        : ${data['balance']:,.2f}\n"
                f"Created At     : {data['created_at']}"
            )
            self.check_result.setText(details)
        else:
            self.check_result.clear()

    def _handle_deposit(self, status_label):
        result = self.bank.deposit_money(
            self.deposit_account.text(),
            self.deposit_amount.text(),
        )
        self._set_status(status_label, result)

    def _handle_withdrawal(self, status_label):
        result = self.bank.widrawal_money(
            self.withdraw_account.text(),
            self.withdraw_pin.text(),
            self.withdraw_amount.text(),
        )
        self._set_status(status_label, result)

    def _handle_transfer(self, status_label):
        result = self.bank.trainsfer_money(
            self.transfer_from_account.text(),
            self.transfer_pin.text(),
            self.transfer_to_account.text(),
            self.transfer_amount.text(),
        )
        self._set_status(status_label, result)
        if result.get("success"):
            balances = result["data"]
            self.activity_log.append(
                "Source balance: ${:,.2f} | Destination balance: ${:,.2f}".format(
                    balances["source_balance"], balances["destination_balance"]
                )
            )

    def _handle_update(self, status_label):
        result = self.bank.update_user_information(
            account_number=self.update_account.text(),
            pin=self.update_pin.text(),
            full_name=self.update_name.text(),
            phone=self.update_phone.text(),
            email=self.update_email.text(),
            address=self.update_address.text(),
        )
        if result.get("success"):
            result["message"] = "User information updated successfully."
        self._set_status(status_label, result)

    def _handle_delete(self, status_label):
        if not self.delete_confirm.isChecked():
            self._set_status(
                status_label,
                {"success": False, "message": "Please confirm account deletion first."},
            )
            return
        result = self.bank.delete_user_account(
            self.delete_account.text(),
            self.delete_pin.text(),
        )
        self._set_status(status_label, result)


def load_qss(app, qss_path="styles.qss"):
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())


def main():
    app = QApplication(sys.argv)
    load_qss(app)
    window = BankingApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
