"""共享参考资产与完整 tracks URI 的路径契约。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from cygnusx.core.exceptions import ValidationError
from cygnusx.tools.jbrowse import config as module

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("internal_dir", ["omichub_data", "cygnusx_data"])
def test_repository_jbrowse_assets_follow_reference_library(
    tmp_path: Path, internal_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference_dir = tmp_path / internal_dir / "reference"
    settings = SimpleNamespace(
        reference_genomes_yaml=str(reference_dir / "registry.yaml"), storage_path=str(tmp_path)
    )
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(module, "_data_root", lambda: tmp_path)
    config = module.ConfigManager("tool_configs/jbrowse/jbrowse_config.yaml").get_config()
    assert len(config.assemblies) == 2
    for assembly in config.assemblies:
        for value in (assembly.fasta, assembly.fai):
            path = Path(value)
            assert path.is_relative_to(tmp_path / internal_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture", encoding="utf-8")
            uri = module.to_tracks_uri(value)
            assert uri == "/tracks/" + path.relative_to(tmp_path).as_posix()
            assert (tmp_path / uri.removeprefix("/tracks/")).read_text() == "fixture"
        assert assembly.data_files["fasta"].path == assembly.fasta
        assert assembly.data_files["fasta"].index_path == assembly.fai
        assert Path(assembly.data_files["gff"].path).is_relative_to(tmp_path / internal_dir)
    track = config.preset_tracks["human_hg38"][0]
    assert track.file == str(
        tmp_path / internal_dir / "jbrowse/tracks/human_hg38/gencode.v50.basic.annotation.gff3"
    )
    assert config.auto_scan.scan_paths == [f"{tmp_path}/users/{{user_id}}"]
    assert config.upload.upload_dir == f"{tmp_path}/users/{{user_id}}/uploads/"


def test_absolute_jbrowse_assets_remain_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "jbrowse.yaml"
    path.write_text(
        "assemblies:\n  - id: custom\n    name: Custom\n    fasta: /shared/custom.fa\n    fai: /shared/custom.fa.fai\n",
        encoding="utf-8",
    )
    config = module.ConfigManager(path).get_config()
    assert config.assemblies[0].fasta == "/shared/custom.fa"
    assert config.assemblies[0].fai == "/shared/custom.fa.fai"


@pytest.mark.parametrize(
    "path", ["/other/reference.fa", "/shared/data/../private/ref.fa", "ref.fa"]
)
def test_tracks_uri_rejects_unmounted_paths(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_data_root", lambda: Path("/shared/data"))
    with pytest.raises(ValidationError, match="共享数据目录"):
        module.to_tracks_uri(path)
