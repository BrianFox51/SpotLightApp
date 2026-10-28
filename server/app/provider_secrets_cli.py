"""SSH-only operator commands for encrypted, versioned provider secrets.

Secrets are read with getpass and are never accepted as command-line arguments,
which avoids shell-history and process-list exposure.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func, select

from app import models  # ensure model mappings are registered before metadata use
from app.database import Base, SessionLocal, engine
from app.models import Account, ProviderSecretVersion
from app.provider_secrets import (
    ProviderSecretError,
    SUPPORTED_PROVIDERS,
    clear_provider_secret,
    normalize_provider,
    provider_secret_history,
    provider_secret_status,
    restore_provider_secret,
    set_provider_secret,
)


def _actor(db, username: str) -> Account:
    account = db.scalar(select(Account).where(func.lower(Account.username) == username.strip().lower()))
    if account is None or not account.is_active or account.role != "admin":
        raise ProviderSecretError("An active Spotlight admin account is required for this operation.")
    return account


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage encrypted Spotlight provider-key history over SSH.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Show configured state and version numbers, never key values")
    for name in ("history", "set", "clear"):
        command = commands.add_parser(name)
        command.add_argument("provider", choices=sorted(SUPPORTED_PROVIDERS))
    restore = commands.add_parser("restore", help="Restore a prior version as a new version")
    restore.add_argument("provider", choices=sorted(SUPPORTED_PROVIDERS))
    restore.add_argument("version", type=int)
    args = parser.parse_args()

    try:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            if args.command == "status":
                for item in provider_secret_status(db):
                    version = item["current_version"] or "—"
                    count = item["versions"]
                    state = "configured" if item["configured"] else "not set"
                    print(f"{item['provider']:<24} {state:<12} current={version} history={count}")
                return 0

            provider = normalize_provider(args.provider)
            if args.command == "history":
                for row in provider_secret_history(db, provider):
                    state = "configured" if row["configured"] else "cleared"
                    fingerprint = row["fingerprint"] or "—"
                    actor_account = db.get(Account, row["actor_id"]) if row["actor_id"] else None
                    actor = actor_account.username if actor_account else "deleted account"
                    print(f"v{row['version']}  {state:<10} {row['created_at']}  fingerprint={fingerprint}  actor={actor}  {row['change_note']}")
                return 0

            actor_name = input("Admin username for audit record: ").strip()
            actor = _actor(db, actor_name)
            if args.command == "set":
                first = getpass.getpass("New provider key (hidden): ")
                second = getpass.getpass("Confirm provider key (hidden): ")
                if not first or first != second:
                    raise ProviderSecretError("Values were blank or did not match; no change was made.")
                note = input("Change note (optional): ").strip()
                row = set_provider_secret(db, provider, first, actor, note)
            elif args.command == "clear":
                note = input("Reason for clearing this key: ").strip()
                if not note:
                    raise ProviderSecretError("A reason is required to clear a key.")
                row = clear_provider_secret(db, provider, actor, note)
            else:
                note = input(f"Reason for restoring version {args.version}: ").strip()
                row = restore_provider_secret(db, provider, args.version, actor, note)
            state = "cleared" if row.ciphertext is None else "saved"
            print(f"{provider} {state} as version {row.version}; value was not displayed.")
            return 0
    except (ProviderSecretError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
