"""Set or rotate a developer's personal admin code.

    python scripts/admin_set_code.py --clerk-subject user_abc123 [--generate]

The user must already exist (signed in once), have role ``admin`` and be listed in
``ADMIN_CLERK_USER_IDS``. The code is never taken from argv or the environment: it is read
from a hidden prompt, or generated and printed once with ``--generate``. Only a salted scrypt
hash is stored. Rotating clears any lockout and ends open admin sessions.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent.admin_auth import append_audit, enroll_code, validate_code
from daily_agent.config import get_settings
from daily_agent.db import get_engine
from daily_agent.models import User


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--clerk-subject", required=True, help="Clerk user id (user_...)")
    parser.add_argument("--generate", action="store_true", help="generate a strong code and print it once")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.clerk_subject not in settings.admin_clerk_user_ids:
        print("error: subject is not in ADMIN_CLERK_USER_IDS", file=sys.stderr)
        return 2
    if args.generate:
        code = secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:20]
    else:
        code = getpass.getpass("New admin code (>=12 letters/digits): ")
        if code != getpass.getpass("Repeat: "):
            print("error: codes differ", file=sys.stderr)
            return 2
    try:
        validate_code(code)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with Session(get_engine()) as session:
        user = session.scalar(select(User).where(User.clerk_subject == args.clerk_subject))
        if user is None or user.role != "admin":
            print("error: no admin-role user with that Clerk subject", file=sys.stderr)
            return 2
        enroll_code(session, user, code)
        append_audit(session, admin_user_id=user.id, action="admin.code_set", target_user_id=user.id)
        session.commit()
    print("admin code stored")
    if args.generate:
        print(f"code (shown once): {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
