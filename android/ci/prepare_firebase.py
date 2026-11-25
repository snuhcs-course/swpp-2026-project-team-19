"""Materialize optional Android Firebase configuration without logging its contents."""
import json
import os
from pathlib import Path
import sys


def prepare(raw: str, destination: Path) -> bool:
    if not raw.strip():
        return False
    try:
        config = json.loads(raw)
        clients = config.get("client", []) if isinstance(config, dict) else []
        matches = any(
            isinstance(client, dict) and
            client.get("client_info", {}).get("android_client_info", {}).get("package_name")
            == "com.zerotoone.bottlemap"
            for client in clients
        )
        if not matches:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid Firebase Android configuration") from None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(raw, encoding="utf-8")
    destination.chmod(0o600)
    return True


def main() -> int:
    destination = Path(__file__).resolve().parents[1] / "app" / "google-services.json"
    try:
        configured = prepare(os.environ.get("BOTTLEMAP_GOOGLE_SERVICES_JSON", ""), destination)
    except ValueError:
        print("Invalid Firebase Android configuration", file=sys.stderr)
        return 1
    print("Firebase configuration provided" if configured else
          "Using existing local Firebase configuration" if destination.is_file() else
          "Firebase configuration absent; using NoOpTelemetry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
