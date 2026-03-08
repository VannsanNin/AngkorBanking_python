from datetime import datetime


def _id_card_status(expiry_date_text):
    expiry_date_text = (expiry_date_text or "").strip()
    if not expiry_date_text:
        return "Unknown"
    try:
        expiry_date = datetime.strptime(expiry_date_text, "%Y-%m-%d").date()
    except ValueError:
        return "Invalid Date"
    return "Expired" if expiry_date < datetime.now().date() else "Active"


def check_user_account(bank, account_number, pin=None):
    raw_account_number = str(account_number or "").strip()
    normalized_account_number = bank._normalize_account_number(raw_account_number)
    pin = str(pin or "").strip()

    if not raw_account_number:
        return {"success": False, "message": "Account number is required."}
    if any(not (char.isdigit() or char in " -") for char in raw_account_number):
        return {
            "success": False,
            "message": "Account number can contain only digits, spaces, or hyphens.",
        }
    if not normalized_account_number or len(normalized_account_number) != 10:
        return {"success": False, "message": "Account number must be 10 digits."}
    if not pin:
        return {"success": False, "message": "PIN is required to check account details."}

    with bank._connect() as conn:
        pin_result = bank._verify_account_pin(conn, normalized_account_number, pin)
        if not pin_result.get("success"):
            return pin_result

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
                account_status,
                balance,
                created_at
            FROM accounts
            WHERE account_number = ?
            """,
            (normalized_account_number,),
        ).fetchone()

    if not row:
        return {"success": False, "message": "Account not found."}
    data = {
        "account_number": row[0],
        "full_name": row[1],
        "phone": row[2],
        "email": row[3],
        "address": row[4],
        "id_card_number": row[5],
        "id_card_issue_date": row[6],
        "id_card_expiry_date": row[7],
        "id_card_status": _id_card_status(row[7]),
        "career": row[8],
        "account_status": bank._normalize_account_status(row[9]) or "Active",
        "balance": row[10],
        "created_at": row[11],
    }
    return {"success": True, "message": "Account found.", "data": data}
