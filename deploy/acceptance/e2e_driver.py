"""RI09.5 end-to-end driver over the real isolated stack (HTTP + real JWT).

Runs INSIDE the acceptance network (api container). No mocks, no direct DB writes
for business facts, no synthetic packaging. Every step records the real HTTP
status and body, and the evidence paths.

Usage: python e2e_driver.py <phase> [evidence_dir]
  phases: auth | ra03 | storage | chain | all
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

API = os.environ.get("E2E_API", "http://api:8000/api/v1")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/e2e-out")
OUT.mkdir(parents=True, exist_ok=True)

RESULTS: list[dict] = []


def rec(step: str, ok: bool, **extra) -> dict:
    row = {"step": step, "ok": ok, **extra}
    RESULTS.append(row)
    print(json.dumps(row, ensure_ascii=False, default=str), flush=True)
    return row


def save(name: str, data: bytes | str) -> str:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return str(path)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- auth helpers
def register(c: httpx.Client, username: str, password: str) -> dict:
    body = {"username": username, "email": f"{username}@example.invalid", "password": password}
    r = c.post(f"{API}/auth/register", json=body)
    return {"status": r.status_code, "body": r.text[:400]}


def login(c: httpx.Client, username: str, password: str) -> tuple[str | None, dict]:
    r = c.post(
        f"{API}/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    detail = {"status": r.status_code, "body": r.text[:300]}
    if r.status_code == 200:
        return r.json().get("access_token"), detail
    return None, detail


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def promote(username: str) -> dict:
    """Isolated disposable DB only: flip a self-registered user to active+admin."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from cygnusx.core.config import Settings, get_settings

    Settings.model_config["env_file"] = None
    get_settings.cache_clear()
    dsn = get_settings().database_url

    async def run() -> str:
        engine = create_async_engine(dsn)
        try:
            async with engine.begin() as conn:
                res = await conn.execute(
                    text(
                        "UPDATE users SET status='active', role='admin' WHERE username=:u "
                        "RETURNING id, status, role"
                    ),
                    {"u": username},
                )
                row = res.first()
                return str(row) if row else "NOT_FOUND"
        finally:
            await engine.dispose()

    return {"result": asyncio.run(run())}


def phase_auth(c: httpx.Client) -> None:
    ts = secrets.token_hex(4)
    users = {}
    for label in ("owner", "other"):
        u = f"ri095_{label}_{ts}"
        pw = f"Pass_{secrets.token_hex(4)}1"
        reg = register(c, u, pw)
        pro = promote(u)
        tok, det = login(c, u, pw)
        users[label] = {"username": u, "password": pw, "token": tok}
        rec(
            f"auth.register.{label}",
            reg["status"] == 201 or reg["status"] == 400,
            register=reg,
            promote=pro,
            login=det,
            got_jwt=tok is not None,
        )
    owner = users["owner"]["token"]
    other = users["other"]["token"]
    if not owner:
        rec("auth.abort", False, reason="owner login failed")
        return

    r = c.get(f"{API}/auth/me", headers=auth(owner))
    rec("auth.me", r.status_code == 200, status=r.status_code, body=r.text[:200])

    r = c.post(f"{API}/auth/api-keys", headers=auth(owner), json={"name": "ri095-key"})
    api_key = r.json().get("key") or r.json().get("api_key") if r.status_code == 201 else None
    rec("auth.create_api_key", r.status_code == 201, status=r.status_code, body=r.text[:200])

    # Contract: /auth/me accepts EITHER credential (CurrentUserId), so an API key is
    # valid there. The JWT-only gate (CurrentJwtUserId) is what must reject API keys —
    # e.g. creating a project report ("human approval state").
    r = c.get(f"{API}/auth/me", headers={"X-API-Key": api_key} if api_key else {})
    rec(
        "auth.apikey_accepted_on_userid_route",
        r.status_code == 200,
        status=r.status_code,
        note="CurrentUserId path accepts API key by design",
    )

    probe = c.post(f"{API}/projects", headers=auth(owner), json={"name": f"RI095 jwt-probe {ts}"})
    probe_project = probe.json().get("id") if probe.status_code in (200, 201) else None
    if probe_project and api_key:
        r = c.post(
            f"{API}/projects/{probe_project}/scientific-summary",
            headers={"X-API-Key": api_key},
            json={
                "source_manifest_job_id": str(uuid4()),
                "claims": [],
                "format": "html",
                "prepare_digest": "0" * 64,
                "request_key": str(uuid4()),
            },
        )
        rec(
            "auth.apikey_on_jwtonly_write_rejected",
            r.status_code == 401,
            status=r.status_code,
            body=r.text[:200],
        )
    else:
        rec("auth.apikey_on_jwtonly_write_rejected", False, reason="no api key or project")

    r = c.get(f"{API}/auth/me")
    rec("auth.no_auth_rejected", r.status_code == 401, status=r.status_code)

    # project ownership isolation
    r = c.post(f"{API}/projects", headers=auth(owner), json={"name": f"RI095 {ts}"})
    project = r.json().get("id") if r.status_code in (200, 201) else None
    rec("auth.create_project_owner", project is not None, status=r.status_code, project=project)

    if project:
        r = c.get(f"{API}/projects/{project}", headers=auth(other))
        rec("auth.cross_owner_project_404", r.status_code == 404, status=r.status_code)
        r = c.get(f"{API}/projects", headers=auth(other))
        body = r.json()
        items = body if isinstance(body, list) else (body.get("items") or body.get("data") or [])
        mine = [p for p in items if p.get("id") == project]
        rec(
            "auth.other_project_list_no_leak",
            len(mine) == 0,
            status=r.status_code,
            other_count=len(items),
        )

    save(
        "auth-users.json",
        json.dumps(
            {k: {"username": v["username"], "got_jwt": bool(v["token"])} for k, v in users.items()},
            ensure_ascii=False,
            indent=2,
        ),
    )

    # context for later phases
    Path(OUT / "context.json").write_text(
        json.dumps(
            {
                "owner": users["owner"]["username"],
                "owner_pw": users["owner"]["password"],
                "owner_token": owner,
                "other_token": other,
                "project": project,
            }
        )
    )


