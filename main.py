import hashlib
import os
import random
import re
import sqlite3
import sys
from datetime import datetime

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from operations.check_account import check_user_account as check_user_account_op
from operations.create_account import create_user_account as create_user_account_op
from operations.delete_account import delete_user_account as delete_user_account_op
from operations.deposit import deposit_money as deposit_money_op
from operations.transfer import transfer_money as transfer_money_op
from operations.update_account import update_user_information as update_user_information_op
from operations.withdrawal import withdrawal_money as withdrawal_money_op


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
                    phone TEXT NOT NULL,
                    email TEXT,
                    address TEXT NOT NULL,
                    id_card_number TEXT NOT NULL,
                    id_card_issue_date TEXT NOT NULL,
                    id_card_expiry_date TEXT NOT NULL,
                    career TEXT NOT NULL,
                    pin_hash TEXT NOT NULL,
                    balance REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._migrate_accounts_table(conn)

    @staticmethod
    def _migrate_accounts_table(conn):
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()
        }
        required_columns = {
            "id_card_number": "TEXT NOT NULL DEFAULT ''",
            "id_card_issue_date": "TEXT NOT NULL DEFAULT ''",
            "id_card_expiry_date": "TEXT NOT NULL DEFAULT ''",
            "career": "TEXT NOT NULL DEFAULT ''",
        }

        for column, definition in required_columns.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE accounts ADD COLUMN {column} {definition}")

        conn.execute("UPDATE accounts SET phone = '' WHERE phone IS NULL")
        conn.execute("UPDATE accounts SET address = '' WHERE address IS NULL")
        conn.execute("UPDATE accounts SET email = '' WHERE email IS NULL")
        conn.execute("UPDATE accounts SET id_card_number = '' WHERE id_card_number IS NULL")
        conn.execute(
            "UPDATE accounts SET id_card_issue_date = '' WHERE id_card_issue_date IS NULL"
        )
        conn.execute(
            "UPDATE accounts SET id_card_expiry_date = '' WHERE id_card_expiry_date IS NULL"
        )
        conn.execute("UPDATE accounts SET career = '' WHERE career IS NULL")

    @staticmethod
    def _hash_pin(pin):
        return hashlib.sha256(pin.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_pin(pin):
        return pin.isdigit() and len(pin) == 4

    @staticmethod
    def _validate_date(date_text):
        try:
            parsed = datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError:
            return False
        return parsed.strftime("%Y-%m-%d") == date_text

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
        self,
        full_name,
        phone,
        email,
        current_address,
        id_card_number,
        id_card_issue_date,
        id_card_expiry_date,
        career,
        pin,
        opening_balance=0.0,
    ):
        return create_user_account_op(
            self,
            full_name=full_name,
            phone=phone,
            email=email,
            current_address=current_address,
            id_card_number=id_card_number,
            id_card_issue_date=id_card_issue_date,
            id_card_expiry_date=id_card_expiry_date,
            career=career,
            pin=pin,
            opening_balance=opening_balance,
        )

    def check_user_account(self, account_number, pin=None):
        return check_user_account_op(self, account_number=account_number, pin=pin)

    def deposit_money(self, account_number, amount):
        return deposit_money_op(self, account_number=account_number, amount=amount)

    def withdrawal_money(self, account_number, pin, amount):
        return withdrawal_money_op(self, account_number=account_number, pin=pin, amount=amount)

    def transfer_money(self, from_account, from_pin, to_account, amount):
        return transfer_money_op(
            self,
            from_account=from_account,
            from_pin=from_pin,
            to_account=to_account,
            amount=amount,
        )

    def update_user_information(
        self,
        account_number,
        pin,
        full_name=None,
        phone=None,
        email=None,
        current_address=None,
        id_card_number=None,
        id_card_issue_date=None,
        id_card_expiry_date=None,
        career=None,
    ):
        return update_user_information_op(
            self,
            account_number=account_number,
            pin=pin,
            full_name=full_name,
            phone=phone,
            email=email,
            current_address=current_address,
            id_card_number=id_card_number,
            id_card_issue_date=id_card_issue_date,
            id_card_expiry_date=id_card_expiry_date,
            career=career,
        )

    def delete_user_account(self, account_number, pin):
        return delete_user_account_op(self, account_number=account_number, pin=pin)


class BankingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bank = BankingSystem()
        self.setWindowTitle("Banking Management System")
        self.setMinimumSize(980, 720)
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("rootContainer")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        header_card = QWidget()
        header_card.setObjectName("headerCard")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(24, 16, 24, 16)
        header_layout.setSpacing(4)

        title = QLabel("Banking Management System")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        subtitle = QLabel("Manage customer accounts, transactions, and updates")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._create_account_tab(), "Create Account")
        self.tabs.addTab(self._check_account_tab(), "Check Account")
        self.tabs.addTab(self._deposit_tab(), "Deposit")
        self.tabs.addTab(self._withdrawal_tab(), "Withdrawal")
        self.tabs.addTab(self._transfer_tab(), "Transfer")
        self.tabs.addTab(self._update_tab(), "Update Info")
        self.tabs.addTab(self._delete_tab(), "Delete Account")

        log_card = QWidget()
        log_card.setObjectName("logCard")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 12, 16, 16)
        log_layout.setSpacing(8)

        log_title = QLabel("Activity Log")
        log_title.setObjectName("sectionLabel")
        self.log_toggle_button = QToolButton()
        self.log_toggle_button.setObjectName("logToggleButton")
        self.log_toggle_button.setCheckable(True)
        self.log_toggle_button.setArrowType(Qt.DownArrow)
        self.log_toggle_button.setToolTip("Minimize activity log")
        self.log_toggle_button.clicked.connect(self._toggle_activity_log)

        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.addWidget(log_title)
        log_header.addStretch()
        log_header.addWidget(self.log_toggle_button)

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setPlaceholderText("Operation logs appear here...")
        self.activity_log.setMinimumHeight(140)
        self.activity_log.setMaximumHeight(190)

        log_layout.addLayout(log_header)
        log_layout.addWidget(self.activity_log)

        root_layout.addWidget(header_card)
        root_layout.addWidget(self.tabs, 1)
        root_layout.addWidget(log_card)

        self.setCentralWidget(root)

    def _form_shell(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("tabScrollArea")

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(18, 18, 18, 18)
        scroll_content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("formCard")
        card.setMaximumWidth(780)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)
        form.setHorizontalSpacing(22)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setFormAlignment(Qt.AlignTop)

        status = QLabel("")
        status.setObjectName("statusLabel")
        status.setWordWrap(True)

        layout.addLayout(form)
        scroll_content_layout.addWidget(card, 0, Qt.AlignTop | Qt.AlignHCenter)
        scroll_content_layout.addStretch()
        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll)
        return tab, layout, form, status

    def _create_account_tab(self):
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("tabScrollArea")

        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setContentsMargins(18, 18, 18, 18)
        scroll_content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("formCard")
        card.setMaximumWidth(1140)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(20)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        form_title = QLabel("ID Information Form")
        form_title.setObjectName("sectionLabel")
        form_note = QLabel("Fields marked * are required.")
        form_note.setObjectName("noteLabel")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(10)
        form.setHorizontalSpacing(22)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        form.setFormAlignment(Qt.AlignTop)

        status = QLabel("")
        status.setObjectName("statusLabel")
        status.setWordWrap(True)

        self.create_name = QLineEdit()
        self.create_phone = QLineEdit()
        self.create_address = QLineEdit()
        self.create_career = QLineEdit()
        self.create_id_card_number = QLineEdit()
        self.create_id_card_issue_date = QDateEdit()
        self.create_id_card_issue_date.setCalendarPopup(True)
        self.create_id_card_issue_date.setDate(QDate.currentDate())
        self.create_id_card_expiry_date = QDateEdit()
        self.create_id_card_expiry_date.setCalendarPopup(True)
        self.create_id_card_expiry_date.setDate(QDate.currentDate().addYears(10))
        self.create_email = QLineEdit()
        self.create_pin = QLineEdit()
        self.create_pin.setEchoMode(QLineEdit.Password)
        self.create_opening_balance = QLineEdit("0")
        self.create_validation_hint = QLabel("")
        self.create_validation_hint.setObjectName("noteLabel")

        form.addRow("ID Card Number *:", self.create_id_card_number)
        form.addRow("Date Create ID Card *:", self.create_id_card_issue_date)
        form.addRow("Expiry Date *:", self.create_id_card_expiry_date)
        form.addRow("Career *:", self.create_career)
        form.addRow("Current Address *:", self.create_address)
        form.addRow("Phone Number *:", self.create_phone)
        form.addRow("Full Name *:", self.create_name)
        form.addRow("Email:", self.create_email)
        form.addRow("4-Digit PIN *:", self.create_pin)
        form.addRow("Opening Balance:", self.create_opening_balance)

        self.create_save_button = QPushButton("Save")
        self.create_save_button.clicked.connect(lambda: self._handle_create_account(status))
        self.create_clear_button = QPushButton("Clear")
        self.create_clear_button.setObjectName("secondaryButton")
        self.create_clear_button.clicked.connect(lambda: self._handle_clear_create_form(status))

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.addWidget(self.create_save_button)
        action_row.addWidget(self.create_clear_button)
        action_row.addStretch()

        left_layout.addWidget(form_title)
        left_layout.addWidget(form_note)
        left_layout.addSpacing(6)
        left_layout.addLayout(form)
        left_layout.addLayout(action_row)
        left_layout.addWidget(self.create_validation_hint)
        left_layout.addWidget(status)
        left_layout.addStretch()

        right_panel = QWidget()
        right_panel.setObjectName("previewPanel")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(8)

        preview_title = QLabel("ID Preview")
        preview_title.setObjectName("sectionLabel")
        preview_note = QLabel("Preview layout only (not an official card design).")
        preview_note.setObjectName("noteLabel")

        preview_card = QWidget()
        preview_card.setObjectName("previewCard")
        preview_card_layout = QVBoxLayout(preview_card)
        preview_card_layout.setContentsMargins(14, 14, 14, 14)
        preview_card_layout.setSpacing(10)

        preview_header = QHBoxLayout()
        preview_header.setSpacing(8)
        preview_left = QVBoxLayout()
        preview_left.setContentsMargins(0, 0, 0, 0)
        preview_left.setSpacing(2)

        preview_tag = QLabel("ID CARD")
        preview_tag.setObjectName("previewMetaLabel")
        self.preview_id_card_number = QLabel("— — — — — —")
        self.preview_id_card_number.setObjectName("previewNumber")
        self.preview_status_badge = QLabel("Status: Unknown")
        self.preview_status_badge.setObjectName("previewBadge")
        self.preview_status_badge.setProperty("state", "unknown")

        preview_left.addWidget(preview_tag)
        preview_left.addWidget(self.preview_id_card_number)
        preview_header.addLayout(preview_left, 1)
        preview_header.addWidget(self.preview_status_badge, 0, Qt.AlignTop)

        details_grid = QGridLayout()
        details_grid.setHorizontalSpacing(14)
        details_grid.setVerticalSpacing(8)

        def _create_preview_item(title_text):
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(2)
            title = QLabel(title_text)
            title.setObjectName("previewMetaLabel")
            value = QLabel("—")
            value.setObjectName("previewMetaValue")
            value.setWordWrap(True)
            container_layout.addWidget(title)
            container_layout.addWidget(value)
            return container, value

        issue_item, self.preview_issue_date = _create_preview_item("Date Create ID Card")
        expiry_item, self.preview_expiry_date = _create_preview_item("Expiry Date")
        career_item, self.preview_career = _create_preview_item("Career")
        phone_item, self.preview_phone = _create_preview_item("Phone")

        details_grid.addWidget(issue_item, 0, 0)
        details_grid.addWidget(expiry_item, 0, 1)
        details_grid.addWidget(career_item, 1, 0)
        details_grid.addWidget(phone_item, 1, 1)

        address_title = QLabel("Current Address")
        address_title.setObjectName("previewMetaLabel")
        self.preview_address = QLabel("—")
        self.preview_address.setObjectName("previewMetaValue")
        self.preview_address.setWordWrap(True)

        preview_footer = QLabel("Generated preview for display only.")
        preview_footer.setObjectName("previewFooter")

        preview_card_layout.addLayout(preview_header)
        preview_card_layout.addLayout(details_grid)
        preview_card_layout.addWidget(address_title)
        preview_card_layout.addWidget(self.preview_address)
        preview_card_layout.addWidget(preview_footer)

        right_layout.addWidget(preview_title)
        right_layout.addWidget(preview_note)
        right_layout.addWidget(preview_card)
        right_layout.addStretch()

        card_layout.addWidget(left_panel, 3)
        card_layout.addWidget(right_panel, 2)

        scroll_content_layout.addWidget(card, 0, Qt.AlignTop | Qt.AlignHCenter)
        scroll_content_layout.addStretch()
        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll)

        self.create_fields = [
            self.create_id_card_number,
            self.create_id_card_issue_date,
            self.create_id_card_expiry_date,
            self.create_career,
            self.create_address,
            self.create_phone,
            self.create_name,
            self.create_email,
            self.create_pin,
            self.create_opening_balance,
        ]
        for field in self.create_fields:
            if isinstance(field, QLineEdit):
                field.textChanged.connect(self._sync_create_preview_and_state)
            elif isinstance(field, QDateEdit):
                field.dateChanged.connect(self._sync_create_preview_and_state)
        self._sync_create_preview_and_state()
        return tab

    @staticmethod
    def _display_or_dash(value, dash="—"):
        text = value.strip() if value is not None else ""
        return text if text else dash

    def _create_preview_status(self):
        expiry_date = self.create_id_card_expiry_date.date().toPyDate()
        if expiry_date < datetime.now().date():
            return "Status: Expired", "expired"
        return "Status: Active", "active"

    def _collect_create_form_errors(self):
        errors = []
        if not self.create_id_card_number.text().strip():
            errors.append("ID card number is required.")

        issue_date = self.create_id_card_issue_date.date().toPyDate()
        expiry_date = self.create_id_card_expiry_date.date().toPyDate()

        if expiry_date <= issue_date:
            errors.append("Expiry date must be after ID card create date.")

        if not self.create_career.text().strip():
            errors.append("Career is required.")
        if not self.create_address.text().strip():
            errors.append("Current address is required.")

        phone_number = self.create_phone.text().strip()
        if not phone_number:
            errors.append("Phone number is required.")
        elif not re.fullmatch(r"[0-9+()\-\s]{6,20}", phone_number):
            errors.append("Enter a valid phone number.")

        if not self.create_name.text().strip():
            errors.append("Full name is required.")

        pin = self.create_pin.text().strip()
        if not pin:
            errors.append("PIN is required.")
        elif not self.bank._validate_pin(pin):
            errors.append("PIN must be exactly 4 digits.")

        opening_balance = self.create_opening_balance.text().strip() or "0"
        try:
            opening_balance_value = float(opening_balance)
            if opening_balance_value < 0:
                errors.append("Opening balance cannot be negative.")
        except (TypeError, ValueError):
            errors.append("Opening balance must be numeric.")

        return errors

    def _sync_create_preview_and_state(self):
        self.preview_id_card_number.setText(
            self._display_or_dash(self.create_id_card_number.text(), "— — — — — —")
        )
        self.preview_issue_date.setText(self.create_id_card_issue_date.date().toString("yyyy-MM-dd"))
        self.preview_expiry_date.setText(
            self.create_id_card_expiry_date.date().toString("yyyy-MM-dd")
        )
        self.preview_career.setText(self._display_or_dash(self.create_career.text()))
        self.preview_phone.setText(self._display_or_dash(self.create_phone.text()))
        self.preview_address.setText(self._display_or_dash(self.create_address.text()))

        status_text, status_state = self._create_preview_status()
        self.preview_status_badge.setText(status_text)
        self.preview_status_badge.setProperty("state", status_state)
        self.preview_status_badge.style().unpolish(self.preview_status_badge)
        self.preview_status_badge.style().polish(self.preview_status_badge)

        errors = self._collect_create_form_errors()
        is_valid = len(errors) == 0
        self.create_save_button.setEnabled(is_valid)
        self.create_validation_hint.setText("Ready to save." if is_valid else errors[0])

    def _handle_clear_create_form(self, status_label):
        for field in self.create_fields:
            if isinstance(field, QLineEdit):
                field.clear()
            elif isinstance(field, QDateEdit):
                field.setDate(QDate.currentDate())
        self.create_opening_balance.setText("0")

        status_label.setText("")
        status_label.setProperty("status", "")
        status_label.style().unpolish(status_label)
        status_label.style().polish(status_label)

        self._sync_create_preview_and_state()

    def _check_account_tab(self):
        tab, layout, form, status = self._form_shell()
        self.check_account_number = QLineEdit()
        self.check_account_number.setPlaceholderText("10-digit account number")

        form.addRow("Account Number:", self.check_account_number)

        action = QPushButton("Check Account")
        action.clicked.connect(lambda: self._handle_check_account(status))
        self.check_account_number.returnPressed.connect(action.click)

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
        layout.addWidget(status)
        layout.addSpacing(8)

        self.check_preview_panel = QWidget()
        self.check_preview_panel.setObjectName("checkPreviewPanel")
        check_preview_layout = QVBoxLayout(self.check_preview_panel)
        check_preview_layout.setContentsMargins(14, 14, 14, 14)
        check_preview_layout.setSpacing(10)

        preview_title = QLabel("Account Preview")
        preview_title.setObjectName("sectionLabel")
        preview_note = QLabel("Modern account snapshot for faster admin review.")
        preview_note.setObjectName("noteLabel")

        summary_card = QWidget()
        summary_card.setObjectName("checkSummaryCard")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(14, 14, 14, 14)
        summary_layout.setSpacing(14)

        summary_left = QWidget()
        summary_left_layout = QVBoxLayout(summary_left)
        summary_left_layout.setContentsMargins(0, 0, 0, 0)
        summary_left_layout.setSpacing(3)
        name_title = QLabel("CUSTOMER")
        name_title.setObjectName("previewMetaLabel")
        self.check_preview_name = QLabel("—")
        self.check_preview_name.setObjectName("checkPrimaryValue")
        account_title = QLabel("ACCOUNT NUMBER")
        account_title.setObjectName("previewMetaLabel")
        self.check_preview_account_number = QLabel("— — — — — —")
        self.check_preview_account_number.setObjectName("previewNumber")
        summary_left_layout.addWidget(name_title)
        summary_left_layout.addWidget(self.check_preview_name)
        summary_left_layout.addSpacing(6)
        summary_left_layout.addWidget(account_title)
        summary_left_layout.addWidget(self.check_preview_account_number)

        summary_right = QWidget()
        summary_right_layout = QVBoxLayout(summary_right)
        summary_right_layout.setContentsMargins(0, 0, 0, 0)
        summary_right_layout.setSpacing(6)
        balance_title = QLabel("AVAILABLE BALANCE")
        balance_title.setObjectName("previewMetaLabel")
        self.check_preview_balance = QLabel("$0.00")
        self.check_preview_balance.setObjectName("checkBalanceValue")
        self.check_preview_status_badge = QLabel("Status: Unknown")
        self.check_preview_status_badge.setObjectName("previewBadge")
        self.check_preview_status_badge.setProperty("state", "unknown")
        summary_right_layout.addWidget(balance_title, 0, Qt.AlignRight)
        summary_right_layout.addWidget(self.check_preview_balance, 0, Qt.AlignRight)
        summary_right_layout.addWidget(self.check_preview_status_badge, 0, Qt.AlignRight)
        summary_right_layout.addStretch()

        summary_layout.addWidget(summary_left, 3)
        summary_layout.addWidget(summary_right, 2)

        details_card = QWidget()
        details_card.setObjectName("checkDetailsCard")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(14, 14, 14, 14)
        details_layout.setSpacing(10)

        details_grid = QGridLayout()
        details_grid.setHorizontalSpacing(16)
        details_grid.setVerticalSpacing(10)

        def _create_check_item(label_text):
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(2)
            title = QLabel(label_text)
            title.setObjectName("previewMetaLabel")
            value = QLabel("—")
            value.setObjectName("previewMetaValue")
            value.setWordWrap(True)
            container_layout.addWidget(title)
            container_layout.addWidget(value)
            return container, value

        phone_item, self.check_preview_phone = _create_check_item("Phone")
        email_item, self.check_preview_email = _create_check_item("Email")
        career_item, self.check_preview_career = _create_check_item("Career")
        id_card_item, self.check_preview_id_card_number = _create_check_item("ID Card Number")
        issue_item, self.check_preview_issue_date = _create_check_item("ID Card Create Date")
        expiry_item, self.check_preview_expiry_date = _create_check_item("ID Card Expiry Date")
        created_item, self.check_preview_created_at = _create_check_item("Created At")

        details_grid.addWidget(phone_item, 0, 0)
        details_grid.addWidget(email_item, 0, 1)
        details_grid.addWidget(career_item, 1, 0)
        details_grid.addWidget(id_card_item, 1, 1)
        details_grid.addWidget(issue_item, 2, 0)
        details_grid.addWidget(expiry_item, 2, 1)
        details_grid.addWidget(created_item, 3, 0, 1, 2)

        address_title = QLabel("Current Address")
        address_title.setObjectName("previewMetaLabel")
        self.check_preview_address = QLabel("—")
        self.check_preview_address.setObjectName("previewMetaValue")
        self.check_preview_address.setWordWrap(True)

        details_layout.addLayout(details_grid)
        details_layout.addWidget(address_title)
        details_layout.addWidget(self.check_preview_address)

        check_preview_layout.addWidget(preview_title)
        check_preview_layout.addWidget(preview_note)
        check_preview_layout.addWidget(summary_card)
        check_preview_layout.addWidget(details_card)

        layout.addWidget(self.check_preview_panel)
        self._reset_check_preview()
        return tab

    def _reset_check_preview(self):
        self.check_preview_name.setText("No account selected")
        self.check_preview_account_number.setText("— — — — — —")
        self.check_preview_balance.setText("$0.00")
        self.check_preview_status_badge.setText("Status: Unknown")
        self.check_preview_status_badge.setProperty("state", "unknown")
        self.check_preview_status_badge.style().unpolish(self.check_preview_status_badge)
        self.check_preview_status_badge.style().polish(self.check_preview_status_badge)

        self.check_preview_phone.setText("—")
        self.check_preview_email.setText("—")
        self.check_preview_career.setText("—")
        self.check_preview_id_card_number.setText("—")
        self.check_preview_issue_date.setText("—")
        self.check_preview_expiry_date.setText("—")
        self.check_preview_created_at.setText("—")
        self.check_preview_address.setText("—")

    def _deposit_tab(self):
        tab, layout, form, status = self._form_shell()
        self.deposit_account = QLineEdit()
        self.deposit_amount = QLineEdit()

        form.addRow("Account Number:", self.deposit_account)
        form.addRow("Amount:", self.deposit_amount)

        action = QPushButton("Deposit")
        action.clicked.connect(lambda: self._handle_deposit(status))

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
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

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
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

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
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
        self.update_career = QLineEdit()
        self.update_id_card_number = QLineEdit()
        self.update_id_card_issue_date = QDateEdit()
        self.update_id_card_issue_date.setCalendarPopup(True)
        self.update_id_card_issue_date.setEnabled(False)
        self.update_id_card_issue_date_check = QCheckBox("Update")
        self.update_id_card_issue_date_check.toggled.connect(self.update_id_card_issue_date.setEnabled)

        self.update_id_card_expiry_date = QDateEdit()
        self.update_id_card_expiry_date.setCalendarPopup(True)
        self.update_id_card_expiry_date.setEnabled(False)
        self.update_id_card_expiry_date_check = QCheckBox("Update")
        self.update_id_card_expiry_date_check.toggled.connect(self.update_id_card_expiry_date.setEnabled)
        note = QLabel("Leave any field blank to keep the existing value.")
        note.setObjectName("noteLabel")

        form.addRow("Account Number:", self.update_account)
        form.addRow("PIN:", self.update_pin)
        form.addRow("New Full Name:", self.update_name)
        form.addRow("New Phone Number:", self.update_phone)
        form.addRow("New Current Address:", self.update_address)
        form.addRow("New Career:", self.update_career)
        form.addRow("New ID Card Number:", self.update_id_card_number)

        issue_date_row = QHBoxLayout()
        issue_date_row.addWidget(self.update_id_card_issue_date)
        issue_date_row.addWidget(self.update_id_card_issue_date_check)
        form.addRow("New ID Card Create Date:", issue_date_row)

        expiry_date_row = QHBoxLayout()
        expiry_date_row.addWidget(self.update_id_card_expiry_date)
        expiry_date_row.addWidget(self.update_id_card_expiry_date_check)
        form.addRow("New ID Card Expiry Date:", expiry_date_row)
        form.addRow("New Email:", self.update_email)

        action = QPushButton("Update Information")
        action.clicked.connect(lambda: self._handle_update(status))

        layout.addWidget(note)
        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
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

    def _toggle_activity_log(self, collapsed):
        self.activity_log.setVisible(not collapsed)
        self.log_toggle_button.setArrowType(Qt.RightArrow if collapsed else Qt.DownArrow)
        self.log_toggle_button.setToolTip(
            "Expand activity log" if collapsed else "Minimize activity log"
        )

    def _handle_create_account(self, status_label):
        result = self.bank.create_user_account(
            full_name=self.create_name.text(),
            phone=self.create_phone.text(),
            current_address=self.create_address.text(),
            career=self.create_career.text(),
            id_card_number=self.create_id_card_number.text(),
            id_card_issue_date=self.create_id_card_issue_date.date().toString("yyyy-MM-dd"),
            id_card_expiry_date=self.create_id_card_expiry_date.date().toString("yyyy-MM-dd"),
            email=self.create_email.text(),
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
        result = self.bank.check_user_account(self.check_account_number.text())
        self._set_status(status_label, result)
        if result.get("success"):
            data = result["data"]
            try:
                balance_value = float(data.get("balance", 0.0))
            except (TypeError, ValueError):
                balance_value = 0.0

            status_value = (data.get("id_card_status") or "Unknown").strip()
            status_state = status_value.lower()
            if status_state == "invalid date":
                status_state = "invalid"
            elif status_state not in {"active", "expired", "invalid"}:
                status_state = "unknown"

            self.check_preview_name.setText(self._display_or_dash(data.get("full_name")))
            self.check_preview_account_number.setText(
                self._display_or_dash(data.get("account_number"), "— — — — — —")
            )
            self.check_preview_balance.setText(f"${balance_value:,.2f}")
            self.check_preview_status_badge.setText(f"Status: {status_value}")
            self.check_preview_status_badge.setProperty("state", status_state)
            self.check_preview_status_badge.style().unpolish(self.check_preview_status_badge)
            self.check_preview_status_badge.style().polish(self.check_preview_status_badge)

            self.check_preview_phone.setText(self._display_or_dash(data.get("phone")))
            self.check_preview_email.setText(self._display_or_dash(data.get("email")))
            self.check_preview_career.setText(self._display_or_dash(data.get("career")))
            self.check_preview_id_card_number.setText(
                self._display_or_dash(data.get("id_card_number"))
            )
            self.check_preview_issue_date.setText(
                self._display_or_dash(data.get("id_card_issue_date"))
            )
            self.check_preview_expiry_date.setText(
                self._display_or_dash(data.get("id_card_expiry_date"))
            )
            self.check_preview_created_at.setText(self._display_or_dash(data.get("created_at")))
            self.check_preview_address.setText(self._display_or_dash(data.get("address")))
        else:
            self._reset_check_preview()

    def _handle_deposit(self, status_label):
        result = self.bank.deposit_money(
            self.deposit_account.text(),
            self.deposit_amount.text(),
        )
        self._set_status(status_label, result)

    def _handle_withdrawal(self, status_label):
        result = self.bank.withdrawal_money(
            self.withdraw_account.text(),
            self.withdraw_pin.text(),
            self.withdraw_amount.text(),
        )
        self._set_status(status_label, result)

    def _handle_transfer(self, status_label):
        result = self.bank.transfer_money(
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
            current_address=self.update_address.text(),
            career=self.update_career.text(),
            id_card_number=self.update_id_card_number.text().strip() or None,
            id_card_issue_date=(
                self.update_id_card_issue_date.date().toString("yyyy-MM-dd")
                if self.update_id_card_issue_date_check.isChecked()
                else None
            ),
            id_card_expiry_date=(
                self.update_id_card_expiry_date.date().toString("yyyy-MM-dd")
                if self.update_id_card_expiry_date_check.isChecked()
                else None
            ),
            email=self.update_email.text().strip() or None,
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
