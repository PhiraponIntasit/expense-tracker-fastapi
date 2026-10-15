"""Create a regular account with a year of sample data, for local development.

uv run python -m app.seed --email you@example.com --password some-password
"""

import argparse
from datetime import UTC, datetime

from sqlalchemy import exists, select

from app.accounts import EmailTakenError, authenticate, register_user
from app.db import SessionLocal
from app.demo import add_sample_data
from app.models import Transaction


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--password", default="demo-password")
    args = parser.parse_args()
    email = args.email.strip().lower()

    with SessionLocal() as db:
        try:
            user = register_user(db, email, args.password)
            print(f"Created {email}")
        except EmailTakenError:
            existing = authenticate(db, email, args.password)
            if existing is None:
                raise SystemExit(f"{email} exists and the password doesn't match") from None
            user = existing
        if db.scalar(select(exists().where(Transaction.user_id == user.id))):
            print(f"{email} already has transactions; leaving them alone")
            return
        count = add_sample_data(db, user, datetime.now(UTC).date(), seed=0)
        db.commit()
        print(f"Added {count} sample transactions. Log in as {email} / {args.password}")


if __name__ == "__main__":
    main()
