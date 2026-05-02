import uuid

import pytest

from backend.models import Application, User
from backend.services.search.indexer import index_record, search_user_documents
from tests.conftest import AUTH_HEADER, TEST_USER_ID, make_auth_header


@pytest.mark.asyncio
async def test_search_documents_are_strictly_user_scoped(db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="other-search", email="other-search@apptrail.test", name="Other"))
    user_app = Application(
        user_id=TEST_USER_ID,
        company="TraceBank",
        role_title="Assistant Search Data Scientist",
        description_text="Build ranking and NLP models.",
    )
    other_app = Application(
        user_id=other_user_id,
        company="OtherBank",
        role_title="Assistant Search Data Scientist",
        description_text="This row must never appear for the first user.",
    )
    db_session.add_all([user_app, other_app])
    await db_session.flush()
    await index_record(db_session, user_app)
    await index_record(db_session, other_app)
    await db_session.commit()

    results = await search_user_documents(db_session, user_id=TEST_USER_ID, query="assistant search", limit=10)

    assert [result.source_id for result in results] == [user_app.id]
    assert all(result.metadata["company"] == "TraceBank" for result in results)


@pytest.mark.asyncio
async def test_search_documents_endpoint_returns_only_authenticated_users_records(client, db_session):
    other_user_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    db_session.add(User(id=other_user_id, google_id="other-search-api", email="other-search-api@apptrail.test", name="Other"))
    user_app = Application(
        user_id=TEST_USER_ID,
        company="TraceBank",
        role_title="NLP Analyst",
        description_text="Assistant search analytics.",
    )
    other_app = Application(
        user_id=other_user_id,
        company="OtherBank",
        role_title="NLP Analyst",
        description_text="Assistant search analytics.",
    )
    db_session.add_all([user_app, other_app])
    await db_session.flush()
    await index_record(db_session, user_app)
    await index_record(db_session, other_app)
    await db_session.commit()

    response = await client.get("/api/search/documents?q=assistant", headers=AUTH_HEADER)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 1
    assert payload["results"][0]["source_id"] == str(user_app.id)
    assert payload["results"][0]["metadata"]["company"] == "TraceBank"

    other_response = await client.get(
        "/api/search/documents?q=assistant",
        headers=make_auth_header(other_user_id, email="other-search-api@apptrail.test"),
    )
    assert other_response.status_code == 200
    assert other_response.json()["results"][0]["source_id"] == str(other_app.id)


@pytest.mark.asyncio
async def test_search_documents_endpoint_requires_dashboard_auth(client, db_session):
    response = await client.get("/api/search/documents?q=assistant", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
