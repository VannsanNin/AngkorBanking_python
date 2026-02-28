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
