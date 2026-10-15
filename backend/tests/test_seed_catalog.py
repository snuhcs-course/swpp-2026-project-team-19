# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-15). Reviewed by Haeul Yang.
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Bar, Brand, BrandAlias, Product
from scripts.seed_catalog import load
from tests.factories import make_brand


def seeds(brand_name: str = "Seed Brand") -> tuple[dict, dict]:
    brand_id = str(uuid4())
    catalog = {
        "brands": [
            {
                "id": brand_id,
                "canonical_name": brand_name,
                "aliases": [{"id": str(uuid4()), "alias_text": brand_name, "language_code": "en"}],
            }
        ],
        "products": [
            {
                "id": str(uuid4()),
                "brand_id": brand_id,
                "category": "whisky",
                "display_name": f"{brand_name} 12",
                "age_years": 12,
                "edition_name": None,
                "abv": None,
                "aliases": [],
            }
        ],
    }
    bars = {
        "bars": [
            {
                "id": str(uuid4()),
                "name": "Seed Bar",
                "address": "서울특별시 관악구 관악로 1",
                "latitude": 37.478,
                "longitude": 126.951,
                "phone": None,
                "status": "active",
            }
        ]
    }
    return catalog, bars


def counts(session) -> tuple[int, ...]:
    return tuple(session.scalar(select(func.count()).select_from(model)) for model in (Bar, Brand, BrandAlias, Product))


def test_dry_run_prints_the_counts_and_changes_nothing(db_session, capsys):
    before = counts(db_session)

    load(db_session.connection(), *seeds(), dry_run=True)

    assert counts(db_session) == before
    lines = capsys.readouterr().out.splitlines()
    assert any(line.startswith("brands ") and line.endswith("inserted 1, updated 0") for line in lines)
    assert lines[-1].startswith("dry run: rolled back")


def test_apply_keeps_the_rows(db_session):
    before = counts(db_session)

    load(db_session.connection(), *seeds(), dry_run=False)

    assert counts(db_session) == tuple(n + 1 for n in before)


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_load_that_fails_changes_nothing_and_leaves_the_connection_usable(db_session, dry_run):
    # Another brand already has the name, under a different id: brands.canonical_name is unique.
    make_brand(db_session, "Taken Brand")
    before = counts(db_session)

    with pytest.raises(IntegrityError):
        load(db_session.connection(), *seeds("Taken Brand"), dry_run=dry_run)

    assert counts(db_session) == before
