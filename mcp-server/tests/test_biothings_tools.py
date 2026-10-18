import pytest

from client.api_client import CygnusXAPIClient
from tools.biothings import _call


@pytest.mark.asyncio
async def test_external_biothings_tool_forwards_to_authenticated_platform_api():
    class FakeAPI:
        async def biothings(self, database, action, arguments):
            return {
                "success": True,
                "summary": "MyGene search completed",
                "data": {"provider": "https://mygene.info/v3", "arguments": arguments},
            }

    response = await _call(
        FakeAPI(),
        "gene",
        "search",
        {"query": "AT3G52430", "species": "arabidopsis_thaliana"},
    )

    assert response["success"] is True
    assert response["data"]["arguments"]["species"] == "arabidopsis_thaliana"


@pytest.mark.asyncio
async def test_api_client_uses_fixed_biothings_route_and_payload(monkeypatch):
    client = CygnusXAPIClient()
    calls = []

    async def fake_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"success": True}

    monkeypatch.setattr(client, "_request", fake_request)
    result = await client.biothings(
        "variant", "search", {"query": "rs123", "assembly": "hg38"}
    )

    assert result == {"success": True}
    assert calls == [
        (
            "POST",
            "/biothings/variant/search",
            {"json": {"query": "rs123", "assembly": "hg38"}},
        )
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_api_client_rejects_uncontrolled_route_components():
    client = CygnusXAPIClient()
    with pytest.raises(ValueError, match="unsupported BioThings database"):
        await client.biothings("https://attacker.invalid", "search", {})
    with pytest.raises(ValueError, match="unsupported BioThings action"):
        await client.biothings("gene", "../metadata", {})
    await client.aclose()
