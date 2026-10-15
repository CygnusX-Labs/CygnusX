"""Read-only GEO SOFT / ENA filereport with bounded trust and explicit gaps.

SOFT: https://www.ncbi.nlm.nih.gov/geo/info/soft.html
ENA: https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/file-reports.html
No fabricated file paths, one-to-one sample/run assumptions or inferred groups.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import re
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from cygnusx.core.exceptions import ValidationError

ACCESSION = re.compile(r"^(?:GSE|GSM|GPL|[SED]R[PXRS]|PRJ(?:NA|EB|DB))\d+$")
RELATED = re.compile(r"\b(?:GSE|GSM|GPL|[SED]R[PXRS]|PRJ(?:NA|EB|DB))\d+\b")
TRUSTED_HOSTS = frozenset(
    {"www.ncbi.nlm.nih.gov", "ftp.ncbi.nlm.nih.gov", "www.ebi.ac.uk", "ftp.sra.ebi.ac.uk"}
)


def accession(value: str) -> str:
    result = value.strip().upper()
    if not ACCESSION.fullmatch(result):
        raise ValidationError("不支持或无效的公共 accession", code="INVALID_ACCESSION")
    return result


def trusted_url(value: str, *, source_ftp: bool = False) -> str:
    """Only exact reviewed public source hosts, HTTPS, no credentials/ports/redirects."""
    if len(value) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValidationError("附件 URL 非法", code="UNTRUSTED_SOURCE")
    parsed = urlsplit(value)
    if source_ftp and parsed.scheme == "ftp":
        parsed = parsed._replace(scheme="https")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("附件 URL 非法", code="UNTRUSTED_SOURCE") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in TRUSTED_HOSTS
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.fragment
        or "\\" in value
        or any(p in {".", ".."} for p in unquote(parsed.path).split("/"))
    ):
        raise ValidationError("来源主机或协议未经审核", code="UNTRUSTED_SOURCE")
    return urlunsplit(parsed)


def parse_soft(text: str) -> dict[str, dict[str, list[str]]]:
    records: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    for line in text.splitlines():
        if line.startswith("^") and " = " in line:
            _, key = line.split(" = ", 1)
            current = records.setdefault(key, {}) if ACCESSION.fullmatch(key) else None
        elif current is not None and line.startswith("!") and " = " in line:
            key, value = line[1:].split(" = ", 1)
            current.setdefault(key.lower(), []).append(value[:8000])
    return records


class GeoMetadataAdapter:
    """Injected transport is for fixture tests; production never accepts a user base URL."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_response_bytes: int = 2 * 1024 * 1024,
        max_samples: int = 24,
        max_runs: int = 100,
        request_interval: float = 0.5,
        cache_seconds: int = 300,
    ) -> None:
        self.transport = transport
        self.max_bytes = max_response_bytes
        self.max_samples = max_samples
        self.max_runs = max_runs
        self.interval = request_interval
        self.cache_seconds = cache_seconds
        self._cache: OrderedDict[str, tuple[float, str, dict[str, Any]]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._next_request = 0.0

    async def _fetch(self, url: str) -> tuple[str, dict[str, Any]]:
        url = trusted_url(url)
        cached = self._cache.get(url)
        if cached and time.monotonic() - cached[0] < self.cache_seconds:
            self._cache.move_to_end(url)
            return cached[1], cached[2]
        headers = {"Accept": "text/plain", "User-Agent": "CygnusX-DatasetMetadata/1.0"}
        if cached:
            for key, field in (("If-None-Match", "etag"), ("If-Modified-Since", "last_modified")):
                if cached[2].get(field):
                    headers[key] = cached[2][field]
        # No transparent retries. A 429/timeout is explicit, never a retry storm.
        async with self._lock:
            await asyncio.sleep(max(0, self._next_request - time.monotonic()))
            self._next_request = time.monotonic() + self.interval
            async with (
                httpx.AsyncClient(
                    transport=self.transport,
                    timeout=httpx.Timeout(10),
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream("GET", url, headers=headers) as response,
            ):
                if response.status_code == 304 and cached:
                    return cached[1], cached[2]
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > self.max_bytes:
                        raise ValidationError("元数据响应超过预算", code="METADATA_LIMIT")
                    body.extend(chunk)
                text = bytes(body).decode("utf-8-sig", errors="strict")
                evidence = {
                    "url": url,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                    "api_version": "GEO-SOFT/ENA-portal-v1",
                    "etag": response.headers.get("etag"),
                    "last_modified": response.headers.get("last-modified"),
                }
        self._cache[url] = (time.monotonic(), text, evidence)
        self._cache.move_to_end(url)
        while len(self._cache) > 64:
            self._cache.popitem(last=False)
        return text, evidence

    async def resolve(self, value: str, *, refresh: bool = False) -> dict[str, Any]:
        if refresh:
            self._cache.clear()
        primary = accession(value)
        candidate: dict[str, Any] = {
            "schema_version": "1.0",
            "repository": "GEO" if primary.startswith("G") else "ENA",
            "primary_accession": primary,
            "assay_type": "unknown",
            "organism": [],
            "samples": [],
            "related_accessions": [],
            "files": [],
            "runs": [],
            "source_evidence": [],
            "confidence_flags": ["sample_groups_need_review", "access_terms_unknown"],
            "status": "NEEDS_REVIEW",
            "access_status": "UNKNOWN",
        }
        try:
            if primary.startswith("G"):
                await self._geo(primary, candidate)
            else:
                await self._ena(primary, candidate)
        except (httpx.HTTPError, UnicodeDecodeError, ValidationError) as exc:
            candidate["status"] = "UNAVAILABLE"
            candidate["error_code"] = (
                exc.code if isinstance(exc, ValidationError) else "METADATA_UNAVAILABLE"
            )
        if not candidate["runs"]:
            candidate["confidence_flags"].append("raw_runs_not_resolved")
        if not candidate["files"]:
            candidate["confidence_flags"].append("no_supplementary_files_verified")
        return candidate

    async def _geo_record(self, acc: str, result: dict[str, Any]) -> dict[str, list[str]]:
        url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={acc}&targ=self&form=text&view=full"
        text, evidence = await self._fetch(url)
        result["source_evidence"].append(evidence)
        records = parse_soft(text)
        if acc not in records:
            raise ValidationError("GEO 未返回请求的记录", code="ACCESSION_NOT_FOUND")
        record = records[acc]
        for key, values in record.items():
            if "supplementary_file" in key:
                for value in values:
                    if value.lower() == "none":
                        continue
                    try:
                        url = trusted_url(value, source_ftp=True)
                    except ValidationError:
                        result["confidence_flags"].append("untrusted_attachment_rejected")
                        continue
                    name = unquote(PurePosixPath(urlsplit(url).path).name)
                    result["files"].append(
                        {
                            "source_accession": acc,
                            "url": url,
                            "original_name": name,
                            "size": None,
                            "sha256": None,
                            "data_type": "UNKNOWN",
                            "format_hint": "series_matrix"
                            if "series_matrix" in name.lower()
                            else PurePosixPath(name).suffix.lower(),
                            "evidence_ref": evidence["response_sha256"],
                        }
                    )
            if key.endswith("relation") or key.endswith("platform_id"):
                for value in values:
                    for related in RELATED.findall(value):
                        edge = {
                            "from": acc,
                            "to": related,
                            "relation": key,
                            "evidence_ref": evidence["response_sha256"],
                        }
                        if edge not in result["related_accessions"]:
                            result["related_accessions"].append(edge)
        for organism in record.get("sample_organism_ch1", []):
            if organism not in result["organism"]:
                result["organism"].append(organism)
        return record

    async def _geo(self, primary: str, result: dict[str, Any]) -> None:
        record = await self._geo_record(primary, result)
        sample_ids = record.get("series_sample_id", []) if primary.startswith("GSE") else []
        if primary.startswith("GSM"):
            sample_ids = [primary]
        if len(sample_ids) > self.max_samples:
            result["confidence_flags"].append("samples_truncated")
        for sample_id in sample_ids[: self.max_samples]:
            if not re.fullmatch(r"GSM\d+", sample_id):
                continue
            sample = record if sample_id == primary else await self._geo_record(sample_id, result)
            result["related_accessions"].append(
                {"from": primary, "to": sample_id, "relation": "series_sample_id"}
            )
            result["samples"].append(
                {
                    "sample_key": sample_id,
                    "title": sample.get("sample_title", []),
                    "characteristics": sample.get("sample_characteristics_ch1", []),
                    "organism": sample.get("sample_organism_ch1", []),
                    "platform": sample.get("sample_platform_id", []),
                    "processing": sample.get("sample_data_processing", []),
                    "source_url": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={sample_id}",
                    "group": None,
                    "group_evidence": "UNKNOWN",
                }
            )
        experiments = list(
            dict.fromkeys(
                e["to"]
                for e in result["related_accessions"]
                if re.fullmatch(r"[SED]RX\d+", e["to"])
            )
        )
        for exp in experiments[: self.max_samples]:
            await self._ena(exp, result)

    async def _ena(self, acc: str, result: dict[str, Any]) -> None:
        fields = "run_accession,experiment_accession,sample_accession,study_accession,library_layout,library_strategy,scientific_name,fastq_ftp,fastq_md5,fastq_bytes"
        url = f"https://www.ebi.ac.uk/ena/portal/api/filereport?accession={acc}&result=read_run&fields={fields}&format=tsv"
        text, evidence = await self._fetch(url)
        result["source_evidence"].append(evidence)
        for i, row in enumerate(csv.DictReader(io.StringIO(text), delimiter="\t")):
            if i >= self.max_runs:
                result["confidence_flags"].append("runs_truncated")
                break
            run = row.get("run_accession", "")
            experiment = row.get("experiment_accession", "")
            if not re.fullmatch(r"[SED]RR\d+", run):
                continue
            # Protect against an upstream mismatched accession response.
            if acc not in {
                run,
                experiment,
                row.get("sample_accession"),
                row.get("study_accession"),
            }:
                raise ValidationError("ENA 返回不匹配的 accession", code="SOURCE_MISMATCH")
            files = row.get("fastq_ftp", "").split(";")
            md5s = row.get("fastq_md5", "").split(";")
            sizes = row.get("fastq_bytes", "").split(";")
            file_records = []
            for index, link in enumerate(files):
                if not link:
                    continue
                url = trusted_url(link if "://" in link else "https://" + link, source_ftp=True)
                size = int(sizes[index]) if index < len(sizes) and sizes[index].isdigit() else None
                file_records.append(
                    {
                        "url": url,
                        "size": size,
                        "source_md5": md5s[index] if index < len(md5s) else None,
                    }
                )
            result["runs"].append(
                {
                    "run_accession": run,
                    "experiment_accession": experiment,
                    "sample_accession": row.get("sample_accession"),
                    "library_layout": row.get("library_layout") or "UNKNOWN",
                    "library_strategy": row.get("library_strategy") or "UNKNOWN",
                    "organism": row.get("scientific_name") or "UNKNOWN",
                    "files": file_records,
                    "evidence_ref": evidence["response_sha256"],
                }
            )
            result["related_accessions"].append(
                {
                    "from": acc,
                    "to": run,
                    "relation": "ena_read_run",
                    "evidence_ref": evidence["response_sha256"],
                }
            )
        if len(result["organism"]) > 1:
            result["confidence_flags"].append("mixed_organisms")
