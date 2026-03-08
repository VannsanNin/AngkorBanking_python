def delete_user_account(bank, account_number, pin):
    account_number = bank._normalize_account_number(account_number)
    if len(account_number) != 10:
        return {"success": False, "message": "Account number must be 10 digits."}

    with bank._connect() as conn:
        pin_result = bank._verify_account_pin(conn, account_number, pin)
        if not pin_result.get("success"):
            return pin_result

        row = conn.execute(
            "SELECT balance FROM accounts WHERE account_number = ?",
            (account_number,),
        ).fetchone()
        if not row:
            return {"success": False, "message": "Account not found."}
        balance = float(row[0] or 0.0)
        # SQLite stores REAL as floating point; treat values that round to 0.00 as zero.
        if round(balance, 2) != 0:
            return {
                "success": False,
                "message": (
                    "Account balance must be 0.00 before deletion. "
                    f"Current balance: ${balance:,.2f}"
                ),
            }

        conn.execute("DELETE FROM accounts WHERE account_number = ?", (account_number,))
    return {"success": True, "message": "Account deleted successfully."}
