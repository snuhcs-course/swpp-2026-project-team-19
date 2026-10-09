# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #11). Reviewed by Haeul Yang.
from uuid import uuid4

from sqlalchemy import func, select

from app.models import ExtractedItem, ImportStatus, MenuImage, MenuImport, MenuImportChange, ResolutionCandidate
from scripts.reset_menu_imports import delete_imports, find_imports
from tests.factories import make_bar, make_brand, make_product

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


def upload(client, bar, headers, filename="sample.jpg"):
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        data={"mode": "full_replace"},
        files=[("images", (filename, JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    return response.json()["menuImportId"]


def count(db_session, model):
    return db_session.scalar(select(func.count()).select_from(model))


def stored_files(storage):
    return sorted(str(p.relative_to(storage.root)) for p in storage.root.rglob("*") if p.is_file())


def test_reset_deletes_a_bars_imports_rows_and_files(client, db_session, image_storage, token_for):
    operator = {"Authorization": f"Bearer {token_for('operator')}"}
    brand = make_brand(db_session, "Glenfiddich")
    make_product(db_session, brand, "Glenfiddich 12", aliases=("글렌피딕 12년",), age_years=12)
    target, other = make_bar(db_session, "Target"), make_bar(db_session, "Other")
    target_import = upload(client, target, operator)
    other_import = upload(client, other, operator, filename="fail.jpg")
    assert count(db_session, ResolutionCandidate) > 0 and count(db_session, MenuImportChange) > 0

    deletable, applied = find_imports(db_session, bar_id=target.id)
    files = delete_imports(db_session, image_storage, deletable)

    assert ([str(i.id) for i in deletable], applied, files) == ([target_import], [], 1)
    remaining = db_session.scalars(select(MenuImport.id)).all()
    assert [str(i) for i in remaining] == [other_import]
    # Only the other bar's rows and file are left.
    assert count(db_session, MenuImage) == 1
    assert count(db_session, ExtractedItem) == count(db_session, ResolutionCandidate) == count(db_session, MenuImportChange) == 0
    assert stored_files(image_storage) == [f"menus/{other.id}/{other_import}/page-1.jpg"]
    # The bar accepts a new upload again.
    upload(client, target, operator)


def test_applied_imports_are_kept(client, db_session, image_storage, token_for):
    operator = {"Authorization": f"Bearer {token_for('operator')}"}
    bar = make_bar(db_session)
    applied_id = upload(client, bar, operator)
    db_session.get(MenuImport, applied_id).status = ImportStatus.APPLIED
    db_session.flush()
    pending_id = upload(client, bar, operator)

    deletable, applied = find_imports(db_session)
    delete_imports(db_session, image_storage, deletable)

    assert [str(i.id) for i in deletable] == [pending_id]
    assert [str(i.id) for i in applied] == [applied_id]
    assert [str(i) for i in db_session.scalars(select(MenuImport.id))] == [applied_id]


def test_single_import_scope_and_nothing_to_delete(client, db_session, image_storage, token_for):
    operator = {"Authorization": f"Bearer {token_for('operator')}"}
    first, second = make_bar(db_session, "A"), make_bar(db_session, "B")
    keep = upload(client, first, operator)
    drop = upload(client, second, operator)

    deletable, _ = find_imports(db_session, import_id=drop)
    delete_imports(db_session, image_storage, deletable)

    assert [str(i) for i in db_session.scalars(select(MenuImport.id))] == [keep]
    assert delete_imports(db_session, image_storage, []) == 0
