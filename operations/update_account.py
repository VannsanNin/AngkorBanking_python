from datetime import datetime


def update_user_information(
    bank,
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
):
    account_number = account_number.strip()
    pin_hash = bank._hash_pin(pin)

    updates = {}
    if full_name is not None and full_name.strip():
        updates["full_name"] = full_name.strip()
    if phone is not None and phone.strip():
        updates["phone"] = phone.strip()
    if email is not None and email.strip():
        updates["email"] = email.strip()
    if current_address is not None and current_address.strip():
        updates["address"] = current_address.strip()
    if id_card_number is not None and id_card_number.strip():
        updates["id_card_number"] = id_card_number.strip()
    if id_card_issue_date is not None and id_card_issue_date.strip():
        issue_date = id_card_issue_date.strip()
        if not bank._validate_date(issue_date):
            return {
                "success": False,
                "message": "ID card create date must be in YYYY-MM-DD format.",
            }
        updates["id_card_issue_date"] = issue_date
    if id_card_expiry_date is not None and id_card_expiry_date.strip():
        expiry_date = id_card_expiry_date.strip()
        if not bank._validate_date(expiry_date):
            return {
                "success": False,
                "message": "ID card expiry date must be in YYYY-MM-DD format.",
            }
        updates["id_card_expiry_date"] = expiry_date
    if career is not None and career.strip():
        updates["career"] = career.strip()

    if not updates:
        return {"success": False, "message": "Provide at least one field to update."}

    with bank._connect() as conn:
        current_row = conn.execute(
            """
            SELECT id_card_issue_date, id_card_expiry_date
            FROM accounts
            WHERE account_number = ? AND pin_hash = ?
            """,
            (account_number, pin_hash),
        ).fetchone()
        if not current_row:
            return {"success": False, "message": "Invalid account number or PIN."}

        final_issue_date = updates.get("id_card_issue_date", current_row[0])
        final_expiry_date = updates.get("id_card_expiry_date", current_row[1])
        if final_issue_date and final_expiry_date:
            issue_dt = datetime.strptime(final_issue_date, "%Y-%m-%d")
            expiry_dt = datetime.strptime(final_expiry_date, "%Y-%m-%d")
            if expiry_dt <= issue_dt:
                return {
                    "success": False,
                    "message": "ID card expiry date must be after ID card create date.",
                }

        set_clause = ", ".join(f"{field} = ?" for field in updates.keys())
        params = list(updates.values()) + [account_number]
        conn.execute(
            f"UPDATE accounts SET {set_clause} WHERE account_number = ?",  # nosec B608
            params,
        )

    return bank.check_user_account(account_number, pin)
