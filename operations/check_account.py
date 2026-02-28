def check_user_account(bank, account_number, pin=None):
    account_number = account_number.strip()
    with bank._connect() as conn:
        row = conn.execute(
            """
            SELECT
                account_number,
                full_name,
                phone,
                email,
                address,
                id_card_number,
                id_card_issue_date,
                id_card_expiry_date,
                career,
                balance,
                created_at,
                pin_hash
            FROM accounts
            WHERE account_number = ?
            """,
            (account_number,),
        ).fetchone()

    if not row:
        return {"success": False, "message": "Account not found."}
    if pin and bank._hash_pin(pin) != row[11]:
        return {"success": False, "message": "Invalid PIN."}

    data = {
        "account_number": row[0],
        "full_name": row[1],
        "phone": row[2],
        "email": row[3],
        "address": row[4],
        "id_card_number": row[5],
        "id_card_issue_date": row[6],
        "id_card_expiry_date": row[7],
        "career": row[8],
        "balance": row[9],
        "created_at": row[10],
    }
    return {"success": True, "message": "Account found.", "data": data}
