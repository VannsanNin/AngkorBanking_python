def withdrawal_money(bank, account_number, pin, amount):
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

    pin_hash = bank._hash_pin(pin)
    with bank._connect() as conn:
        cursor = conn.execute(
            "UPDATE accounts SET balance = balance - ? WHERE account_number = ? AND pin_hash = ? AND balance >= ?",
            (amount, account_number, pin_hash, amount),
        )
        if cursor.rowcount == 0:
            # Check if it was because of insufficient balance or wrong account/PIN
            row = conn.execute(
                "SELECT balance FROM accounts WHERE account_number = ? AND pin_hash = ?",
                (account_number, pin_hash),
            ).fetchone()
            if not row:
                return {"success": False, "message": "Invalid account number or PIN."}
            return {"success": False, "message": "Insufficient balance."}

        new_balance = conn.execute(
            "SELECT balance FROM accounts WHERE account_number = ?", (account_number,)
        ).fetchone()[0]

    return {
        "success": True,
        "message": f"Withdrawal successful. New balance: ${new_balance:,.2f}",
        "data": {"balance": new_balance},
    }
