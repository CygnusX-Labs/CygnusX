"""Static/isolated transport contracts; no CLI, sockets or queue invocation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cygnusx.application.schemas.download import DownloadRequest

pytestmark = pytest.mark.unit


def test_aspera_is_rejected_instead_of_silently_mapped() -> None:
    with pytest.raises(ValidationError) as error:
        DownloadRequest(accession="SRR1", download_method="aspera")
    assert error.value.errors()[0]["type"] == "DOWNLOAD_METHOD_UNSUPPORTED"
