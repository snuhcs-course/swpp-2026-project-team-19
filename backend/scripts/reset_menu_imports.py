"""Delete menu imports and their stored photos, for local development and testing.

Until review submission exists, an import stays in ready_for_review and blocks the next
upload for its bar (409 ACTIVE_IMPORT_EXISTS). This removes such imports with all their
rows (images, extraction runs, items, options, candidates, draft changes) and image files.

Imports in `applied` are never deleted: the published menu board, its options, and products
created during that review refer to them.

Without `--apply` it only lists what would be deleted.

    cd backend
    uv run --env-file .env python scripts/reset_menu_imports.py --bar <barId>
    uv run --env-file .env python scripts/reset_menu_imports.py --bar <barId> --apply
    uv run --env-file .env python scripts/reset_menu_imports.py --import <menuImportId> --apply
    uv run --env-file .env python scripts/reset_menu_imports.py --all --apply
"""

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.adapters.storage import ImageStorage  # noqa: E402
from app.api.deps import get_image_storage  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.models import (  # noqa: E402
    Bar,
    ExtractedItem,
    ExtractedOption,
    ExtractionRun,
    ImportStatus,
    MenuImage,
    MenuImport,
    MenuImportChange,
    ResolutionCandidate,
)


def find_imports(
    session: Session, *, bar_id: UUID | None = None, import_id: UUID | None = None
) -> tuple[list[MenuImport], list[MenuImport]]:
    """(deletable, skipped applied) imports for one bar, one import, or everything when both are None."""
    query = select(MenuImport).order_by(MenuImport.created_at)
    if bar_id is not None:
        query = query.where(MenuImport.bar_id == bar_id)
    if import_id is not None:
        query = query.where(MenuImport.id == import_id)
    imports = list(session.scalars(query))
    deletable = [i for i in imports if i.status != ImportStatus.APPLIED]
    applied = [i for i in imports if i.status == ImportStatus.APPLIED]
    return deletable, applied


def delete_imports(session: Session, storage: ImageStorage, imports: list[MenuImport]) -> int:
    """Delete the imports' rows children first, then their image files. Returns the number of files."""
    if not imports:
        return 0
    keys = delete_import_rows(session, [i.id for i in imports])
    # Files go after the rows so a failed delete never leaves rows pointing at missing files.
    for key in keys:
        storage.delete(key)
    return len(keys)


def delete_import_rows(session: Session, import_ids: list[UUID]) -> list[str]:
    """Delete the imports and every row below them, children first. Returns their image keys;
    the caller deletes the files."""
    keys = list(session.scalars(select(MenuImage.storage_key).where(MenuImage.menu_import_id.in_(import_ids))))
    image_ids = select(MenuImage.id).where(MenuImage.menu_import_id.in_(import_ids))
    run_ids = select(ExtractionRun.id).where(ExtractionRun.menu_image_id.in_(image_ids))
    item_ids = select(ExtractedItem.id).where(ExtractedItem.extraction_run_id.in_(run_ids))

    session.execute(delete(MenuImportChange).where(MenuImportChange.menu_import_id.in_(import_ids)))
    session.execute(delete(ResolutionCandidate).where(ResolutionCandidate.extracted_item_id.in_(item_ids)))
    session.execute(delete(ExtractedOption).where(ExtractedOption.extracted_item_id.in_(item_ids)))
    session.execute(delete(ExtractedItem).where(ExtractedItem.id.in_(item_ids)))
    session.execute(delete(ExtractionRun).where(ExtractionRun.id.in_(run_ids)))
    session.execute(delete(MenuImage).where(MenuImage.menu_import_id.in_(import_ids)))
    session.execute(delete(MenuImport).where(MenuImport.id.in_(import_ids)))
    session.flush()
    return keys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--bar", type=UUID, metavar="BAR_ID", help="imports of this bar")
    scope.add_argument("--import", dest="import_id", type=UUID, metavar="MENU_IMPORT_ID", help="this import only")
    scope.add_argument("--all", action="store_true", help="imports of every bar")
    parser.add_argument("--apply", action="store_true", help="delete (default: list only)")
    args = parser.parse_args()

    with Session(get_engine()) as session:
        deletable, applied = find_imports(session, bar_id=args.bar, import_id=args.import_id)
        bar_names = dict(session.execute(select(Bar.id, Bar.name)).all())
        for menu_import in deletable:
            print(
                f"{'delete' if args.apply else 'would delete'} {menu_import.id}  "
                f"{bar_names.get(menu_import.bar_id, menu_import.bar_id)}  {menu_import.status.value}  "
                f"{menu_import.created_at:%Y-%m-%d %H:%M}"
            )
        for menu_import in applied:
            print(f"skip {menu_import.id}  {bar_names.get(menu_import.bar_id)}  applied (kept)")
        if not deletable:
            print("nothing to delete")
            return
        if not args.apply:
            print(f"\ndry run: {len(deletable)} import(s) would be deleted. Re-run with --apply.")
            return
        files = delete_imports(session, get_image_storage(), deletable)
        session.commit()
        print(f"\ndeleted {len(deletable)} import(s) and {files} image file(s)")


if __name__ == "__main__":
    main()
