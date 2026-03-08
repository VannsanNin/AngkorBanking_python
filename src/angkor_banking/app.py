import hashlib
import os
import random
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .operations.check_account import check_user_account as check_user_account_op
from .operations.create_account import create_user_account as create_user_account_op
from .operations.delete_account import delete_user_account as delete_user_account_op
from .operations.deposit import deposit_money as deposit_money_op
from .operations.transfer import transfer_money as transfer_money_op
from .operations.update_account import update_user_information as update_user_information_op
from .operations.withdrawal import withdrawal_money as withdrawal_money_op

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "banking.db"
LEGACY_DB_PATH = PROJECT_ROOT / "banking.db"


class BankingSystem:
    MAX_FAILED_PIN_ATTEMPTS = 3
    PIN_LOCK_MINUTES = 5
    ACCOUNT_STATUSES = ("Active", "Inactive", "Suspended")

    def __init__(self, db_path=None):
        if db_path is None:
            DATA_DIR.mkdir(exist_ok=True)
            if LEGACY_DB_PATH.exists() and not DEFAULT_DB_PATH.exists():
                db_path = LEGACY_DB_PATH
            else:
                db_path = DEFAULT_DB_PATH
        self.db_path = str(db_path)
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
                    account_status TEXT NOT NULL DEFAULT 'Active',
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
            "account_status": "TEXT NOT NULL DEFAULT 'Active'",
            "failed_pin_attempts": "INTEGER NOT NULL DEFAULT 0",
            "pin_locked_until": "TEXT",
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
        conn.execute(
            "UPDATE accounts SET account_status = 'Active' "
            "WHERE account_status IS NULL OR TRIM(account_status) = ''"
        )
        conn.execute(
            "UPDATE accounts SET account_status = 'Active' "
            "WHERE LOWER(TRIM(account_status)) NOT IN ('active', 'inactive', 'suspended')"
        )
        conn.execute(
            "UPDATE accounts SET failed_pin_attempts = 0 WHERE failed_pin_attempts IS NULL"
        )

    @staticmethod
    def _normalize_account_number(raw_account_number):
        raw_account_number = str(raw_account_number or "").strip()
        return "".join(char for char in raw_account_number if char.isdigit())

    def _resolve_account_number(self, account_or_id):
        lookup_value = str(account_or_id or "").strip()
        if not lookup_value:
            return None

        normalized_account = self._normalize_account_number(lookup_value)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT account_number
                FROM accounts
                WHERE account_number = ? OR id_card_number = ?
                LIMIT 1
                """,
                (normalized_account, lookup_value),
            ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _format_lock_until(locked_until):
        return locked_until.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_lock_until(locked_until_text):
        locked_until_text = (locked_until_text or "").strip()
        if not locked_until_text:
            return None
        try:
            return datetime.strptime(locked_until_text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def _verify_account_pin(self, conn, account_number, pin):
        pin = str(pin or "").strip()
        if not self._validate_pin(pin):
            return {"success": False, "message": "PIN must be exactly 4 digits."}

        row = conn.execute(
            """
            SELECT pin_hash, failed_pin_attempts, pin_locked_until
            FROM accounts
            WHERE account_number = ?
            """,
            (account_number,),
        ).fetchone()
        if not row:
            return {"success": False, "message": "Account not found."}

        pin_hash, failed_attempts, pin_locked_until = row
        now = datetime.now()
        locked_until = self._parse_lock_until(pin_locked_until)
        if locked_until and now < locked_until:
            return {
                "success": False,
                "message": (
                    "Account is temporarily locked due to failed PIN attempts. "
                    f"Try again at {locked_until.strftime('%H:%M:%S')}."
                ),
            }

        if locked_until and now >= locked_until:
            conn.execute(
                "UPDATE accounts SET failed_pin_attempts = 0, pin_locked_until = NULL WHERE account_number = ?",
                (account_number,),
            )
            failed_attempts = 0

        if pin_hash == self._hash_pin(pin):
            if failed_attempts or pin_locked_until:
                conn.execute(
                    "UPDATE accounts SET failed_pin_attempts = 0, pin_locked_until = NULL WHERE account_number = ?",
                    (account_number,),
                )
            return {"success": True}

        failed_attempts = (failed_attempts or 0) + 1
        remaining = self.MAX_FAILED_PIN_ATTEMPTS - failed_attempts

        if failed_attempts >= self.MAX_FAILED_PIN_ATTEMPTS:
            locked_until = now + timedelta(minutes=self.PIN_LOCK_MINUTES)
            conn.execute(
                "UPDATE accounts SET failed_pin_attempts = 0, pin_locked_until = ? WHERE account_number = ?",
                (self._format_lock_until(locked_until), account_number),
            )
            return {
                "success": False,
                "message": (
                    "Too many failed PIN attempts. "
                    f"Account locked until {locked_until.strftime('%H:%M:%S')}."
                ),
            }

        conn.execute(
            "UPDATE accounts SET failed_pin_attempts = ? WHERE account_number = ?",
            (failed_attempts, account_number),
        )
        return {
            "success": False,
            "message": f"Invalid PIN. {remaining} attempt(s) remaining before lock.",
        }

    @staticmethod
    def _hash_pin(pin):
        return hashlib.sha256(pin.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_pin(pin):
        pin = str(pin or "")
        return pin.isdigit() and len(pin) == 4

    @staticmethod
    def _normalize_account_status(status_text):
        value = str(status_text or "").strip().lower()
        mapping = {
            "active": "Active",
            "inactive": "Inactive",
            "suspended": "Suspended",
        }
        return mapping.get(value)

    @staticmethod
    def _validate_date(date_text):
        return BankingSystem._normalize_date(date_text) is not None

    @staticmethod
    def _normalize_date(date_text):
        date_text = str(date_text or "").strip()
        if not date_text:
            return None
        # Accept Khmer numerals in date input by normalizing them to ASCII digits.
        khmer_to_ascii = str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789")
        date_text = date_text.translate(khmer_to_ascii)
        formats = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y")
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_text, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

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
        account_status=None,
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
            account_status=account_status,
        )

    def delete_user_account(self, account_number, pin):
        return delete_user_account_op(self, account_number=account_number, pin=pin)


class BankingApp(QMainWindow):
    STATUS_ROW_HEIGHT = 40

    def __init__(self):
        super().__init__()
        self.bank = BankingSystem()
        self._update_preview_verified = None
        self.setWindowTitle("Banking Management System")
        self.setMinimumSize(980, 720)
        self._build_ui()
        self._refresh_dashboard()
        self._configure_tab_order()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("rootContainer")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(16)

        topbar = QWidget()
        topbar.setObjectName("topBar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(18, 12, 18, 12)
        topbar_layout.setSpacing(10)

        title = QLabel("Banking Management System")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        topbar_layout.addWidget(title)
        topbar_layout.addStretch()

        admin_label = QLabel("Admin")
        admin_label.setObjectName("subtitleLabel")
        admin_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        logout_button = QPushButton("Logout")
        logout_button.setObjectName("secondaryButton")
        logout_button.setMinimumWidth(76)
        logout_button.setToolTip("Logout action placeholder")
        topbar_layout.addWidget(admin_label)
        topbar_layout.addWidget(logout_button)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(14)

        sidebar = QWidget()
        sidebar.setObjectName("sidebarCard")
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 14, 12, 14)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel("Menu")
        sidebar_title.setObjectName("sectionLabel")
        sidebar_layout.addWidget(sidebar_title)

        self.page_stack = QStackedWidget()
        self.page_stack.setObjectName("mainPages")
        self.page_stack.addWidget(self._dashboard_tab())
        self.page_stack.addWidget(self._create_account_tab())
        self.page_stack.addWidget(self._check_account_tab())
        self.page_stack.addWidget(self._deposit_tab())
        self.page_stack.addWidget(self._withdrawal_tab())
        self.page_stack.addWidget(self._transfer_tab())
        self.page_stack.addWidget(self._update_tab())
        self.page_stack.addWidget(self._delete_tab())

        self.sidebar_buttons = []
        nav_items = [
            "Dashboard",
            "Create Account",
            "Check Account",
            "Deposit",
            "Withdraw",
            "Transfer",
            "Update Account",
            "Delete Account",
        ]
        for index, label in enumerate(nav_items):
            button = self._build_sidebar_button(label, index)
            self.sidebar_buttons.append(button)
            sidebar_layout.addWidget(button)
        sidebar_layout.addStretch()
        self.sidebar_buttons[0].setChecked(True)

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
        self.log_toggle_button.setArrowType(Qt.UpArrow)
        self.log_toggle_button.setToolTip("Collapse activity log")
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

        main_content = QWidget()
        main_content.setObjectName("mainContentCard")
        main_content_layout = QVBoxLayout(main_content)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(12)
        main_content_layout.addWidget(self.page_stack, 1)
        main_content_layout.addWidget(log_card)

        body_layout.addWidget(sidebar)
        body_layout.addWidget(main_content, 1)

        root_layout.addWidget(topbar)
        root_layout.addWidget(body, 1)

        self.setCentralWidget(root)

    def _configure_status_label(self, label):
        label.setFixedHeight(self.STATUS_ROW_HEIGHT)
        label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        label.setWordWrap(True)

    def _configure_tab_order(self):
        self.setTabOrder(self.create_id_card_number, self.create_id_card_issue_date)
        self.setTabOrder(self.create_id_card_issue_date, self.create_id_card_expiry_date)
        self.setTabOrder(self.create_id_card_expiry_date, self.create_career)
        self.setTabOrder(self.create_career, self.create_address)
        self.setTabOrder(self.create_address, self.create_phone)
        self.setTabOrder(self.create_phone, self.create_name)
        self.setTabOrder(self.create_name, self.create_email)
        self.setTabOrder(self.create_email, self.create_pin)
        self.setTabOrder(self.create_pin, self.create_opening_balance)
        self.setTabOrder(self.create_opening_balance, self.create_save_button)
        self.setTabOrder(self.create_save_button, self.create_clear_button)

        self.setTabOrder(self.update_lookup, self.update_pin)
        self.setTabOrder(self.update_pin, self.update_name)
        self.setTabOrder(self.update_name, self.update_phone)
        self.setTabOrder(self.update_phone, self.update_address)
        self.setTabOrder(self.update_address, self.update_career)
        self.setTabOrder(self.update_career, self.update_account_status)
        self.setTabOrder(self.update_account_status, self.update_account_status_check)
        self.setTabOrder(self.update_account_status_check, self.update_id_card_number)
        self.setTabOrder(self.update_id_card_number, self.update_id_card_issue_date)
        self.setTabOrder(self.update_id_card_issue_date, self.update_id_card_issue_date_check)
        self.setTabOrder(
            self.update_id_card_issue_date_check, self.update_id_card_expiry_date
        )
        self.setTabOrder(
            self.update_id_card_expiry_date, self.update_id_card_expiry_date_check
        )
        self.setTabOrder(self.update_id_card_expiry_date_check, self.update_email)
        self.setTabOrder(self.update_email, self.update_preview_button)
        self.setTabOrder(self.update_preview_button, self.update_submit_button)

    def _build_sidebar_button(self, text, page_index):
        button = QPushButton(text)
        button.setObjectName("sidebarButton")
        button.setCheckable(True)
        button.clicked.connect(lambda checked, idx=page_index: self._set_active_page(idx))
        return button

    def _set_active_page(self, page_index):
        self.page_stack.setCurrentIndex(page_index)
        for i, button in enumerate(self.sidebar_buttons):
            button.setChecked(i == page_index)
        if page_index == 0:
            self._refresh_dashboard()

    def _dashboard_tab(self):
        tab = QWidget()
        tab.setObjectName("dashboardTab")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        hero = QWidget()
        hero.setObjectName("dashboardHeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 18, 18, 18)
        hero_layout.setSpacing(8)

        hero_header = QHBoxLayout()
        hero_header.setContentsMargins(0, 0, 0, 0)
        hero_header.setSpacing(8)

        title = QLabel("Dashboard Overview")
        title.setObjectName("sectionLabel")
        self.dashboard_last_updated = QLabel("Last updated: -")
        self.dashboard_last_updated.setObjectName("noteLabel")
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self._refresh_dashboard)

        hero_header.addWidget(title)
        hero_header.addStretch()
        hero_header.addWidget(self.dashboard_last_updated)
        hero_header.addWidget(refresh_button)

        subtitle = QLabel(
            "Live account health and balance insights from the current database."
        )
        subtitle.setObjectName("noteLabel")
        subtitle.setWordWrap(True)

        hero_layout.addLayout(hero_header)
        hero_layout.addWidget(subtitle)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(12)

        def _build_metric_card(title_text):
            card = QWidget()
            card.setObjectName("dashboardMetricCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(4)
            title_label = QLabel(title_text)
            title_label.setObjectName("dashboardMetricTitle")
            value_label = QLabel("0")
            value_label.setObjectName("dashboardMetricValue")
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            card_layout.addStretch()
            return card, value_label

        total_accounts_card, self.dashboard_total_accounts = _build_metric_card(
            "Total Accounts"
        )
        total_balance_card, self.dashboard_total_balance = _build_metric_card(
            "Total Balance"
        )
        average_balance_card, self.dashboard_average_balance = _build_metric_card(
            "Average Balance"
        )
        locked_accounts_card, self.dashboard_locked_accounts = _build_metric_card(
            "Locked Accounts"
        )

        metrics_row.addWidget(total_accounts_card)
        metrics_row.addWidget(total_balance_card)
        metrics_row.addWidget(average_balance_card)
        metrics_row.addWidget(locked_accounts_card)

        details_row = QHBoxLayout()
        details_row.setContentsMargins(0, 0, 0, 0)
        details_row.setSpacing(12)

        status_card = QWidget()
        status_card.setObjectName("dashboardStatusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(8)
        status_title = QLabel("ID Card Status")
        status_title.setObjectName("sectionLabel")
        self.dashboard_active_ids = QLabel("Active: 0")
        self.dashboard_active_ids.setObjectName("dashboardStatusActive")
        self.dashboard_expired_ids = QLabel("Expired: 0")
        self.dashboard_expired_ids.setObjectName("dashboardStatusExpired")
        self.dashboard_invalid_ids = QLabel("Invalid: 0")
        self.dashboard_invalid_ids.setObjectName("dashboardStatusInvalid")
        status_layout.addWidget(status_title)
        status_layout.addWidget(self.dashboard_active_ids)
        status_layout.addWidget(self.dashboard_expired_ids)
        status_layout.addWidget(self.dashboard_invalid_ids)
        status_layout.addStretch()

        recent_card = QWidget()
        recent_card.setObjectName("dashboardRecentCard")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(14, 12, 14, 12)
        recent_layout.setSpacing(8)
        recent_title = QLabel("Recent Accounts")
        recent_title.setObjectName("sectionLabel")
        recent_note = QLabel("Latest 5 created accounts")
        recent_note.setObjectName("noteLabel")
        self.dashboard_recent_accounts = QTableWidget(0, 4)
        self.dashboard_recent_accounts.setObjectName("dashboardRecentTable")
        self.dashboard_recent_accounts.setHorizontalHeaderLabels(
            ["Account", "Name", "Balance", "Created At"]
        )
        self.dashboard_recent_accounts.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.dashboard_recent_accounts.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.dashboard_recent_accounts.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.dashboard_recent_accounts.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.dashboard_recent_accounts.verticalHeader().setVisible(False)
        self.dashboard_recent_accounts.setAlternatingRowColors(True)
        self.dashboard_recent_accounts.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dashboard_recent_accounts.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dashboard_recent_accounts.setFocusPolicy(Qt.NoFocus)
        self.dashboard_recent_accounts.setMinimumHeight(190)
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(recent_note)
        recent_layout.addWidget(self.dashboard_recent_accounts)
        recent_layout.addStretch()

        details_row.addWidget(status_card, 1)
        details_row.addWidget(recent_card, 2)

        layout.addWidget(hero, 0, Qt.AlignTop)
        layout.addLayout(metrics_row)
        layout.addLayout(details_row)
        layout.addStretch(1)
        return tab

    def _collect_dashboard_data(self):
        now = datetime.now()
        today = now.date()
        now_text = now.strftime("%Y-%m-%d %H:%M:%S")
        with self.bank._connect() as conn:
            totals = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(balance), 0), COALESCE(AVG(balance), 0) FROM accounts"
            ).fetchone()
            locked_row = conn.execute(
                """
                SELECT COUNT(*)
                FROM accounts
                WHERE pin_locked_until IS NOT NULL
                  AND pin_locked_until > ?
                """,
                (now_text,),
            ).fetchone()
            recent_rows = conn.execute(
                """
                SELECT account_number, full_name, balance, created_at
                FROM accounts
                ORDER BY created_at DESC
                LIMIT 5
                """
            ).fetchall()
            expiry_rows = conn.execute(
                "SELECT id_card_expiry_date FROM accounts"
            ).fetchall()

        active_count = 0
        expired_count = 0
        invalid_count = 0
        for (expiry_text,) in expiry_rows:
            value = str(expiry_text or "").strip()
            if not value:
                invalid_count += 1
                continue
            try:
                expiry_date = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                invalid_count += 1
                continue
            if expiry_date < today:
                expired_count += 1
            else:
                active_count += 1

        recent_accounts = []
        for account_number, full_name, balance, created_at in recent_rows:
            safe_name = self._display_or_dash(full_name)
            try:
                safe_balance = float(balance or 0.0)
            except (TypeError, ValueError):
                safe_balance = 0.0
            recent_accounts.append(
                {
                    "account_number": self._display_or_dash(account_number, "-"),
                    "full_name": safe_name,
                    "balance": f"${safe_balance:,.2f}",
                    "created_at": self._display_or_dash(created_at, "-"),
                }
            )

        return {
            "total_accounts": int(totals[0] or 0),
            "total_balance": float(totals[1] or 0.0),
            "average_balance": float(totals[2] or 0.0),
            "locked_accounts": int(locked_row[0] or 0),
            "active_ids": active_count,
            "expired_ids": expired_count,
            "invalid_ids": invalid_count,
            "recent_accounts": recent_accounts,
        }

    def _refresh_dashboard(self):
        data = self._collect_dashboard_data()
        self.dashboard_total_accounts.setText(f"{data['total_accounts']:,}")
        self.dashboard_total_balance.setText(f"${data['total_balance']:,.2f}")
        self.dashboard_average_balance.setText(f"${data['average_balance']:,.2f}")
        self.dashboard_locked_accounts.setText(f"{data['locked_accounts']:,}")
        self.dashboard_active_ids.setText(f"Active: {data['active_ids']:,}")
        self.dashboard_expired_ids.setText(f"Expired: {data['expired_ids']:,}")
        self.dashboard_invalid_ids.setText(f"Invalid: {data['invalid_ids']:,}")
        recent_accounts = data["recent_accounts"]
        self.dashboard_recent_accounts.setRowCount(len(recent_accounts))
        for row_index, account in enumerate(recent_accounts):
            self.dashboard_recent_accounts.setItem(
                row_index, 0, QTableWidgetItem(account["account_number"])
            )
            self.dashboard_recent_accounts.setItem(
                row_index, 1, QTableWidgetItem(account["full_name"])
            )
            self.dashboard_recent_accounts.setItem(
                row_index, 2, QTableWidgetItem(account["balance"])
            )
            self.dashboard_recent_accounts.setItem(
                row_index, 3, QTableWidgetItem(account["created_at"])
            )
        self.dashboard_last_updated.setText(
            f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

    def _form_shell(self, tab_object_name=None, card_max_width=780, full_width=False):
        tab = QWidget()
        if tab_object_name:
            tab.setObjectName(tab_object_name)
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
        if card_max_width:
            card.setMaximumWidth(card_max_width)
        if full_width:
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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
        self._configure_status_label(status)

        layout.addLayout(form)
        if full_width:
            scroll_content_layout.addWidget(card)
        else:
            scroll_content_layout.addWidget(card, 0, Qt.AlignTop | Qt.AlignHCenter)
        scroll_content_layout.addStretch()
        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll)
        return tab, layout, form, status

    def _create_account_tab(self):
        tab = QWidget()
        tab.setObjectName("createAccountTab")
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
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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
        self._configure_status_label(status)

        self.create_name = QLineEdit()
        self.create_phone = QLineEdit()
        self.create_address = QLineEdit()
        self.create_career = QLineEdit()
        self.create_id_card_number = QLineEdit()
        self.create_id_card_issue_date = QDateEdit()
        self.create_id_card_issue_date.setCalendarPopup(True)
        self.create_id_card_issue_date.setDisplayFormat("yyyy-MM-dd")
        self.create_id_card_issue_date.setDate(QDate.currentDate())
        self.create_id_card_expiry_date = QDateEdit()
        self.create_id_card_expiry_date.setCalendarPopup(True)
        self.create_id_card_expiry_date.setDisplayFormat("yyyy-MM-dd")
        self.create_id_card_expiry_date.setDate(QDate.currentDate().addYears(10))
        self.create_email = QLineEdit()
        self.create_pin = QLineEdit()
        self.create_pin.setEchoMode(QLineEdit.Password)
        self.create_opening_balance = QLineEdit("0")
        self.create_validation_hint = QLabel("")
        self.create_validation_hint.setObjectName("noteLabel")

        id_section = QLabel("ID Details")
        id_section.setObjectName("sectionLabel")
        personal_section = QLabel("Personal Details")
        personal_section.setObjectName("sectionLabel")
        security_section = QLabel("Security & Opening")
        security_section.setObjectName("sectionLabel")

        form.addRow(id_section)
        form.addRow("ID Card Number *:", self.create_id_card_number)
        form.addRow("Date Create ID Card *:", self.create_id_card_issue_date)
        form.addRow("Expiry Date *:", self.create_id_card_expiry_date)
        form.addRow(personal_section)
        form.addRow("Career *:", self.create_career)
        form.addRow("Current Address *:", self.create_address)
        form.addRow("Phone Number *:", self.create_phone)
        form.addRow("Full Name *:", self.create_name)
        form.addRow("Email:", self.create_email)
        form.addRow(security_section)
        form.addRow("4-Digit PIN *:", self.create_pin)
        form.addRow("Opening Balance:", self.create_opening_balance)

        self.create_save_button = QPushButton("Save")
        self.create_save_button.clicked.connect(lambda: self._handle_create_account(status))
        self.create_clear_button = QPushButton("Clear")
        self.create_clear_button.setObjectName("secondaryButton")
        self.create_clear_button.clicked.connect(lambda: self._handle_clear_create_form(status))
        self.create_opening_balance.returnPressed.connect(self.create_save_button.click)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.addWidget(self.create_save_button)
        action_row.addWidget(self.create_clear_button)
        action_row.addStretch()

        left_layout.addWidget(form_title)
        left_layout.addWidget(form_note)
        left_layout.addSpacing(6)
        left_layout.addLayout(form)
        left_layout.addStretch(1)
        left_layout.addLayout(action_row)
        left_layout.addWidget(self.create_validation_hint)
        left_layout.addWidget(status)

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

        scroll_content_layout.addWidget(card)
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
        tab, layout, form, status = self._form_shell(
            "checkAccountTab",
            card_max_width=None,
            full_width=True,
        )
        self.check_account_number = QLineEdit()
        self.check_account_number.setPlaceholderText("10-digit account number")
        self.check_pin = QLineEdit()
        self.check_pin.setEchoMode(QLineEdit.Password)
        self.check_pin.setPlaceholderText("4-digit PIN")

        form.addRow("Account Number:", self.check_account_number)
        form.addRow("PIN:", self.check_pin)

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
        account_status_item, self.check_preview_account_status = _create_check_item(
            "Account Status"
        )
        id_card_item, self.check_preview_id_card_number = _create_check_item("ID Card Number")
        issue_item, self.check_preview_issue_date = _create_check_item("ID Card Create Date")
        expiry_item, self.check_preview_expiry_date = _create_check_item("ID Card Expiry Date")
        created_item, self.check_preview_created_at = _create_check_item("Created At")

        details_grid.addWidget(phone_item, 0, 0)
        details_grid.addWidget(email_item, 0, 1)
        details_grid.addWidget(career_item, 1, 0)
        details_grid.addWidget(account_status_item, 1, 1)
        details_grid.addWidget(id_card_item, 2, 0)
        details_grid.addWidget(issue_item, 2, 1)
        details_grid.addWidget(expiry_item, 3, 0)
        details_grid.addWidget(created_item, 3, 1)

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
        self.check_preview_account_status.setText("—")
        self.check_preview_id_card_number.setText("—")
        self.check_preview_issue_date.setText("—")
        self.check_preview_expiry_date.setText("—")
        self.check_preview_created_at.setText("—")
        self.check_preview_address.setText("—")

    def _deposit_tab(self):
        tab, layout, form, status = self._form_shell("depositTab")
        self.deposit_account = QLineEdit()
        self.deposit_amount = QLineEdit()

        form.addRow("Account Number:", self.deposit_account)
        form.addRow("Amount:", self.deposit_amount)

        action = QPushButton("Deposit")
        action.clicked.connect(lambda: self._handle_deposit(status))
        self.deposit_amount.returnPressed.connect(action.click)

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _withdrawal_tab(self):
        tab, layout, form, status = self._form_shell("withdrawalTab")
        self.withdraw_account = QLineEdit()
        self.withdraw_pin = QLineEdit()
        self.withdraw_pin.setEchoMode(QLineEdit.Password)
        self.withdraw_amount = QLineEdit()

        form.addRow("Account Number:", self.withdraw_account)
        form.addRow("PIN:", self.withdraw_pin)
        form.addRow("Amount:", self.withdraw_amount)

        action = QPushButton("Withdraw")
        action.clicked.connect(lambda: self._handle_withdrawal(status))
        self.withdraw_amount.returnPressed.connect(action.click)

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _transfer_tab(self):
        tab, layout, form, status = self._form_shell("transferTab")
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
        self.transfer_amount.returnPressed.connect(action.click)

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(action)
        layout.addLayout(action_row)
        layout.addWidget(status)
        layout.addStretch()
        return tab

    def _update_tab(self):
        tab, layout, _, status = self._form_shell(
            "updateAccountTab",
            card_max_width=None,
            full_width=True,
        )
        self.update_lookup = QLineEdit()
        self.update_lookup.setPlaceholderText("Account Number or ID Card Number")
        self.update_account = self.update_lookup
        self.update_pin = QLineEdit()
        self.update_pin.setEchoMode(QLineEdit.Password)
        self.update_pin.setPlaceholderText("4-digit PIN")
        self.update_name = QLineEdit()
        self.update_phone = QLineEdit()
        self.update_email = QLineEdit()
        self.update_address = QLineEdit()
        self.update_career = QLineEdit()
        self.update_account_status = QComboBox()
        self.update_account_status.addItems(list(self.bank.ACCOUNT_STATUSES))
        self.update_account_status.setEnabled(False)
        self.update_account_status_check = QCheckBox("Update")
        self.update_account_status_check.toggled.connect(
            self.update_account_status.setEnabled
        )
        self.update_id_card_number = QLineEdit()
        self.update_id_card_issue_date = QDateEdit()
        self.update_id_card_issue_date.setCalendarPopup(True)
        self.update_id_card_issue_date.setDisplayFormat("yyyy-MM-dd")
        self.update_id_card_issue_date.setEnabled(False)
        self.update_id_card_issue_date_check = QCheckBox("Update")
        self.update_id_card_issue_date_check.toggled.connect(self.update_id_card_issue_date.setEnabled)

        self.update_id_card_expiry_date = QDateEdit()
        self.update_id_card_expiry_date.setCalendarPopup(True)
        self.update_id_card_expiry_date.setDisplayFormat("yyyy-MM-dd")
        self.update_id_card_expiry_date.setEnabled(False)
        self.update_id_card_expiry_date_check = QCheckBox("Update")
        self.update_id_card_expiry_date_check.toggled.connect(self.update_id_card_expiry_date.setEnabled)
        self.update_lookup.textChanged.connect(self._mark_update_preview_stale)
        self.update_pin.textChanged.connect(self._mark_update_preview_stale)
        note = QLabel("Leave any update field blank to keep the current value.")
        note.setObjectName("noteLabel")

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        left_panel = QWidget()
        left_panel.setObjectName("formCard")
        left_panel.setMinimumWidth(320)
        left_panel.setMaximumWidth(360)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)
        left_title = QLabel("Account Lookup")
        left_title.setObjectName("sectionLabel")
        left_note = QLabel("Enter account number or ID card number, plus PIN.")
        left_note.setObjectName("noteLabel")
        lookup_form = QFormLayout()
        lookup_form.setLabelAlignment(Qt.AlignRight)
        lookup_form.setSpacing(10)
        lookup_form.setHorizontalSpacing(16)
        lookup_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        lookup_form.addRow("Account/ID:", self.update_lookup)
        lookup_form.addRow("PIN:", self.update_pin)

        issue_date_row = QHBoxLayout()
        issue_date_row.addWidget(self.update_id_card_issue_date)
        issue_date_row.addWidget(self.update_id_card_issue_date_check)

        expiry_date_row = QHBoxLayout()
        expiry_date_row.addWidget(self.update_id_card_expiry_date)
        expiry_date_row.addWidget(self.update_id_card_expiry_date_check)
        account_status_row = QHBoxLayout()
        account_status_row.addWidget(self.update_account_status)
        account_status_row.addWidget(self.update_account_status_check)

        self.update_preview_button = QPushButton("Preview Account")
        self.update_preview_button.clicked.connect(lambda: self._handle_update_preview(status))

        self.update_submit_button = QPushButton("Update Information")
        self.update_submit_button.clicked.connect(lambda: self._handle_update(status))
        self.update_email.returnPressed.connect(self.update_submit_button.click)

        left_layout.addWidget(left_title)
        left_layout.addWidget(left_note)
        left_layout.addLayout(lookup_form)
        left_layout.addWidget(self.update_preview_button)
        left_layout.addStretch()
        left_layout.addWidget(status)

        right_panel = QWidget()
        right_panel.setObjectName("formCard")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)
        right_title = QLabel("Preview And Update")
        right_title.setObjectName("sectionLabel")
        right_note = QLabel("Current account snapshot for safe edits before submit.")
        right_note.setObjectName("noteLabel")

        summary_card = QWidget()
        summary_card.setObjectName("updateSummaryCard")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(12)

        summary_left = QWidget()
        summary_left_layout = QVBoxLayout(summary_left)
        summary_left_layout.setContentsMargins(0, 0, 0, 0)
        summary_left_layout.setSpacing(2)
        name_title = QLabel("CUSTOMER")
        name_title.setObjectName("previewMetaLabel")
        self.update_preview_name = QLabel("No account selected")
        self.update_preview_name.setObjectName("updatePrimaryValue")
        account_title = QLabel("ACCOUNT NUMBER")
        account_title.setObjectName("previewMetaLabel")
        self.update_preview_account_number = QLabel("----------")
        self.update_preview_account_number.setObjectName("previewNumber")
        summary_left_layout.addWidget(name_title)
        summary_left_layout.addWidget(self.update_preview_name)
        summary_left_layout.addSpacing(4)
        summary_left_layout.addWidget(account_title)
        summary_left_layout.addWidget(self.update_preview_account_number)

        summary_right = QWidget()
        summary_right_layout = QVBoxLayout(summary_right)
        summary_right_layout.setContentsMargins(0, 0, 0, 0)
        summary_right_layout.setSpacing(4)
        balance_title = QLabel("AVAILABLE BALANCE")
        balance_title.setObjectName("previewMetaLabel")
        self.update_preview_balance = QLabel("$0.00")
        self.update_preview_balance.setObjectName("updateBalanceValue")
        self.update_preview_status_badge = QLabel("Status: Unknown")
        self.update_preview_status_badge.setObjectName("previewBadge")
        self.update_preview_status_badge.setProperty("state", "unknown")
        summary_right_layout.addWidget(balance_title, 0, Qt.AlignRight)
        summary_right_layout.addWidget(self.update_preview_balance, 0, Qt.AlignRight)
        summary_right_layout.addWidget(self.update_preview_status_badge, 0, Qt.AlignRight)
        summary_right_layout.addStretch()

        summary_layout.addWidget(summary_left, 1)
        summary_layout.addWidget(summary_right)

        details_card = QWidget()
        details_card.setObjectName("updateDetailsCard")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(12, 12, 12, 12)
        details_layout.setSpacing(10)

        details_grid = QGridLayout()
        details_grid.setHorizontalSpacing(16)
        details_grid.setVerticalSpacing(8)

        def _create_update_item(label_text):
            item = QWidget()
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(2)
            title = QLabel(label_text)
            title.setObjectName("previewMetaLabel")
            value = QLabel("-")
            value.setObjectName("previewMetaValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            item_layout.addWidget(title)
            item_layout.addWidget(value)
            return item, value

        phone_item, self.update_preview_phone = _create_update_item("Phone")
        email_item, self.update_preview_email = _create_update_item("Email")
        career_item, self.update_preview_career = _create_update_item("Career")
        account_status_item, self.update_preview_account_status = _create_update_item(
            "Account Status"
        )
        id_card_item, self.update_preview_id_card_number = _create_update_item("ID Card Number")
        issue_item, self.update_preview_issue_date = _create_update_item("ID Card Create Date")
        expiry_item, self.update_preview_expiry_date = _create_update_item("ID Card Expiry Date")
        created_item, self.update_preview_created_at = _create_update_item("Created At")

        details_grid.addWidget(phone_item, 0, 0)
        details_grid.addWidget(email_item, 0, 1)
        details_grid.addWidget(career_item, 1, 0)
        details_grid.addWidget(account_status_item, 1, 1)
        details_grid.addWidget(id_card_item, 2, 0)
        details_grid.addWidget(issue_item, 2, 1)
        details_grid.addWidget(expiry_item, 3, 0)
        details_grid.addWidget(created_item, 3, 1)

        address_title = QLabel("Current Address")
        address_title.setObjectName("previewMetaLabel")
        self.update_preview_address = QLabel("-")
        self.update_preview_address.setObjectName("previewMetaValue")
        self.update_preview_address.setWordWrap(True)
        self.update_preview_address.setTextInteractionFlags(Qt.TextSelectableByMouse)

        details_layout.addLayout(details_grid)
        details_layout.addWidget(address_title)
        details_layout.addWidget(self.update_preview_address)
        self._reset_update_preview()

        update_form = QFormLayout()
        update_form.setLabelAlignment(Qt.AlignRight)
        update_form.setSpacing(10)
        update_form.setHorizontalSpacing(16)
        update_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        update_form.addRow("New Full Name:", self.update_name)
        update_form.addRow("New Phone Number:", self.update_phone)
        update_form.addRow("New Current Address:", self.update_address)
        update_form.addRow("New Career:", self.update_career)
        update_form.addRow("New Account Status:", account_status_row)
        update_form.addRow("New ID Card Number:", self.update_id_card_number)
        update_form.addRow("New ID Card Create Date:", issue_date_row)
        update_form.addRow("New ID Card Expiry Date:", expiry_date_row)
        update_form.addRow("New Email:", self.update_email)

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(self.update_submit_button)

        right_layout.addWidget(right_title)
        right_layout.addWidget(right_note)
        right_layout.addWidget(summary_card)
        right_layout.addWidget(details_card)
        right_layout.addWidget(note)
        right_layout.addLayout(update_form)
        right_layout.addStretch(1)
        right_layout.addLayout(action_row)

        content_layout.addWidget(left_panel)
        content_layout.addWidget(right_panel, 1)

        layout.addWidget(content)
        return tab

    def _mark_update_preview_stale(self):
        self._update_preview_verified = None
        self._resolved_update_account_number = None

    def _reset_update_preview(self):
        self._update_preview_verified = None
        self._resolved_update_account_number = None
        self.update_preview_name.setText("No account selected")
        self.update_preview_account_number.setText("----------")
        self.update_preview_balance.setText("$0.00")
        self.update_preview_status_badge.setText("Status: Unknown")
        self.update_preview_status_badge.setProperty("state", "unknown")
        self.update_preview_status_badge.style().unpolish(self.update_preview_status_badge)
        self.update_preview_status_badge.style().polish(self.update_preview_status_badge)
        self.update_preview_phone.setText("-")
        self.update_preview_email.setText("-")
        self.update_preview_career.setText("-")
        self.update_preview_account_status.setText("-")
        self.update_preview_id_card_number.setText("-")
        self.update_preview_issue_date.setText("-")
        self.update_preview_expiry_date.setText("-")
        self.update_preview_created_at.setText("-")
        self.update_preview_address.setText("-")

    def _set_update_preview(self, data):
        status = (data.get("id_card_status") or "Unknown").strip()
        status_state = status.lower()
        if status_state == "invalid date":
            status_state = "invalid"
        elif status_state not in {"active", "expired", "invalid"}:
            status_state = "unknown"

        try:
            balance_value = float(data.get("balance", 0.0))
        except (TypeError, ValueError):
            balance_value = 0.0

        self.update_preview_name.setText(self._display_or_dash(data.get("full_name")))
        self.update_preview_account_number.setText(
            self._display_or_dash(data.get("account_number"), "----------")
        )
        self.update_preview_balance.setText(f"${balance_value:,.2f}")
        self.update_preview_status_badge.setText(f"Status: {status}")
        self.update_preview_status_badge.setProperty("state", status_state)
        self.update_preview_status_badge.style().unpolish(self.update_preview_status_badge)
        self.update_preview_status_badge.style().polish(self.update_preview_status_badge)
        self.update_preview_phone.setText(self._display_or_dash(data.get("phone")))
        self.update_preview_email.setText(self._display_or_dash(data.get("email")))
        self.update_preview_career.setText(self._display_or_dash(data.get("career")))
        account_status = self._display_or_dash(data.get("account_status"), "Active")
        self.update_preview_account_status.setText(account_status)
        if not self.update_account_status_check.isChecked():
            idx = self.update_account_status.findText(account_status)
            if idx >= 0:
                self.update_account_status.setCurrentIndex(idx)
        self.update_preview_id_card_number.setText(
            self._display_or_dash(data.get("id_card_number"))
        )
        self.update_preview_issue_date.setText(
            self._display_or_dash(data.get("id_card_issue_date"))
        )
        self.update_preview_expiry_date.setText(
            self._display_or_dash(data.get("id_card_expiry_date"))
        )
        self.update_preview_created_at.setText(
            self._display_or_dash(data.get("created_at"))
        )
        self.update_preview_address.setText(self._display_or_dash(data.get("address")))

    def _handle_update_preview(self, status_label):
        account_number = self.bank._resolve_account_number(self.update_lookup.text())
        pin = self.update_pin.text()
        if not account_number:
            self._set_status(
                status_label,
                {
                    "success": False,
                    "message": "Account not found for the provided account number or ID card number.",
                },
            )
            self._reset_update_preview()
            return

        result = self.bank.check_user_account(account_number, pin)
        self._set_status(status_label, result)
        if not result.get("success"):
            self._reset_update_preview()
            return

        self._set_update_preview(result["data"])
        self._resolved_update_account_number = account_number
        normalized_account = self.bank._normalize_account_number(account_number)
        self._update_preview_verified = (
            normalized_account,
            self.bank._hash_pin(pin.strip()),
        )

    def _delete_tab(self):
        tab, layout, form, status = self._form_shell("deleteAccountTab")
        self.delete_account = QLineEdit()
        self.delete_pin = QLineEdit()
        self.delete_pin.setEchoMode(QLineEdit.Password)
        self.delete_confirm = QCheckBox("I confirm this account should be deleted.")

        form.addRow("Account Number:", self.delete_account)
        form.addRow("PIN:", self.delete_pin)

        action_row = QHBoxLayout()
        action = QPushButton("Delete Account")
        action.clicked.connect(lambda: self._handle_delete(status))
        self.delete_pin.returnPressed.connect(action.click)
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
        if success:
            self._refresh_dashboard()

    def _log(self, message, success):
        stamp = datetime.now().strftime("%H:%M:%S")
        level = "INFO" if success else "ERROR"
        self.activity_log.append(f"[{stamp}] {level} - {message}")

    def _toggle_activity_log(self, collapsed):
        self.activity_log.setVisible(not collapsed)
        self.log_toggle_button.setArrowType(Qt.DownArrow if collapsed else Qt.UpArrow)
        self.log_toggle_button.setToolTip(
            "Expand activity log" if collapsed else "Collapse activity log"
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
        result = self.bank.check_user_account(
            self.check_account_number.text(),
            self.check_pin.text(),
        )
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
            self.check_preview_account_status.setText(
                self._display_or_dash(data.get("account_status"), "Active")
            )
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
        account_number = getattr(self, "_resolved_update_account_number", None)
        if not account_number:
            self._set_status(
                status_label,
                {
                    "success": False,
                    "message": "Preview account first before updating.",
                },
            )
            return

        normalized_account = self.bank._normalize_account_number(account_number)
        preview_key = (
            normalized_account,
            self.bank._hash_pin(self.update_pin.text().strip()),
        )
        if self._update_preview_verified != preview_key:
            self._set_status(
                status_label,
                {
                    "success": False,
                    "message": (
                        "Preview account first with the current account number and PIN "
                        "before updating."
                    ),
                },
            )
            return

        result = self.bank.update_user_information(
            account_number=account_number,
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
            account_status=(
                self.update_account_status.currentText()
                if self.update_account_status_check.isChecked()
                else None
            ),
        )
        if result.get("success"):
            result["message"] = "User information updated successfully."
            refreshed = self.bank.check_user_account(
                account_number,
                self.update_pin.text(),
            )
            if refreshed.get("success"):
                self._set_update_preview(refreshed["data"])
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


def load_qss(
    app,
    qss_dir=APP_ROOT / "assets" / "styles",
    fallback_qss_path=APP_ROOT / "assets" / "styles.qss",
    qss_files=None,
):
    if qss_files is None:
        qss_files = [
            "base.qss",
            "dashboard.qss",
            "create_account.qss",
            "check_account.qss",
            "deposit.qss",
            "withdrawal.qss",
            "transfer.qss",
            "update_account.qss",
            "delete_account.qss",
        ]

    chunks = []
    qss_dir = str(qss_dir)
    fallback_qss_path = str(fallback_qss_path)

    if os.path.isdir(qss_dir):
        for qss_name in qss_files:
            path = os.path.join(qss_dir, qss_name)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    chunks.append(f.read())
        if chunks:
            app.setStyleSheet("\n\n".join(chunks))
            return

    if os.path.exists(fallback_qss_path):
        with open(fallback_qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())


def main():
    app = QApplication(sys.argv)
    load_qss(app)
    window = BankingApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
