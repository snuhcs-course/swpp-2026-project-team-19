# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-21). Reviewed by Haeul Yang.
"""GET /api/search/bar-names: active bars by part of their name or address (API spec, section 3.11.11)."""

import pytest

from app.models import BarStatus
from tests.factories import make_bar
from tests.sql_support import recorded_statements
from tests.test_search_api import ANY_AUTHORIZATION

URL = "/api/search/bar-names"
ITEM_FIELDS = {"barId", "name", "address", "latitude", "longitude", "hasOwner"}


def find(client, query, headers=None, **params) -> dict:
    response = client.get(URL, params={"query": query, **params}, headers=headers)
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"items", "truncated"}
    return response.json()


def names(body) -> list[str]:
    return [item["name"] for item in body["items"]]


def test_finds_a_bar_by_part_of_its_name_with_every_field(client, db_session):
    bar = make_bar(db_session, "위스키복춘", latitude="37.478225", longitude="126.962940")
    make_bar(db_session, "Seorosang")

    body = find(client, "복춘")

    assert body == {
        "items": [
            {
                "barId": str(bar.id),
                "name": "위스키복춘",
                "address": "위스키복춘 address",
                "latitude": 37.478225,
                "longitude": 126.96294,
                "hasOwner": False,
            }
        ],
        "truncated": False,
    }


def test_finds_a_bar_by_part_of_its_address(client, db_session):
    bar = make_bar(db_session, "Seorosang")
    bar.address = "서울특별시 관악구 관악로14길 10 2층"
    make_bar(db_session, "Malt House")
    db_session.flush()

    assert names(find(client, "관악로14길")) == ["Seorosang"]


@pytest.mark.parametrize("query", ["seorosang", "SEOROSANG", "sEoRo", "  Seorosang  "])
def test_letter_case_and_surrounding_spaces_do_not_matter(client, db_session, query):
    make_bar(db_session, "Seorosang")

    assert names(find(client, query)) == ["Seorosang"]


def test_the_query_is_not_normalized_so_inner_spaces_count(client, db_session):
    # Spec 3.11.11 matches a part of the name as typed; unlike product search (3.10.1) there is
    # no normalization, so "위스키 복춘" does not find "위스키복춘".
    make_bar(db_session, "위스키복춘")

    assert find(client, "위스키 복춘")["items"] == []


@pytest.mark.parametrize(("query", "expected"), [("%", ["100% Malt"]), ("_", ["Bar_One"]), ("\\", [])])
def test_like_wildcards_are_plain_characters(client, db_session, query, expected):
    for name in ("100% Malt", "Bar_One", "Barone"):
        make_bar(db_session, name)

    assert names(find(client, query)) == expected


def test_inactive_bars_are_left_out(client, db_session):
    make_bar(db_session, "Malt Open")
    make_bar(db_session, "Malt Closed", status=BarStatus.INACTIVE)

    assert names(find(client, "Malt")) == ["Malt Open"]


def test_sorted_by_name_then_bar_id(client, db_session):
    twins = [make_bar(db_session, "Malt Twin") for _ in range(2)]
    make_bar(db_session, "Malt B")
    make_bar(db_session, "Malt A")

    body = find(client, "Malt")

    assert names(body) == ["Malt A", "Malt B", "Malt Twin", "Malt Twin"]
    assert [item["barId"] for item in body["items"][2:]] == sorted(str(bar.id) for bar in twins)


def test_limit_and_truncated(client, db_session):
    for i in range(3):
        make_bar(db_session, f"Malt {i}")

    cut = find(client, "Malt", limit=2)
    whole = find(client, "Malt", limit=3)

    assert (names(cut), cut["truncated"]) == (["Malt 0", "Malt 1"], True)
    assert (names(whole), whole["truncated"]) == (["Malt 0", "Malt 1", "Malt 2"], False)


def test_default_limit_is_20(client, db_session):
    for i in range(21):
        make_bar(db_session, f"Malt {i:02}")

    body = find(client, "Malt")

    assert (len(body["items"]), body["truncated"]) == (20, True)
    assert len(find(client, "Malt", limit=50)["items"]) == 21


def test_no_match_is_an_empty_list(client, db_session):
    make_bar(db_session, "Seorosang")

    assert find(client, "없는 바") == {"items": [], "truncated": False}


def test_a_query_of_100_characters_after_trimming_is_accepted(client):
    assert find(client, f"  {'가' * 100}  ")["items"] == []


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, ("query", "MISSING")),
        ({"query": ""}, ("query", "BLANK")),
        ({"query": "   "}, ("query", "BLANK")),
        ({"query": "가" * 101}, ("query", "STRING_TOO_LONG")),
        ({"query": "Malt", "limit": 0}, ("limit", "GREATER_THAN_EQUAL")),
        ({"query": "Malt", "limit": 51}, ("limit", "LESS_THAN_EQUAL")),
        ({"query": "Malt", "limit": "many"}, ("limit", "INT_PARSING")),
    ],
)
def test_invalid_parameters_are_validation_errors(client, params, expected):
    response = client.get(URL, params=params)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert [(field["path"], field["code"]) for field in error["fieldErrors"]] == [expected]


@pytest.mark.parametrize("authorization", ANY_AUTHORIZATION, ids=lambda case: case.__name__)
def test_any_authorization_header_gives_the_guest_result(
    client, db_session, supabase, token_for, monkeypatch, authorization
):
    make_bar(db_session, "Seorosang")
    as_guest = find(client, "Seorosang")

    header = authorization(supabase, token_for, monkeypatch)

    assert find(client, "Seorosang", headers={"Authorization": header}) == as_guest
    assert as_guest["items"]


def test_an_operator_does_not_see_inactive_bars_either(client, db_session, token_for):
    make_bar(db_session, "Malt Closed", status=BarStatus.INACTIVE)

    body = find(client, "Malt", headers={"Authorization": f"Bearer {token_for('operator')}"})

    assert body["items"] == []


def test_one_select_whatever_the_number_of_bars(client, db_session):
    make_bar(db_session, "Malt 0")
    with recorded_statements(db_session) as with_one_bar:
        find(client, "Malt")
    for i in range(1, 10):
        make_bar(db_session, f"Malt {i}")
    with recorded_statements(db_session) as with_ten_bars:
        find(client, "Malt")

    assert len(with_one_bar) == len(with_ten_bars) == 1
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in with_one_bar + with_ten_bars)


def test_every_item_has_exactly_the_spec_fields(client, db_session):
    make_bar(db_session, "Seorosang")

    assert [set(item) for item in find(client, "Seorosang")["items"]] == [ITEM_FIELDS]
