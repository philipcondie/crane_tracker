"""Run `uv run python -m app.admin USERNAME` to provision an admin."""

import argparse
from getpass import getpass

from sqlalchemy import select

from app.core.database import session_scope
from app.models.base import AdminUser
from app.services.auth import hash_password


def main():
    parser = argparse.ArgumentParser(description="Create an admin account")
    parser.add_argument("username")
    args = parser.parse_args()
    username = args.username.strip()
    if not username or len(username) > 255:
        parser.error("Username must contain 1 to 255 characters")
    password = getpass("Password (15 to 1024 characters): ")
    if not 15 <= len(password) <= 1024:
        parser.error("Password must contain 15 to 1024 characters")
    if password != getpass("Confirm password: "):
        parser.error("Passwords do not match")
    with session_scope("webserver") as session:
        if session.scalar(select(AdminUser).where(AdminUser.username == username)):
            parser.error("Username already exists")
        session.add(AdminUser(username=username, password_hash=hash_password(password)))
        session.commit()
    print(f"Created admin {username}")


if __name__ == "__main__":
    main()
