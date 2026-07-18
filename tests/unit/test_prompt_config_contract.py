from pathlib import Path

import yaml

from omichub.infrastructure.config.prompt_loader import PromptRegistry
from omichub.infrastructure.config.runtime_image_loader import RuntimeImageRegistryManager


def test_all_registered_prompt_files_exist():
    registry = PromptRegistry("data/prompts/registry.yaml")
    raw = yaml.safe_load(Path("data/prompts/registry.yaml").read_text(encoding="utf-8"))
    for key in raw["prompts"]:
        definition = registry.definition(key)
        assert definition is not None
        assert (registry.root / definition.file).is_file(), key


def test_all_enabled_agents_use_external_prompt_refs():
    site = yaml.safe_load(Path("data/OmicHub.yaml").read_text(encoding="utf-8"))
    registry = PromptRegistry("data/prompts/registry.yaml")
    for name in site["agents"]["enabled"]:
        agent = yaml.safe_load(Path(f"data/ai/{name}.yaml").read_text(encoding="utf-8"))
        assert "system_prompt" not in agent, name
        assert registry.get(agent["prompt_ref"]), name
        studio = agent.get("studio")
        assert isinstance(studio, dict) and studio.get("enabled") is True, name
        runtime = RuntimeImageRegistryManager("data/runtime_images.yaml").get_config()
        runtime.select(
            set(studio.get("required_capabilities", [])),
            "studio",
            studio["runtime_profile"],
        )
