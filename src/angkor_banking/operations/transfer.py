import sqlite3


def transfer_money(bank, from_account, from_pin, to_account, amount):
    from_account = bank._normalize_account_number(from_account)
    to_account = bank._normalize_account_number(to_account)
    if len(from_account) != 10 or len(to_account) != 10:
        return {"success": False, "message": "Both account numbers must be 10 digits."}
    if from_account == to_account:
        return {"success": False, "message": "Source and destination accounts must differ."}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"success": False, "message": "Transfer amount must be numeric."}
    if amount <= 0:
        return {"success": False, "message": "Transfer amount must be greater than zero."}

    with bank._connect() as conn:
        try:
            conn.execute("BEGIN")
            pin_result = bank._verify_account_pin(conn, from_account, from_pin)
            if not pin_result.get("success"):
                conn.execute("ROLLBACK")
                return pin_result

            cursor = conn.execute(
                "UPDATE accounts SET balance = balance - ? WHERE account_number = ? AND balance >= ?",
                (amount, from_account, amount),
            )
            if cursor.rowcount == 0:
                conn.execute("ROLLBACK")
                existing = conn.execute(
                    "SELECT balance FROM accounts WHERE account_number = ?",
                    (from_account,),
                ).fetchone()
                if not existing:
                    return {"success": False, "message": "Source account not found."}
                return {"success": False, "message": "Insufficient source balance."}

            target = conn.execute(
                "SELECT 1 FROM accounts WHERE account_number = ?", (to_account,)
            ).fetchone()
            if not target:
                conn.execute("ROLLBACK")
                return {"success": False, "message": "Destination account not found."}

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
