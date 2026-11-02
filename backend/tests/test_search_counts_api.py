"""Customer search counts its searches per Seoul date (API spec 3.10.6)."""

import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.models import ProductSearchCount, SearchSource, UnmatchedSearchQuery
from app.services.request_limits import kst_date
from app.services.search_counts import (
    MAX_NEW_UNMATCHED_QUERIES_PER_DAY,
    _count_unmatched,
    is_storable_unmatched_query,
)
from tests.factories import make_bar, make_brand, make_product, publish_menu
from tests.sql_support import recorded_statements


@pytest.fixture
def glenfiddich(db_session):
    brand = make_brand(db_session, "Glenfiddich", aliases=("글렌피딕",))
    return {
        age: make_product(db_session, brand, f"Glenfiddich {age}", aliases=(f"글렌피딕 {age}년",), age_years=age)
        for age in (12, 15)
    }


def today() -> date:
    return kst_date(datetime.now(timezone.utc))


def search(client, **params) -> dict:
    response = client.get("/api/search/bars", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def product_counts(db_session) -> set[tuple]:
    rows = db_session.scalars(select(ProductSearchCount))
    return {(row.search_date, row.product_id, row.source, row.search_count) for row in rows}


def unmatched_counts(db_session) -> set[tuple]:
    rows = db_session.scalars(select(UnmatchedSearchQuery))
    return {(row.search_date, row.normalized_query, row.search_count) for row in rows}


def test_a_search_for_one_product_counts_per_product_and_source(client, db_session, glenfiddich):
    twelve = glenfiddich[12].id
    search(client, query="글렌피딕 12년")
    search(client, query="Glenfiddich 12", source="input")
    search(client, query="글렌피딕 12년", source="recent")
    search(client, productId=str(twelve), source="popular")
    search(client, productId=str(twelve), source="popular")

    assert product_counts(db_session) == {
        (today(), twelve, SearchSource.INPUT, 2),
        (today(), twelve, SearchSource.RECENT, 1),
        (today(), twelve, SearchSource.POPULAR, 2),
    }
    assert unmatched_counts(db_session) == set()


def test_a_product_sold_nowhere_is_counted_too(client, db_session, glenfiddich):
    body = search(client, query="글렌피딕 15년")

    assert body["items"] == []
    assert product_counts(db_session) == {(today(), glenfiddich[15].id, SearchSource.INPUT, 1)}


def test_searches_for_several_products_are_not_counted(client, db_session, glenfiddich):
    # Two products share an exact alias.
    make_product(db_session, make_brand(db_session, "Twin"), "Twin A", aliases=("쌍둥이",))
    make_product(db_session, make_brand(db_session, "Twin B"), "Twin B", aliases=("쌍둥이",))
    publish_menu(db_session, make_bar(db_session), [(glenfiddich[12], "12", [(None, 30, 1)])])

    assert search(client, query="글렌피딕")["matchType"] == "brand"
    assert search(client, query="피딕")["matchType"] == "partial"
    twins = search(client, query="쌍둥이")
    assert (twins["matchType"], len(twins["matchedProducts"])) == ("alias_exact", 2)
    assert product_counts(db_session) == unmatched_counts(db_session) == set()


def test_a_product_id_search_that_finds_nothing_is_not_counted(client, db_session):
    retired = make_product(db_session, make_brand(db_session, "Port Ellen"), "Port Ellen", is_active=False)

    search(client, productId=str(retired.id))
    search(client, productId="44444444-4444-4444-8444-444444444444")

    assert product_counts(db_session) == unmatched_counts(db_session) == set()


def test_validation_errors_are_not_counted(client, db_session, glenfiddich):
    for params in ({"query": "글렌피딕 12년", "lat": 37.5}, {"query": "!!!"}, {"query": "없는 위스키", "limit": 0}):
        assert client.get("/api/search/bars", params=params).status_code == 422

    assert product_counts(db_session) == unmatched_counts(db_session) == set()


def test_an_unmatched_query_is_counted_normalized(client, db_session):
    search(client, query="  카발란 솔리스트  ")
    search(client, query="카발란솔리스트")
    search(client, query="KAVALAN!!")

    assert unmatched_counts(db_session) == {(today(), "카발란솔리스트", 2), (today(), "kavalan", 1)}
    assert product_counts(db_session) == set()


@pytest.mark.parametrize(
    "query",
    [
        "someone@example.com",
        "글렌 @",
        "010-1234-5678",
        "010.1234.5678",
        "01012345678",
        "1234567",
        "12-34-56-78",
        "전화 02 123 4567",  # spaces are dropped by the normalization, leaving 7 digits in a row
    ],
)
def test_emails_and_phone_numbers_are_not_stored(client, db_session, query):
    assert search(client, query=query)["matchType"] == "none"

    assert unmatched_counts(db_session) == set()


@pytest.mark.parametrize("query", ["123456", "1990 빈티지", "글렌 12-34", "No. 123 456"])
def test_short_numbers_are_stored(client, db_session, query):
    search(client, query=query)

    assert len(unmatched_counts(db_session)) == 1


def test_a_normalized_query_longer_than_the_column_is_not_stored():
    # NFKC can make a query longer than its 100 characters: "㍿" becomes "株式会社".
    assert is_storable_unmatched_query("㍿" * 51, "株式会社" * 51) is False
    assert is_storable_unmatched_query("㍿" * 50, "株式会社" * 50) is True


def add_unmatched(db_session, day: date, count: int) -> None:
    db_session.add_all(
        UnmatchedSearchQuery(search_date=day, normalized_query=f"q{i}", search_count=1) for i in range(count)
    )
    db_session.flush()


def test_at_most_1000_new_unmatched_queries_a_day(client, db_session):
    add_unmatched(db_session, today(), MAX_NEW_UNMATCHED_QUERIES_PER_DAY - 1)
    add_unmatched(db_session, today() - timedelta(days=1), 5)  # other days do not count

    search(client, query="새검색어")
    search(client, query="또다른검색어")  # the 1,001st
    search(client, query="q0")  # existing queries still count
    search(client, query="새검색어")

    rows = {row[1]: row[2] for row in unmatched_counts(db_session) if row[0] == today()}
    assert len(rows) == MAX_NEW_UNMATCHED_QUERIES_PER_DAY
    assert (rows["새검색어"], rows["q0"], "또다른검색어" in rows) == (2, 2, False)


def test_a_query_created_while_waiting_for_the_cap_lock_still_counts(db_session, monkeypatch):
    add_unmatched(db_session, today(), MAX_NEW_UNMATCHED_QUERIES_PER_DAY - 1)
    execute = db_session.execute

    def concurrent_search_wins(statement, *args, **kwargs):
        result = execute(statement, *args, **kwargs)
        if "pg_advisory_xact_lock" in str(statement):
            # Another search created the 1,000th row, this query, before we got the lock.
            db_session.add(UnmatchedSearchQuery(search_date=today(), normalized_query="새검색어", search_count=1))
            db_session.flush()
        return result

    monkeypatch.setattr(db_session, "execute", concurrent_search_wins)
    _count_unmatched(db_session, today(), "새검색어")

    rows = {row[1]: row[2] for row in unmatched_counts(db_session) if row[0] == today()}
    assert (len(rows), rows["새검색어"]) == (MAX_NEW_UNMATCHED_QUERIES_PER_DAY, 2)


def test_only_a_new_unmatched_query_takes_the_daily_cap_lock(client, db_session):
    with recorded_statements(db_session) as first:
        search(client, query="새검색어")
    with recorded_statements(db_session) as again:
        search(client, query="새검색어")

    assert any("pg_advisory_xact_lock" in statement for statement in first)
    assert not any("pg_advisory_xact_lock" in statement for statement in again)


def test_a_repeated_search_only_raises_its_row(client, db_session, glenfiddich):
    search(client, query="글렌피딕 12년")
    with recorded_statements(db_session) as statements:
        search(client, query="글렌피딕 12년")

    writes = [s for s in statements if "product_search_counts" in s]
    assert len(writes) == 1 and writes[0].lstrip().upper().startswith("UPDATE")


def test_counts_use_the_seoul_date(client, db_session, glenfiddich, monkeypatch):
    # 15:30 UTC is 00:30 the next day in Seoul.
    class LateEvening(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 2, 15, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr("app.services.search.datetime", LateEvening)
    search(client, query="글렌피딕 12년")
    search(client, query="없는 위스키")

    assert product_counts(db_session) == {(date(2026, 11, 3), glenfiddich[12].id, SearchSource.INPUT, 1)}
    assert unmatched_counts(db_session) == {(date(2026, 11, 3), "없는위스키", 1)}


def test_creating_a_row_deletes_the_rows_past_their_retention(client, db_session, glenfiddich):
    fifteen = glenfiddich[15].id
    for days_ago in (89, 90):
        db_session.add(
            ProductSearchCount(
                search_date=today() - timedelta(days=days_ago),
                product_id=fifteen,
                source=SearchSource.INPUT,
                search_count=5,
            )
        )
        db_session.add(
            UnmatchedSearchQuery(search_date=today() - timedelta(days=days_ago - 60), normalized_query="old", search_count=5)
        )
    db_session.flush()

    search(client, query="글렌피딕 12년")
    search(client, query="없는 위스키")

    assert {row[0] for row in product_counts(db_session) if row[1] == fifteen} == {today() - timedelta(days=89)}
    assert {row[0] for row in unmatched_counts(db_session) if row[1] == "old"} == {today() - timedelta(days=29)}


def test_a_failed_count_still_answers_the_search(client, db_session, glenfiddich, monkeypatch, caplog):
    publish_menu(db_session, make_bar(db_session), [(glenfiddich[12], "12", [(None, 30, 1)])])
    expected = search(client, query="글렌피딕 12년")
    db_session.execute(ProductSearchCount.__table__.delete())
    db_session.commit()  # the failed count rolls back the request's transaction, not the test's rows

    def database_down(*args, **kwargs):
        raise OperationalError("DELETE FROM product_search_counts", {}, Exception("connection lost"))

    # Fails after the row was inserted, so the insert must be rolled back too.
    monkeypatch.setattr("app.services.search_counts.delete", database_down)
    with caplog.at_level(logging.ERROR, logger="app.services.search_counts"):
        body = search(client, query="글렌피딕 12년")

    assert body == expected
    assert product_counts(db_session) == set()
    assert "Could not record a search count" in caplog.text
    assert "글렌피딕" not in caplog.text


def test_a_token_does_not_change_what_is_counted(client, db_session, glenfiddich, token_for):
    operator = {"Authorization": f"Bearer {token_for('operator')}"}
    client.get("/api/search/bars", params={"query": "글렌피딕 12년"}, headers=operator)
    search(client, query="글렌피딕 12년")

    assert product_counts(db_session) == {(today(), glenfiddich[12].id, SearchSource.INPUT, 2)}
