def withdrawal_money(bank, account_number, pin, amount):
    account_number = bank._normalize_account_number(account_number)
    if len(account_number) != 10:
        return {"success": False, "message": "Account number must be 10 digits."}

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"success": False, "message": "Withdrawal amount must be numeric."}
    if amount <= 0:
        return {
            "success": False,
            "message": "Withdrawal amount must be greater than zero.",
        }

    with bank._connect() as conn:
        pin_result = bank._verify_account_pin(conn, account_number, pin)
        if not pin_result.get("success"):
            return pin_result

        cursor = conn.execute(
            "UPDATE accounts SET balance = balance - ? WHERE account_number = ? AND balance >= ?",
            (amount, account_number, amount),
        )
        if cursor.rowcount == 0:
            row = conn.execute(
                "SELECT balance FROM accounts WHERE account_number = ?",
                (account_number,),
            ).fetchone()
            if not row:
                return {"success": False, "message": "Account not found."}
            return {"success": False, "message": "Insufficient balance."}

        new_balance = conn.execute(
            "SELECT balance FROM accounts WHERE account_number = ?", (account_number,)
        ).fetchone()[0]

    return {
        "success": True,
        "message": f"Withdrawal successful. New balance: ${new_balance:,.2f}",
        "data": {"balance": new_balance},
    }
