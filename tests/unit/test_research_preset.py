"""Contract and boundary tests for the internal research-data preset."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from cygnusx.application.services.research_data_service import (
    _request,
    _request_xml,
    execute_research,
)
from cygnusx.infrastructure.mcp.presets import get_preset_by_name
from cygnusx.infrastructure.mcp.research_preset import (
    CYGNUSX_RESEARCH_SERVER_NAME,
    RESEARCH_HANDLERS,
    RESEARCH_TOOLS,
    validate_research_arguments,
)


class _CountingByteStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.yielded = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.unit
def test_research_preset_has_fixed_verified_read_only_contract():
    preset = get_preset_by_name(CYGNUSX_RESEARCH_SERVER_NAME)

    assert preset is not None
    assert preset["transport"] == "builtin"
    assert len(RESEARCH_TOOLS) == 28
    assert set(RESEARCH_HANDLERS) == {tool["name"] for tool in RESEARCH_TOOLS}


@pytest.mark.unit
async def test_research_service_rejects_unbounded_inputs_before_http(monkeypatch):
    async def fail_request(*_args, **_kwargs):
        pytest.fail("invalid provider input must fail before HTTP")

    monkeypatch.setattr("cygnusx.application.services.research_data_service._request", fail_request)
    result = await execute_research("cygnusx_pathway_get", {"pathway_id": "not-a-pathway"})
    assert result["success"] is False
    assert "pathway_id" in result["summary"]


@pytest.mark.unit
async def test_research_builtin_handler_enforces_published_tool_schema(monkeypatch):
    async def fail(*_args, **_kwargs):
        pytest.fail("invalid arguments must not reach the provider service")

    monkeypatch.setattr("cygnusx.infrastructure.mcp.research_preset.execute_research", fail)
    from cygnusx.infrastructure.mcp.research_preset import research_handler

    result = await research_handler(
        {"pathway_id": "R-HSA-1", "owner_id": "other-user"},
        tool_name="cygnusx_pathway_get",
    )

    assert result == {
        "success": False,
        "summary": "Unknown arguments: owner_id",
        "data": None,
    }


@pytest.mark.unit
async def test_research_service_uses_fixed_rcsb_endpoint(monkeypatch):
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"total_count": 1, "result_set": [{"identifier": "1ABC_1"}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )
    result = await execute_research("cygnusx_structure_search", {"accession": "P04637"})

    assert result["success"] is True
    assert requests[0].url.host == "search.rcsb.org"
    assert requests[0].method == "POST"
    await client.aclose()


@pytest.mark.unit
async def test_string_identifier_resolution_preserves_ambiguous_taxon_matches(monkeypatch):
    calls = []

    async def request(method, params):
        calls.append((method, params))
        return [
            {"stringId": "9606.ENSP00000269305", "ncbiTaxonId": "9606", "preferredName": "TP53"},
            {"stringId": "9606.ENSP00000269306", "ncbiTaxonId": "9606", "preferredName": "TP53"},
            {"stringId": "3702.AT1G01010", "ncbiTaxonId": "3702", "preferredName": "TP53"},
        ]

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_string_tsv", request
    )
    result = await execute_research(
        "cygnusx_string_resolve", {"identifier": "TP53", "taxon_id": 9606, "limit": 10}
    )

    assert result["success"] is True
    payload = result["data"]["result"]
    assert payload["candidate_count"] == 2
    assert {item["string_id"] for item in payload["candidates"]} == {
        "9606.ENSP00000269305",
        "9606.ENSP00000269306",
    }
    assert calls[0][0] == "get_string_ids"
    assert calls[0][1]["species"] == 9606


@pytest.mark.unit
async def test_string_network_requires_matching_taxon_and_disables_node_expansion(monkeypatch):
    calls = []

    async def request(method, params):
        calls.append((method, params))
        if params.get("network_type") == "regulatory":
            return [
                {
                    "source_string_id": "9606.ENSP00000269305",
                    "source_preferred_name": "TP53",
                    "target_string_id": f"9606.ENSP0000025814{i}",
                    "target_preferred_name": "MDM2" if i == 9 else f"gene{i}",
                    "combined_score": "0.996",
                }
                for i in (9, 8, 7)
            ]
        return [
            {
                "stringId_A": "9606.ENSP00000269305",
                "stringId_B": f"9606.ENSP00000{i}",
                "preferredName_B": f"partner{i}",
                "score": "0.999",
            }
            for i in range(3)
        ]

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_string_tsv", request
    )
    invalid = await execute_research(
        "cygnusx_string_network",
        {"string_id": "10090.ENSMUSP00000000001", "taxon_id": 9606, "network_type": "physical"},
    )
    assert invalid["success"] is False
    assert calls == []

    result = await execute_research(
        "cygnusx_string_network",
        {
            "string_id": "9606.ENSP00000269305",
            "taxon_id": 9606,
            "network_type": "regulatory",
            "required_score": 500,
            "limit": 2,
        },
    )
    assert result["success"] is True
    payload = result["data"]["result"]
    assert payload["returned"] == 2
    assert payload["has_more"] is True
    assert payload["partners"][0]["combined_score"] == 0.996
    assert payload["partners"][0]["partner_string_id"] == "9606.ENSP00000258149"
    assert payload["partners"][0]["partner_preferred_name"] == "MDM2"
    assert "directional" in payload["interpretation"]
    assert calls[0][0] == "interaction_partners"
    assert calls[0][1]["network_type"] == "regulatory"
    assert calls[0][1]["add_color_nodes"] == 0
    assert calls[0][1]["add_white_nodes"] == 0

    async def unrelated_row(_method, _params):
        return [
            {
                "source_string_id": "9606.ENSP00000999999",
                "source_preferred_name": "OTHER_A",
                "target_string_id": "9606.ENSP00000888888",
                "target_preferred_name": "OTHER_B",
                "combined_score": "0.9",
            }
        ]

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_string_tsv",
        unrelated_row,
    )
    unrelated = await execute_research(
        "cygnusx_string_network",
        {
            "string_id": "9606.ENSP00000269305",
            "taxon_id": 9606,
            "network_type": "regulatory",
        },
    )
    assert unrelated["success"] is False
    assert "unrelated" in unrelated["summary"]


@pytest.mark.unit
async def test_string_rate_limit_uses_shared_redis_slot(monkeypatch):
    from cygnusx.application.services import research_data_service as service

    class FakeRedis:
        def __init__(self):
            self.delays = iter((250, 0))
            self.calls = []

        async def eval(self, *args):
            self.calls.append(args)
            return next(self.delays)

    fake = FakeRedis()
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(service, "get_redis", lambda: fake)
    monkeypatch.setattr(service.asyncio, "sleep", sleep)

    await service._string_rate_limit()

    assert len(fake.calls) == 2
    assert fake.calls[0][2] == "provider-rate:string:v12-5"
    assert slept == [0.25]


@pytest.mark.unit
async def test_string_tsv_parser_uses_versioned_host_and_rejects_html(monkeypatch):
    from cygnusx.application.services import research_data_service as service

    async def no_wait():
        return None

    monkeypatch.setattr(service, "_string_rate_limit", no_wait)
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/tab-separated-values; charset=utf-8"},
            text="stringId\tncbiTaxonId\tpreferredName\n9606.ENSP00000269305\t9606\tTP53\n",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(service, "_client", lambda: client)
    rows = await service._request_string_tsv(
        "get_string_ids", {"identifiers": "TP53", "species": 9606}
    )
    assert rows[0]["preferredName"] == "TP53"
    assert requests[0].url.host == "version-12-5.string-db.org"
    assert requests[0].url.path == "/api/tsv/get_string_ids"
    await client.aclose()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_host", "expected_path"),
    [
        ("cygnusx_te_get", {"accession": "DF0000001"}, "dfam.org", "/api/families/DF0000001"),
        (
            "cygnusx_expression_studies",
            {"single_cell": False},
            "www.ebi.ac.uk",
            "/gxa/json/experiments",
        ),
        (
            "cygnusx_expression_studies",
            {"single_cell": True},
            "www.ebi.ac.uk",
            "/gxa/sc/json/experiments",
        ),
        (
            "cygnusx_domain_get",
            {"accession": "P04637"},
            "www.ebi.ac.uk",
            "/interpro/api/entry/interpro/protein/uniprot/P04637/",
        ),
        (
            "cygnusx_target_search",
            {"query": "TP53"},
            "api.platform.opentargets.org",
            "/api/v4/graphql",
        ),
    ],
)
async def test_research_service_uses_fixed_provider_endpoints(
    monkeypatch, tool_name, arguments, expected_host, expected_path
):
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"experiments": [], "data": {"search": {"hits": []}}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )
    result = await execute_research(tool_name, arguments)

    assert result["success"] is True
    assert len(requests) == (2 if tool_name == "cygnusx_pathway_get" else 1)
    assert all(request.url.host == expected_host for request in requests)
    assert any(expected_path in request.url.path for request in requests)
    await client.aclose()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_host", "path_fragment"),
    [
        (
            "cygnusx_genome_lookup",
            {"species": "arabidopsis_thaliana", "identifier": "AT1G01010"},
            "rest.ensembl.org",
            "/lookup/id/",
        ),
        (
            "cygnusx_genome_homology",
            {"species": "arabidopsis_thaliana", "identifier": "AT1G01010"},
            "rest.ensembl.org",
            "/homology/id/",
        ),
        (
            "cygnusx_genome_region",
            {"species": "arabidopsis_thaliana", "region": "1:1..10"},
            "rest.ensembl.org",
            "/overlap/region/",
        ),
        (
            "cygnusx_genome_sequence",
            {"identifier": "AT1G01010"},
            "rest.ensembl.org",
            "/sequence/id/",
        ),
        ("cygnusx_plant_search", {"query": "rice", "limit": 1}, "data.gramene.org", "/v69/search"),
        ("cygnusx_plant_get", {"identifier": "LOC_Os01g01010"}, "data.gramene.org", "/v69/genes"),
        ("cygnusx_te_search", {"query": "CACTA", "limit": 1}, "dfam.org", "/api/families"),
        ("cygnusx_te_get", {"accession": "DF0000001"}, "dfam.org", "/api/families/"),
        (
            "cygnusx_expression_studies",
            {"single_cell": False, "limit": 1},
            "www.ebi.ac.uk",
            "/gxa/json/experiments",
        ),
        (
            "cygnusx_expression_studies",
            {"single_cell": True, "limit": 1},
            "www.ebi.ac.uk",
            "/gxa/sc/json/experiments",
        ),
        (
            "cygnusx_expression_manifest",
            {"accession": "E-MTAB-1", "single_cell": False},
            "www.ebi.ac.uk",
            "/gxa/json/experiments",
        ),
        (
            "cygnusx_expression_manifest",
            {"accession": "E-MTAB-1", "single_cell": True},
            "www.ebi.ac.uk",
            "/gxa/sc/json/experiments",
        ),
        ("cygnusx_protein_resolve", {"query": "TP53"}, "rest.uniprot.org", "/uniprotkb/search"),
        (
            "cygnusx_protein_features",
            {"accession": "P04637"},
            "rest.uniprot.org",
            "/uniprotkb/P04637.json",
        ),
        (
            "cygnusx_protein_sequence",
            {"accession": "P04637"},
            "rest.uniprot.org",
            "/uniprotkb/P04637.fasta",
        ),
        ("cygnusx_domain_get", {"accession": "P04637"}, "www.ebi.ac.uk", "/interpro/api/entry/"),
        (
            "cygnusx_domain_proteins",
            {"interpro_id": "IPR000001"},
            "www.ebi.ac.uk",
            "/interpro/api/protein/",
        ),
        ("cygnusx_structure_get", {"entry_id": "1ABC"}, "data.rcsb.org", "/rest/v1/core/entry/"),
        (
            "cygnusx_structure_search",
            {"accession": "P04637"},
            "search.rcsb.org",
            "/rcsbsearch/v2/query",
        ),
        (
            "cygnusx_structure_prediction",
            {"accession": "P04637"},
            "alphafold.ebi.ac.uk",
            "/api/prediction/",
        ),
        (
            "cygnusx_pathway_get",
            {"pathway_id": "R-HSA-1"},
            "reactome.org",
            "/ContentService/data/query/",
        ),
        (
            "cygnusx_clinvar_search",
            {"query": "BRCA1"},
            "eutils.ncbi.nlm.nih.gov",
            "/entrez/eutils/esearch.fcgi",
        ),
        (
            "cygnusx_clinvar_get",
            {"vcv_accession": "VCV000000001"},
            "eutils.ncbi.nlm.nih.gov",
            "/entrez/eutils/efetch.fcgi",
        ),
        (
            "cygnusx_target_search",
            {"query": "TP53"},
            "api.platform.opentargets.org",
            "/api/v4/graphql",
        ),
        (
            "cygnusx_target_associations",
            {"target_id": "ENSG00000141510"},
            "api.platform.opentargets.org",
            "/api/v4/graphql",
        ),
        (
            "cygnusx_target_evidence",
            {"target_id": "ENSG00000141510", "disease_id": "EFO_0000305"},
            "api.platform.opentargets.org",
            "/api/v4/graphql",
        ),
        (
            "cygnusx_literature_get",
            {"article_id": "12345"},
            "www.ebi.ac.uk",
            "/europepmc/webservices/rest/article/MED/",
        ),
        (
            "cygnusx_literature_annotations",
            {"article_ids": ["MED:12345"]},
            "www.ebi.ac.uk",
            "/europepmc/webservices/rest/annotationsByArticleIds",
        ),
    ],
)
async def test_every_research_tool_routes_to_its_fixed_provider(
    monkeypatch, tool_name, arguments, expected_host, path_fragment
):
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/efetch.fcgi"):
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                content=b'<VariationArchive Accession="VCV000000001" />',
            )
        if request.url.path.endswith("/database/version"):
            return httpx.Response(200, text="93")
        if request.url.path.endswith(".fasta"):
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text=">P04637\nMPEPTIDE\n",
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={
                "seq": "ATGC",
                "experiments": [{"accession": "E-MTAB-1"}],
                "comments": [],
                "features": [],
                "data": {"search": {"hits": []}},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )
    result = await execute_research(tool_name, arguments)

    assert result["success"] is True, result
    expected_request_count = 2 if tool_name == "cygnusx_pathway_get" else 1
    assert len(requests) == expected_request_count
    assert all(request.url.host == expected_host for request in requests)
    assert any(path_fragment in request.url.path for request in requests)
    await client.aclose()


@pytest.mark.unit
async def test_clinvar_get_uses_vcv_efetch_and_keeps_evidence_categories(monkeypatch):
    import xml.etree.ElementTree as ET

    requests = []
    xml = ET.fromstring(
        '<ClinVarResult-Set><VariationArchive Accession="VCV000000001" Version="4" '
        'VariationID="1" NumberOfSubmissions="2" NumberOfSubmitters="1">'
        '<Classifications><GermlineClassification><ReviewStatus>criteria provided, '
        'multiple submitters</ReviewStatus><Description>Pathogenic</Description>'
        '</GermlineClassification><SomaticClinicalImpact><Description>Responsive</Description>'
        '</SomaticClinicalImpact><OncogenicityClassification>'
        '<Description>Uncertain significance</Description></OncogenicityClassification>'
        '</Classifications><ClinicalAssertion><ClinVarSubmissionID title="Example lab" />'
        '</ClinicalAssertion></VariationArchive></ClinVarResult-Set>'
    )

    async def request_xml(provider, path, *, params):
        requests.append((provider, path, params))
        return xml

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_xml", request_xml
    )

    result = await execute_research("cygnusx_clinvar_get", {"vcv_accession": "VCV000000001.4"})

    assert requests == [
        (
            "clinvar",
            "efetch.fcgi",
            {
                "db": "clinvar",
                "id": "VCV000000001.4",
                "rettype": "vcv",
                "retmode": "xml",
            },
        )
    ]
    data = result["data"]["result"]
    assert data["record"] == {
        "record_type": "VCV",
        "accession": "VCV000000001",
        "version": "4",
        "variation_id": "1",
        "submission_count": "2",
        "submitter_count": "1",
        "scv_accessions": [],
    }
    assert data["classifications"]["germline"][0]["evidence"][1]["text"] == "Pathogenic"
    assert (
        data["classifications"]["somatic_clinical_impact"][0]["evidence"][0]["text"]
        == "Responsive"
    )
    assert (
        data["classifications"]["oncogenicity"][0]["evidence"][0]["text"]
        == "Uncertain significance"
    )
    assert data["review_statuses"][0]["text"] == "criteria provided, multiple submitters"
    assert data["submitter_evidence"][0]["element"] == "ClinVarSubmissionID"
    assert data["submitter_evidence"][0]["attributes"]["title"] == "Example lab"


@pytest.mark.unit
async def test_clinvar_get_rejects_non_vcv_identifier_before_http(monkeypatch):
    async def fail(*_args, **_kwargs):
        pytest.fail("non-VCV identifiers must not reach E-utilities")

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_xml", fail
    )
    result = await execute_research("cygnusx_clinvar_get", {"vcv_accession": "RCV000000001"})

    assert result["success"] is False
    assert "VCV" in result["summary"]


@pytest.mark.unit
async def test_clinvar_get_rejects_response_with_wrong_vcv_version(monkeypatch):
    import xml.etree.ElementTree as ET

    async def request_xml(*_args, **_kwargs):
        return ET.fromstring(
            '<ClinVarResult-Set><VariationArchive Accession="VCV000000001" Version="3" '
            'VariationID="1" /></ClinVarResult-Set>'
        )

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_xml", request_xml
    )
    result = await execute_research(
        "cygnusx_clinvar_get", {"vcv_accession": "VCV000000001.4"}
    )

    assert result["success"] is False
    assert "different VCV version" in result["summary"]


@pytest.mark.unit
def test_clinvar_schema_keeps_legacy_vcv_and_requires_typed_pair():
    assert validate_research_arguments(
        "cygnusx_clinvar_get", {"vcv_accession": "VCV000000001"}
    ) is None
    assert validate_research_arguments(
        "cygnusx_clinvar_get", {"identifier": "RCV000000001"}
    ) == "identifier and identifier_type must be provided together"
    assert validate_research_arguments(
        "cygnusx_clinvar_get", {"vcv_accession": None}
    ) == "ClinVar identifier arguments cannot be null"
    assert validate_research_arguments(
        "cygnusx_clinvar_get",
        {"vcv_accession": "VCV000000001", "identifier": "1", "identifier_type": "VariationID"},
    ) == "Use vcv_accession or identifier with identifier_type, not both"


@pytest.mark.unit
async def test_clinvar_get_supports_rcv_scv_and_variation_id_without_coercion(monkeypatch):
    import xml.etree.ElementTree as ET

    calls = []
    rcv_xml = ET.fromstring(
        '<ClinVarResult-Set><ClinVarSet><ReferenceClinVarAssertion>'
        '<ClinVarAccession Acc="RCV000000123" Version="7" Type="RCV" />'
        '<ClinVarAssertion><ClinVarAccession Acc="SCV000000456" Version="2" Type="SCV" />'
        '</ClinVarAssertion></ReferenceClinVarAssertion></ClinVarSet></ClinVarResult-Set>'
    )
    vcv_xml = ET.fromstring(
        '<ClinVarResult-Set><VariationArchive Accession="VCV000000123" Version="3" '
        'VariationID="14206"><ClinicalAssertion><ClinVarAccession Accession="SCV000000456" '
        'Version="2" Type="SCV" /></ClinicalAssertion></VariationArchive></ClinVarResult-Set>'
    )

    async def request_xml(provider, path, *, params):
        calls.append((provider, path, params))
        return rcv_xml if params.get("rettype") == "clinvarset" else vcv_xml

    async def request_json(provider, path, *, params):
        calls.append((provider, path, params))
        return {"esearchresult": {"idlist": ["14206"]}}

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_xml", request_xml
    )
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request", request_json
    )
    rcv = await execute_research(
        "cygnusx_clinvar_get", {"identifier": "RCV000000123.7", "identifier_type": "RCV"}
    )
    assert rcv["success"] is True, rcv
    assert rcv["data"]["result"]["record"]["record_type"] == "RCV"
    assert rcv["data"]["result"]["record"]["scv_accessions"] == [
        {"accession": "SCV000000456", "version": "2"}
    ]
    scv = await execute_research(
        "cygnusx_clinvar_get", {"identifier": "SCV000000456.2", "identifier_type": "SCV"}
    )
    assert scv["success"] is True, scv
    assert calls[-2][1] == "esearch.fcgi"
    assert calls[-2][2]["term"] == "SCV000000456[clv_acc]"
    assert calls[-2][2]["retmode"] == "json"
    variation = await execute_research(
        "cygnusx_clinvar_get", {"identifier": "14206", "identifier_type": "VariationID"}
    )
    assert variation["success"] is True, variation
    assert calls[-1][2]["id"] == "14206"
    assert calls[-1][2]["is_variationid"] == "true"
    assert calls[-1][2]["from_esearch"] == "true"


@pytest.mark.unit
async def test_clinvar_get_rejects_allele_id_without_http(monkeypatch):
    async def fail(*_args, **_kwargs):
        pytest.fail("unsupported Allele ID must not reach E-utilities")

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_xml", fail
    )
    result = await execute_research(
        "cygnusx_clinvar_get", {"identifier": "12345", "identifier_type": "AlleleID"}
    )
    assert result["success"] is False
    assert "not interchangeable" in result["summary"]


@pytest.mark.unit
async def test_clinvar_projection_preserves_core_fields_within_tool_budget(monkeypatch):
    import json
    import xml.etree.ElementTree as ET

    from cygnusx.application.services.research_data_service import _MAX_OUTPUT

    root = ET.Element("ClinVarResult-Set")
    archive = ET.SubElement(
        root,
        "VariationArchive",
        Accession="VCV000000001",
        Version="4",
        VariationID="1",
        NumberOfSubmissions="20",
        NumberOfSubmitters="8",
    )
    classifications = ET.SubElement(archive, "Classifications")
    for tag in ("GermlineClassification", "SomaticClinicalImpact", "OncogenicityClassification"):
        for _ in range(6):
            category = ET.SubElement(classifications, tag)
            ET.SubElement(category, "ReviewStatus").text = "reviewed"
            ET.SubElement(category, "Description").text = "Pathogenic " * 80
    for _ in range(10):
        ET.SubElement(archive, "ReviewStatus").text = "reviewed " * 80
        ET.SubElement(archive, "ClinVarSubmissionID", title="submitter " * 80)

    async def request_xml(*_args, **_kwargs):
        return root

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request_xml", request_xml
    )
    result = await execute_research("cygnusx_clinvar_get", {"vcv_accession": "VCV000000001"})
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()

    assert result["success"] is True
    assert len(payload) <= _MAX_OUTPUT
    projected = result["data"]["result"]
    assert projected["record"]["variation_id"] == "1"
    assert projected["classifications"]["germline"]
    assert projected["classifications"]["somatic_clinical_impact"]
    assert projected["classifications"]["oncogenicity"]
    assert projected["truncated"] is True
    assert "classifications" in projected["truncated_sections"]


@pytest.mark.unit
async def test_research_xml_request_rejects_dtd_and_entity_declarations(monkeypatch):
    import httpx

    async def response(_request):
        return httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            content=b'<!DOCTYPE x [<!ENTITY leak "unsafe">]><x>&leak;</x>',
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(response))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )
    with pytest.raises(ValueError, match="DTD and entity"):
        await _request_xml("clinvar", "efetch.fcgi", params={"id": "VCV000000001"})
    await client.aclose()


@pytest.mark.unit
async def test_reactome_version_uses_text_accept_and_is_included_in_result(monkeypatch):
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/database/version"):
            assert request.headers["accept"] == "text/plain"
            return httpx.Response(200, text="93")
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"stId": "R-HSA-1"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )

    result = await execute_research("cygnusx_pathway_get", {"pathway_id": "R-HSA-1"})

    assert result["success"] is True
    assert result["data"]["result"]["release"] == "93"
    assert len(requests) == 2
    await client.aclose()


@pytest.mark.unit
async def test_europe_pmc_article_uses_source_qualified_core_route(monkeypatch):
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"id": "29972563", "source": "MED", "title": "Example"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )

    result = await execute_research(
        "cygnusx_literature_get", {"source": "MED", "article_id": "29972563"}
    )

    assert result["success"] is True
    assert requests[0].url.path.endswith("/article/MED/29972563")
    assert requests[0].url.params["resultType"] == "core"
    await client.aclose()


@pytest.mark.unit
async def test_research_protein_sequence_rejects_html_success_response(monkeypatch):
    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>login</html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )

    result = await execute_research("cygnusx_protein_sequence", {"accession": "P04637"})

    assert result["success"] is False
    assert "non-FASTA" in result["summary"]
    await client.aclose()


@pytest.mark.unit
async def test_research_json_provider_stops_reading_after_response_budget(monkeypatch):
    stream = _CountingByteStream([b"1234", b"5678", b"unused"])

    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )
    with pytest.raises(ValueError, match="exceeds 6 bytes"):
        await _request("ensembl", "lookup/id/ENSG00000141510", max_response_bytes=6)

    assert stream.yielded == 2
    assert stream.closed is True
    await client.aclose()


@pytest.mark.unit
async def test_research_text_provider_stops_reading_after_response_budget(monkeypatch):
    stream = _CountingByteStream([b">entry\n", b"sequence", b"unused"])

    async def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/plain"}, stream=stream)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._client", lambda: client
    )
    monkeypatch.setattr("cygnusx.application.services.research_data_service._MAX_RESPONSE", 10)

    result = await execute_research("cygnusx_protein_sequence", {"accession": "P04637"})

    assert result["success"] is False
    assert "exceeds 2 MiB" in result["summary"]
    assert stream.yielded == 2
    assert stream.closed is True
    await client.aclose()


@pytest.mark.unit
async def test_atlas_directory_cache_coalesces_repeated_reads(monkeypatch):
    calls = 0

    async def read_directory(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {"experiments": [{"accession": "E-MTAB-1"}]}

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request", read_directory
    )
    from cygnusx.application.services.research_data_service import _atlas_directory

    first = await _atlas_directory("atlas")
    second = await _atlas_directory("atlas")

    assert first == second
    assert calls == 1


@pytest.mark.unit
async def test_open_targets_partial_graphql_errors_are_explicit(monkeypatch):
    async def partial_response(*_args, **_kwargs):
        return {"data": {"search": {"hits": []}}, "errors": [{"message": "field warning"}]}

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request", partial_response
    )

    result = await execute_research("cygnusx_target_search", {"query": "TP53"})

    assert result["success"] is True
    data = result["data"]["result"]
    assert data["partial"] is True
    assert data["warnings"]


@pytest.mark.unit
async def test_ensembl_lookup_rejects_returned_species_mismatch(monkeypatch):
    async def wrong_species(*_args, **_kwargs):
        return {"id": "AT1G01010", "species": "homo_sapiens"}

    monkeypatch.setattr(
        "cygnusx.application.services.research_data_service._request", wrong_species
    )

    result = await execute_research(
        "cygnusx_genome_lookup",
        {"species": "arabidopsis_thaliana", "identifier": "AT1G01010"},
    )

    assert result["success"] is False
    assert "does not match provider species" in result["summary"]


@pytest.mark.unit
async def test_gramene_literal_search_rejects_raw_query_syntax(monkeypatch):
    async def fail(*_args, **_kwargs):
        pytest.fail("raw Solr syntax must be rejected before provider access")

    monkeypatch.setattr("cygnusx.application.services.research_data_service._request", fail)

    result = await execute_research("cygnusx_plant_search", {"query": "gene:*"})

    assert result["success"] is False
    assert "literal terms" in result["summary"]
