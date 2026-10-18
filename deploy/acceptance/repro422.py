"""Reproduce the UI export create payload verbatim to capture the 422 body."""

import json
import uuid

import httpx

with open("/tmp/e2e-out/context.json") as context_file:
    ctx = json.load(context_file)
base = "http://api:8000/api/v1"
c = httpx.Client(base_url=base, timeout=30)
r = c.post("/auth/login", data={"username": ctx["owner"], "password": ctx["owner_pw"]})
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
project = ctx["project"]

r = c.post(
    f"/projects/{project}/exports/prepare",
    json={"kind": "evidence", "task_ids": [], "report_ids": []},
    headers=headers,
)
print("PREPARE", r.status_code)
manifest = r.json()
print("SELECTION", json.dumps(manifest["manifest"]["selection"]))

r = c.post(
    f"/projects/{project}/exports",
    json={
        "selection": manifest["manifest"]["selection"],
        "manifest_digest": manifest["manifest_digest"],
        "request_key": str(uuid.uuid4()),
    },
    headers=headers,
)
print("CREATE", r.status_code)
print("BODY", r.text[:800])