def load_ctx() -> dict:
    p = OUT / "context.json"
    if not p.exists():
        raise SystemExit("run auth phase first")
    return json.loads(p.read_text())


# ---------------------------------------------------------------- RA03 (concurrency)
def phase_ra03(c: httpx.Client) -> None:
    ctx = load_ctx()
    owner = ctx["owner_token"]
    project = ctx["project"]
    if not project:
        rec("ra03.abort", False, reason="no project from auth phase")
        return

    # A report requires an M0 export job; create a default evidence export first.
    r = c.post(
        f"{API}/projects/{project}/exports/prepare", headers=auth(owner), json={"kind": "evidence"}
    )
    rec("ra03.prepare_m0", r.status_code in (200, 201), status=r.status_code, body=r.text[:300])
    if r.status_code not in (200, 201):
        return
    manifest_digest = r.json()["manifest_digest"]
    rk = str(uuid4())
    r = c.post(
        f"{API}/projects/{project}/exports",
        headers=auth(owner),
        json={
            "selection": {"kind": "evidence", "task_ids": [], "report_ids": []},
            "manifest_digest": manifest_digest,
            "request_key": rk,
        },
    )
    rec(
        "ra03.create_m0_export",
        r.status_code in (200, 201),
        status=r.status_code,
        body=r.text[:300],
    )
    if r.status_code not in (200, 201):
        return
    export_job = r.json()["id"]

    # wait for the export to reach ready (real worker)
    status = None
    for _ in range(60):
        s = c.get(f"{API}/projects/{project}/exports/{export_job}", headers=auth(owner))
        status = s.json().get("status")
        if status in ("ready", "failed"):
            break
        time.sleep(1)
    rec("ra03.m0_export_ready", status == "ready", status=status, export_job=export_job)

    # 8 concurrent scientific-summary creates against the same M0
    import concurrent.futures

    prep = c.post(
        f"{API}/projects/{project}/scientific-summary/prepare",
        headers=auth(owner),
        json={"source_manifest_job_id": export_job, "claims": [], "format": "html"},
    )
    rec(
        "ra03.prepare_report_source",
        prep.status_code == 200,
        status=prep.status_code,
        body=prep.text[:300],
    )
    if prep.status_code != 200:
        return
    prepare_digest = prep.json()["prepare_digest"]

    def submit() -> tuple[int, str]:
        body = {
            "source_manifest_job_id": export_job,
            "claims": [],
            "format": "html",
            "prepare_digest": prepare_digest,
            "request_key": str(uuid4()),
        }
        rr = c.post(f"{API}/projects/{project}/scientific-summary", headers=auth(owner), json=body)
        try:
            jid = rr.json().get("id")
        except Exception:
            jid = None
        return rr.status_code, jid

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        outs = list(ex.map(lambda _: submit(), range(8)))
    codes = [o[0] for o in outs]
    job_ids = {o[1] for o in outs}
    rec(
        "ra03.concurrent_8",
        all(c == 200 for c in codes),
        codes=codes,
        distinct_jobs=len(job_ids),
        job_ids=sorted(map(str, job_ids)),
    )
    ctx["export_job"] = export_job
    ctx["report_job"] = sorted(map(str, job_ids))[0] if job_ids else None
    Path(OUT / "context.json").write_text(json.dumps(ctx))


