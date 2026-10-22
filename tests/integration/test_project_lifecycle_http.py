"""Opt-in real HTTP checks against the disposable stage0 API, without dependency overrides."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def api() -> Iterator[httpx.Client]:
    base = os.environ.get("PROJECT_LIFECYCLE_TEST_API_URL")
    password = os.environ.get("PROJECT_LIFECYCLE_TEST_PASSWORD")
    if not base or not password:
        pytest.skip("Requires the disposable stage0 API and its private test password")
    if base != "http://127.0.0.1:18002/api/v1":
        pytest.fail("Refusing to run lifecycle writes against a different API")
    with httpx.Client(base_url=base, timeout=30) as client:
        login = client.post("/auth/login", data={"username": "stage0_owner", "password": password})
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        yield client


def test_concurrent_merge_patches_keep_independent_nested_keys(api: httpx.Client) -> None:
    project = api.post("/projects", json={"name": "concurrent-" + uuid4().hex[:8]}).json()
    endpoint = f"/projects/{project['id']}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(
            lambda key: api.patch(endpoint, json={"settings": {"parallel": {key: True}}}),
            ["first", "second"],
        ))
    assert [r.status_code for r in responses] == [200, 200]
    assert api.get(endpoint).json()["settings"]["parallel"] == {"first": True, "second": True}


def test_invalid_combined_patch_never_partially_commits(api: httpx.Client) -> None:
    project = api.post("/projects", json={"name": "atomic-" + uuid4().hex[:8]}).json()
    endpoint = f"/projects/{project['id']}"
    response = api.patch(endpoint, json={
        "name": "must-not-commit", "settings": {"research_mode": {"enabled": "invalid"}},
    })
    assert response.status_code == 422
    after = api.get(endpoint).json()
    assert after["name"] == project["name"] and after["slug"] == project["slug"]


def test_tombstone_reserves_identity_across_explicit_sync(api: httpx.Client) -> None:
    name = "deleted-" + uuid4().hex[:8]
    project = api.post("/projects", json={"name": name}).json()
    endpoint = f"/projects/{project['id']}"
    assert api.delete(endpoint).status_code == 204
    for _ in range(3):
        assert all(p["id"] != project["id"] for p in api.get("/projects").json())
        assert api.get("/projects/count").status_code == 200
    sync = api.post("/projects/sync-from-disk")
    assert sync.status_code == 200 and sync.json()["skipped_deleted"] >= 1
    assert api.get(endpoint).status_code == 404
    assert api.post("/projects", json={"name": name}).status_code == 409
