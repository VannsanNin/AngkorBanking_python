def deposit_money(bank, account_number, amount):
    account_number = bank._normalize_account_number(account_number)
    if len(account_number) != 10:
        return {"success": False, "message": "Account number must be 10 digits."}
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"success": False, "message": "Deposit amount must be numeric."}
    if amount <= 0:
        return {"success": False, "message": "Deposit amount must be greater than zero."}

    with bank._connect() as conn:
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
