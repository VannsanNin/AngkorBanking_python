import sqlite3


def transfer_money(bank, from_account, from_pin, to_account, amount):
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

    pin_hash = bank._hash_pin(from_pin)
    with bank._connect() as conn:
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
