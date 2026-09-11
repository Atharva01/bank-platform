"""One-off bootstrap for the first staff/admin account (Phase 6 - Auth &
Authorisation). There's no self-registration endpoint on purpose - staff
accounts aren't public signup. Run manually against the target DB:

    uv run python scripts/create_staff_user.py

Prompts for a username and password, hashes the password (never stores
it raw), and inserts the StaffUser row directly.
"""

import getpass
import sys
import uuid

from sqlalchemy import select

from bank_platform.auth import hash_password
from bank_platform.database import SessionLocal
from bank_platform.models import StaffUser


def main() -> None:
    username = input("Staff username: ").strip()
    if not username:
        sys.exit("Username must not be empty.")

    password = getpass.getpass("Password: ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters.")
    if password != getpass.getpass("Confirm password: "):
        sys.exit("Passwords did not match.")

    db = SessionLocal()
    try:
        if db.execute(select(StaffUser).where(StaffUser.username == username)).scalar_one_or_none():
            sys.exit(f"A staff user named {username!r} already exists.")
        db.add(StaffUser(id=str(uuid.uuid4()), username=username, hashed_password=hash_password(password)))
        db.commit()
    finally:
        db.close()

    print(f"Created staff user {username!r}.")


if __name__ == "__main__":
    main()
