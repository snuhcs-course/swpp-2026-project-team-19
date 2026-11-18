"""Print the API's OpenAPI document as JSON, without starting the server or touching the database.

The owner web generates its API types from this (`npm run gen:api` in owner-web/):

    uv run python scripts/export_openapi.py > openapi.json
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def main() -> None:
    json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
