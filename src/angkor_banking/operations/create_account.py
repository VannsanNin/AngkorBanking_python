from datetime import datetime


def create_user_account(
    bank,
    full_name,
    phone,
    email,
    current_address,
    id_card_number,
    id_card_issue_date,
    id_card_expiry_date,
    career,
    pin,
    opening_balance=0.0,
):
    full_name = full_name.strip()
    phone = phone.strip()
    current_address = current_address.strip()
    id_card_number = id_card_number.strip()
    id_card_issue_date = bank._normalize_date(id_card_issue_date)
    id_card_expiry_date = bank._normalize_date(id_card_expiry_date)
    career = career.strip()

    if not full_name:
        return {"success": False, "message": "Full name is required."}
    if not phone:
        return {"success": False, "message": "Phone number is required."}
    if not current_address:
        return {"success": False, "message": "Current address is required."}
    if not id_card_number:
        return {"success": False, "message": "ID card number is required."}
    if not id_card_issue_date:
        return {
            "success": False,
            "message": "ID card create date must be in YYYY-MM-DD format.",
        }
    if not id_card_expiry_date:
        return {
            "success": False,
            "message": "ID card expiry date must be in YYYY-MM-DD format.",
        }

    issue_date = datetime.strptime(id_card_issue_date, "%Y-%m-%d")
    expiry_date = datetime.strptime(id_card_expiry_date, "%Y-%m-%d")
    if expiry_date <= issue_date:
        return {
            "success": False,
            "message": "ID card expiry date must be after ID card create date.",
        }
    if not career:
        return {"success": False, "message": "Career is required."}
    if not bank._validate_pin(pin):
        return {"success": False, "message": "PIN must be exactly 4 digits."}
    try:
        opening_balance = float(opening_balance)
    except (TypeError, ValueError):
        return {"success": False, "message": "Opening balance must be numeric."}
    if opening_balance < 0:
        return {"success": False, "message": "Opening balance cannot be negative."}

    account_number = bank._generate_account_number()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with bank._connect() as conn:
        duplicate = conn.execute(
            "SELECT 1 FROM accounts WHERE id_card_number = ? LIMIT 1",
            (id_card_number,),
        ).fetchone()
        if duplicate:
            return {"success": False, "message": "ID card number already exists."}
        duplicate_phone = conn.execute(
            "SELECT 1 FROM accounts WHERE phone = ? LIMIT 1",
            (phone,),
        ).fetchone()
        if duplicate_phone:
            return {"success": False, "message": "Phone number already exists."}
        cleaned_email = email.strip()
        if cleaned_email:
            duplicate_email = conn.execute(
                "SELECT 1 FROM accounts WHERE LOWER(email) = LOWER(?) LIMIT 1",
                (cleaned_email,),
            ).fetchone()
            if duplicate_email:
                return {"success": False, "message": "Email already exists."}

        conn.execute(
            """
            INSERT INTO accounts (
                account_number, full_name, phone, email, address,
                id_card_number, id_card_issue_date, id_card_expiry_date, career,
                pin_hash, balance, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_number,
                full_name,
                phone,
                cleaned_email,
                current_address,
                id_card_number,
                id_card_issue_date,
                id_card_expiry_date,
                career,
                bank._hash_pin(pin),
                opening_balance,
                created_at,
            ),
        )

    return {
        "success": True,
        "message": f"Account created successfully. Account Number: {account_number}",
        "data": {"account_number": account_number},
    }
