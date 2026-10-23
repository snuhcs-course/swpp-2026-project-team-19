"""Where a Supabase user's role comes from (API spec, section 3.1.4): `users.user_type`, never the token.

Which routes need an operator is unchanged here; these tests only check the source of the role.
"""

from sqlalchemy import select

from app.models import BarStatus, User, UserType
from tests.factories import make_bar

SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"


def brands(client, token):
    return client.get("/api/catalog/brands", params={"query": "x"}, headers={"Authorization": f"Bearer {token}"})


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


def add_user(db_session, subject, user_type):
    db_session.add(User(auth_subject=subject, user_type=user_type))
    db_session.flush()


def test_user_without_row_is_a_customer(client, supabase, db_session):
    response = brands(client, supabase.token(sub=SUBJECT))

    assert error_of(response) == (403, "FORBIDDEN")
    # Only GET /api/me creates users.
    assert db_session.scalar(select(User).where(User.auth_subject == SUBJECT)) is None


def test_customer_cannot_call_operator_api(client, supabase, db_session):
    add_user(db_session, SUBJECT, UserType.CUSTOMER)

    assert error_of(brands(client, supabase.token(sub=SUBJECT))) == (403, "FORBIDDEN")


def test_database_operator_can_call_operator_api(client, supabase, db_session):
    add_user(db_session, SUBJECT, UserType.OPERATOR)

    assert brands(client, supabase.token(sub=SUBJECT)).status_code == 200


def test_role_change_applies_to_the_next_request(client, supabase, db_session):
    add_user(db_session, SUBJECT, UserType.CUSTOMER)
    token = supabase.token(sub=SUBJECT)
    before = brands(client, token)

    db_session.scalars(select(User).where(User.auth_subject == SUBJECT)).one().user_type = UserType.OPERATOR
    db_session.flush()

    assert (before.status_code, brands(client, token).status_code) == (403, 200)


def test_token_claims_never_grant_a_role(client, supabase, db_session):
    add_user(db_session, SUBJECT, UserType.CUSTOMER)
    token = supabase.token(
        sub=SUBJECT,
        user_type="operator",
        role="service_role",
        user_metadata={"name": "홍길동", "user_type": "operator"},
        app_metadata={"user_type": "operator"},
    )

    assert error_of(brands(client, token)) == (403, "FORBIDDEN")


def test_bar_menu_uses_the_database_role(client, supabase, db_session):
    bar = make_bar(db_session, status=BarStatus.INACTIVE)
    add_user(db_session, "operator-subject", UserType.OPERATOR)
    add_user(db_session, "customer-subject", UserType.CUSTOMER)

    def menu(subject):
        token = supabase.token(sub=subject)
        return client.get(f"/api/bars/{bar.id}/menu", headers={"Authorization": f"Bearer {token}"})

    assert menu("operator-subject").status_code == 200
    assert error_of(menu("customer-subject")) == (404, "BAR_NOT_FOUND")
