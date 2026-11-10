"""Rotate the keys of the stored business registration numbers (backend/DEPLOY.md, "Business number keys").

Encryption key. The API may keep running.
  1. Put the new key first in BUSINESS_NUMBER_ENCRYPTION_KEYS, keep the old one after it, and restart.
  2. Re-encrypt every row with the first key:
       uv run --env-file .env python scripts/rotate_business_number_keys.py --apply
  3. Remove the old key from the list and restart.

Lookup (HMAC) key. Stop the API first: a request between the run and the restart would compare
numbers under the wrong key and could let a pending duplicate through.
  1. sudo systemctl stop bottlemap-api
  2. Recompute every lookup value with the new key, typed without echoing it into an environment variable
     (not an argument, so it stays out of the shell history and the process list):
       read -rs NEW_BUSINESS_NUMBER_HMAC_KEY && export NEW_BUSINESS_NUMBER_HMAC_KEY
       uv run --env-file .env python scripts/rotate_business_number_keys.py --hmac --apply
  3. Put the new key in BUSINESS_NUMBER_HMAC_KEY, unset NEW_BUSINESS_NUMBER_HMAC_KEY, and start the API.

Every run is one transaction. Without --apply the whole run is done and then rolled back, and only the
number of rows is printed. Nothing prints a business number or a key.
"""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.business_number_crypto import (  # noqa: E402
    BusinessNumberCipher,
    BusinessNumberDecryptError,
    BusinessNumberKeyError,
    get_business_number_cipher,
)
from app.db.session import get_engine  # noqa: E402
from app.models import BarOwnerApplication  # noqa: E402

NEW_HMAC_KEY_ENV = "NEW_BUSINESS_NUMBER_HMAC_KEY"


def _applications(session: Session) -> list[BarOwnerApplication]:
    # Locked, so an application changed meanwhile waits for this run instead of being overwritten.
    return list(session.scalars(select(BarOwnerApplication).order_by(BarOwnerApplication.id).with_for_update()))


def reencrypt(session: Session, cipher: BusinessNumberCipher) -> int:
    """Encrypt every stored number again with the cipher's first key; the number of rows."""
    applications = _applications(session)
    for application in applications:
        application.business_registration_number_ciphertext = cipher.rotate(
            application.business_registration_number_ciphertext
        )
    session.flush()
    return len(applications)


def recompute_lookups(session: Session, cipher: BusinessNumberCipher, new_cipher: BusinessNumberCipher) -> int:
    """Replace every lookup value with one made by `new_cipher`'s key; the number of rows."""
    applications = _applications(session)
    for application in applications:
        number = cipher.decrypt(application.business_registration_number_ciphertext)
        application.business_registration_number_hmac = new_cipher.lookup(number)
    session.flush()
    return len(applications)


def run(session: Session, *, hmac: bool, apply: bool, new_hmac_key: str | None = None) -> str:
    """Do the rotation in the session; commit with `apply`, else roll it back. The line to print."""
    cipher = get_business_number_cipher()
    if hmac:
        if not new_hmac_key or not new_hmac_key.strip():
            raise BusinessNumberKeyError(f"{NEW_HMAC_KEY_ENV} is not set")
        new_cipher = cipher.with_lookup_key(new_hmac_key, NEW_HMAC_KEY_ENV)
    with session.begin_nested() as change:
        count = recompute_lookups(session, cipher, new_cipher) if hmac else reencrypt(session, cipher)
        if not apply:
            change.rollback()
    what = "lookup values recomputed" if hmac else "numbers re-encrypted with the first key"
    if not apply:
        return f"dry run: {count} {what} and rolled back. Re-run with --apply."
    session.commit()
    if hmac:
        return f"{count} {what}. Now put the new key in BUSINESS_NUMBER_HMAC_KEY and start the API."
    return f"{count} {what}. The old key can be removed from BUSINESS_NUMBER_ENCRYPTION_KEYS."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hmac", action="store_true", help=f"recompute lookup values with {NEW_HMAC_KEY_ENV}")
    parser.add_argument("--apply", action="store_true", help="commit (default: run and roll back)")
    args = parser.parse_args()

    try:
        with Session(get_engine()) as session:
            print(run(session, hmac=args.hmac, apply=args.apply, new_hmac_key=os.getenv(NEW_HMAC_KEY_ENV)))
    except (BusinessNumberKeyError, BusinessNumberDecryptError) as error:
        sys.exit(f"error: {error}")


if __name__ == "__main__":
    main()
