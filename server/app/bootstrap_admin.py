from getpass import getpass
from sqlalchemy import select
from app.database import SessionLocal
from app.models import Account, Profile
from app.security import hash_password
def main() -> None:
    email = input("Admin email: ").strip().lower()
    username = input("Admin username: ").strip()
    password = getpass("Admin password (at least 12 characters): ")
    confirmation = getpass("Confirm password: ")
    if not email or not username:
        raise SystemExit("Email and username are required.")
    if len(password) < 12:
        raise SystemExit("Choose a password with at least 12 characters.")
    if password != confirmation:
        raise SystemExit("The passwords do not match.")
    with SessionLocal() as db:
        admin_exists = db.scalar(
            select(Account.id).where(Account.role == "admin").limit(1)
        )
        if admin_exists:
            raise SystemExit("An administrator already exists; no account was created.")
        account = Account(
            email=email,
            username=username,
            password_hash=hash_password(password),
            role="admin",
            profile=Profile(),
        )
        db.add(account)
        db.commit()
    print("Administrator account created.")
if __name__ == "__main__":
    main()
