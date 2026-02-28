def delete_user_account(bank, account_number, pin):
    account_number = account_number.strip()
    pin_hash = bank._hash_pin(pin)
    with bank._connect() as conn:
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