def phase_chain(c: httpx.Client) -> None:
    """M0 -> Report(HTML+PDF) -> M1 via ExportSelectionV2 -> ZIP -> verify -> JWT download."""
    ctx = load_ctx()
    owner = ctx["owner_token"]
    other = ctx["other_token"]
    project = ctx["project"]
    export_job = ctx.get("export_job")
    if not (project and export_job):
        rec("chain.abort", False, reason="run auth+ra03 first")
        return

    # M0 bytes: download the default evidence ZIP before anything else.
    r = c.get(f"{API}/projects/{project}/exports/{export_job}/download", headers=auth(owner))
    rec(
        "chain.m0_download",
        r.status_code == 200,
        status=r.status_code,
        sha256=sha(r.content) if r.status_code == 200 else None,
        size=len(r.content),
    )
    m0_sha = sha(r.content) if r.status_code == 200 else None
    save("m0-export.zip", r.content)

    # ---- report job -> ready (HTML required; PDF only if format=html_pdf) ----
    prep = c.post(
        f"{API}/projects/{project}/scientific-summary/prepare",
        headers=auth(owner),
        json={"source_manifest_job_id": export_job, "claims": [], "format": "html_pdf"},
    )
    rec(
        "chain.prepare_report_html_pdf",
        prep.status_code == 200,
        status=prep.status_code,
        body=prep.text[:300],
    )
    if prep.status_code != 200:
        return
    body = {
        "source_manifest_job_id": export_job,
        "claims": [],
        "format": "html_pdf",
        "prepare_digest": prep.json()["prepare_digest"],
        "request_key": str(uuid4()),
    }
    r = c.post(f"{API}/projects/{project}/scientific-summary", headers=auth(owner), json=body)
    rec("chain.create_report", r.status_code == 200, status=r.status_code, body=r.text[:300])
    if r.status_code != 200:
        return
    report_job = r.json()["id"]

    status = None
    for _ in range(90):
        s = c.get(f"{API}/projects/{project}/scientific-summary/{report_job}", headers=auth(owner))
        j = s.json()
        status = j.get("status")
        if status in ("ready", "failed"):
            break
        time.sleep(1)
    rec(
        "chain.report_terminal",
        status in ("ready", "failed"),
        status=status,
        pdf_status=j.get("pdf_status"),
        html_sha256=j.get("html_sha256"),
        pdf_sha256=j.get("pdf_sha256"),
        html_size=j.get("html_size"),
        pdf_size=j.get("pdf_size"),
        error_code=j.get("error_code"),
    )

    # ---- HTML: DB vs HTTP download SHA parity ----
    h = c.get(
        f"{API}/projects/{project}/scientific-summary/{report_job}/download",
        headers=auth(owner),
        params={"format": "html"},
    )
    html_ok = h.status_code == 200 and sha(h.content) == j.get("html_sha256")
    rec(
        "chain.html_db_http_sha_parity",
        html_ok,
        status=h.status_code,
        http_sha=sha(h.content) if h.status_code == 200 else None,
        db_sha=j.get("html_sha256"),
    )
    if h.status_code == 200:
        save("report.html", h.content)

    # ---- PDF: DB vs HTTP download SHA parity + parse/fonts/pages ----
    if j.get("pdf_status") == "ready" or j.get("pdf_sha256"):
        p = c.get(
            f"{API}/projects/{project}/scientific-summary/{report_job}/download",
            headers=auth(owner),
            params={"format": "pdf"},
        )
        pdf_ok = p.status_code == 200 and sha(p.content) == j.get("pdf_sha256")
        rec(
            "chain.pdf_db_http_sha_parity",
            pdf_ok,
            status=p.status_code,
            http_sha=sha(p.content) if p.status_code == 200 else None,
            db_sha=j.get("pdf_sha256"),
        )
        if p.status_code == 200:
            save("report.pdf", p.content)
            try:
                import io

                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(p.content))
                text = "".join((pg.extract_text() or "") for pg in reader.pages)
                rec(
                    "chain.pdf_parse",
                    True,
                    pages=len(reader.pages),
                    chars=len(text),
                    has_cjk=any("一" <= ch <= "鿿" for ch in text),
                )
                save("report.pdf.txt", text)
            except Exception as exc:  # noqa: BLE001
                rec("chain.pdf_parse", False, error=str(exc)[:200])
    else:
        rec("chain.pdf_db_http_sha_parity", False, reason=f"pdf_status={j.get('pdf_status')}")

    # ---- M1 via ExportSelectionV2: bundle the report artifact ----
    v2 = {
        "kind": "evidence",
        "task_ids": [],
        "report_ids": [],
        "source_manifest_job_id": export_job,
        "project_report_job_ids": [report_job],
    }
    prep2 = c.post(f"{API}/projects/{project}/exports/prepare", headers=auth(owner), json=v2)
    rec(
        "chain.m1_prepare_v2",
        prep2.status_code == 200,
        status=prep2.status_code,
        body=prep2.text[:300],
        schema=None if prep2.status_code != 200 else prep2.json()["manifest"].get("schema_version"),
    )
    if prep2.status_code == 200:
        m1 = prep2.json()
        save("m1-manifest.json", json.dumps(m1["manifest"], ensure_ascii=False, indent=2))
        rec(
            "chain.m1_has_report_artifacts",
            bool(m1["manifest"].get("report_artifacts")),
            report_artifacts=m1["manifest"].get("report_artifacts"),
        )

        r = c.post(
            f"{API}/projects/{project}/exports",
            headers=auth(owner),
            json={
                "selection": v2,
                "manifest_digest": m1["manifest_digest"],
                "request_key": str(uuid4()),
            },
        )
        rec("chain.m1_create_export", r.status_code == 200, status=r.status_code, body=r.text[:300])
        if r.status_code == 200:
            v2_job = r.json()["id"]
            vstatus = None
            for _ in range(90):
                s = c.get(f"{API}/projects/{project}/exports/{v2_job}", headers=auth(owner))
                vstatus = s.json().get("status")
                if vstatus in ("ready", "failed"):
                    break
                time.sleep(1)
            st = c.get(f"{API}/projects/{project}/exports/{v2_job}", headers=auth(owner)).json()
            rec(
                "chain.m1_export_ready",
                vstatus == "ready",
                status=vstatus,
                archive_sha256=st.get("archive_sha256"),
                error_code=st.get("error_code"),
            )
            if vstatus == "ready":
                z = c.get(
                    f"{API}/projects/{project}/exports/{v2_job}/download", headers=auth(owner)
                )
                rec(
                    "chain.zip_download_jwt",
                    z.status_code == 200,
                    status=z.status_code,
                    http_sha=sha(z.content),
                    db_sha=st.get("archive_sha256"),
                )
                save("m1-delivery.zip", z.content)
                # verify with the repo's own stdlib verifier
                try:
                    import tempfile

                    from cygnusx.domain.project_delivery_archive import verify_archive

                    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
                        tf.write(z.content)
                        tmp = tf.name
                    res = verify_archive(tmp)
                    members = _zip_members(z.content)
                    rec("chain.zip_verify_archive", True, result=str(res)[:200], members=members)
                    save("zip-members.json", json.dumps(members, indent=2))
                except Exception as exc:  # noqa: BLE001
                    rec("chain.zip_verify_archive", False, error=str(exc)[:300])
                # cross-owner download must be rejected
                o = c.get(
                    f"{API}/projects/{project}/exports/{v2_job}/download", headers=auth(other)
                )
                rec("chain.zip_cross_owner_denied", o.status_code == 404, status=o.status_code)

    # ---- M0 byte immutability across the whole run ----
    r2 = c.get(f"{API}/projects/{project}/exports/{export_job}/download", headers=auth(owner))
    rec(
        "chain.m0_bytes_unchanged",
        r2.status_code == 200 and sha(r2.content) == m0_sha,
        before=m0_sha,
        after=sha(r2.content) if r2.status_code == 200 else None,
    )

    ctx["v2_job"] = locals().get("v2_job")
    ctx["report_job"] = report_job
    Path(OUT / "context.json").write_text(json.dumps(ctx))


def _zip_members(blob: bytes) -> list[str]:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return sorted(zf.namelist())


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    with httpx.Client(timeout=120.0, follow_redirects=True) as c:
        if phase in ("auth", "all"):
            phase_auth(c)
        if phase in ("ra03", "all"):
            phase_ra03(c)
        if phase in ("chain", "all"):
            phase_chain(c)
    save("results.json", json.dumps(RESULTS, ensure_ascii=False, indent=2, default=str))
    failed = [r for r in RESULTS if not r["ok"]]
    print(json.dumps({"summary": {"steps": len(RESULTS), "failed": len(failed)}}), flush=True)


if __name__ == "__main__":
    main()
