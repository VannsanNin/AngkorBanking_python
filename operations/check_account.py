from datetime import datetime


def _normalize_account_number(raw_account_number):
    return "".join(char for char in raw_account_number if char.isdigit())


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
    normalized_account_number = _normalize_account_number(raw_account_number)

    if not raw_account_number:
        return {"success": False, "message": "Account number is required."}
    if any(not (char.isdigit() or char in " -") for char in raw_account_number):
        return {
            "success": False,
            "message": "Account number can contain only digits, spaces, or hyphens.",
        }
    if not normalized_account_number or len(normalized_account_number) != 10:
        return {"success": False, "message": "Account number must be 10 digits."}

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
        "balance": row[9],
        "created_at": row[10],
    }
    return {"success": True, "message": "Account found.", "data": data}
