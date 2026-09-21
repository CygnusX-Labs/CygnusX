# OmicHub Agent Instructions

## Deployment and Image Rules

These rules apply to every Agent that changes files under `deploy/`, `data/ai/`,
`tool_configs/terminal/`, or image-related defaults in `src/` and `.env.example`.

### Source of truth

- The canonical image inventory is `deploy/image-mapping.yaml`.
- The human-readable explanation and update procedure is
  `deploy/docker/README.md`.
- Do not update only a Dockerfile, only a YAML registry, or only the Makefile.
  An image tag is valid only when all registered references agree.
- Do not use `latest` for a published image. Keep the image name and tag explicit.

### Current image mapping

| Image purpose | Image | Build definition | Configuration |
|---|---|---|---|
| General analysis | `cygnusx-analysis:core-v0.0.2dev` | `deploy/runtime-images/core.Dockerfile` | `data/ai/runtime_images.yaml`, `data/ai/studio.yaml` |
| Plotting | `cygnusx-analysis:plot-v0.0.2dev` | `deploy/runtime-images/plot.Dockerfile` | `data/ai/runtime_images.yaml`, `data/ai/studio.yaml` |
| Single-cell analysis | `cygnusx-analysis:scrna-v0.0.3dev` | `deploy/runtime-images/scrna.Dockerfile` | `data/ai/runtime_images.yaml`, `data/ai/studio.yaml`, `.env.example`, `src/cygnusx/core/config.py` |
| Studio base | `cygnusx-sandbox-base:v0.0.2dev` | `deploy/studio/base.Dockerfile` | `data/ai/studio.yaml` |
| Studio bioinformatics | `cygnusx-sandbox-bio:v0.0.2dev` | `deploy/studio/bio.Dockerfile` | `data/ai/runtime_images.yaml`, `data/ai/studio.yaml` |
| Studio browser/office | `cygnusx-sandbox-browser-office:v0.0.2dev` | `deploy/studio/browser-office.Dockerfile` | `data/ai/runtime_images.yaml`, `data/ai/studio.yaml` |
| Copilot execution sandbox | `cygnusx-sandbox-copilot:v0.0.2dev` | `deploy/sandbox/Dockerfile` | `src/cygnusx/core/config.py` |
| Terminal base | `cygnusx-sandbox-terminal:v0.0.2dev` | `tool_configs/terminal/docker/Dockerfile` | `tool_configs/terminal/terminal_images.yaml` |
| Terminal child images | `cygnusx-sandbox-{rnaseq,scrna,gatk,ggplot2,assembly,metagenomics}:v0.0.2dev` | matching `Dockerfile.*` files | `tool_configs/terminal/terminal_images.yaml` |

The full 14-image list, including exact tags, is always maintained in
`deploy/image-mapping.yaml`; do not duplicate a second authoritative list.

### Runtime inheritance

- `plot.Dockerfile` extends `cygnusx-analysis:core-${CYGNUSX_IMAGE_TAG}`.
- `scrna.Dockerfile` extends `cygnusx-analysis:plot-${CYGNUSX_IMAGE_TAG}`.
- `deploy/studio/bio.Dockerfile` extends the Studio base image.
- `deploy/studio/browser-office.Dockerfile` extends the Studio bio image.
- Terminal child images extend `cygnusx-sandbox-terminal:v0.0.2dev`.
- A child image tag may be independent from its base tag, but the base image must
  exist locally before the child build starts.

### Agent to runtime selection

The selection chain is:

`data/ai/<agent>.yaml` `studio.runtime_profile`
-> `data/ai/runtime_images.yaml` `profiles.<profile>.image`
-> the local Docker image.

The enabled Agent groups currently resolve as follows:

- `analysis-core`: `agent-atacseq`, `agent-cloud-ops`, `agent-code`, `agent-data`,
  `agent-delivery`, `agent-explorer`, `agent-mcp-builder`, `agent-qc`,
  `agent-rnaseq`, `agent-router`, `agent-skill-builder`, `agentteams-manager`,
  and `shania`.
- `analysis-plot`: `agent-viz`.
- `analysis-scrna`: `agent-general`, `agent-scrna`, `agent-scrna-advanced`,
  `agent-scrna-integration`, and `agent-scrna-upstream`.

Keep the profile name in Agent YAML. Do not replace it with a hard-coded image,
and do not change a model/provider binding while updating an image unless that is
an explicitly requested, separate change.

## Image Tag Update Checklist

When an image is rebuilt or its tag changes, follow this order:

1. Update the final image name/tag in `deploy/image-mapping.yaml`.
2. Update every file listed in that image's `config_files` entry. For analysis
   images this normally includes `data/ai/runtime_images.yaml` and
   `data/ai/studio.yaml`; for terminal images it includes
   `tool_configs/terminal/terminal_images.yaml`.
3. Update build inputs and tag variables:
   - `deploy/runtime-images/build.sh` for `core`, `plot`, and `scrna` tags;
   - `deploy/studio/build.sh` for Studio sandbox tags;
   - `Makefile` build, inspect, and expected-image lists;
   - `.env.example` for `CYGNUSX_IMAGE_TAG`, `CYGNUSX_SCRNA_IMAGE_TAG`, and
     derived image variables;
   - `src/cygnusx/core/config.py` when a hard-coded Copilot or MAS image is
     involved.
4. If a parent image changed, rebuild all child images that inherit from it.
5. Run the static checks before starting Studio or any sandbox:

   ```bash
   make validate-image-mapping
   ```

   This validates the 14-image inventory and the enabled Agent profile mapping.
   On a host with Docker access, also run:

   ```bash
   python deploy/validate_image_mapping.py --check-local
   ```

6. Build the complete sandbox set with:

   ```bash
   make docker-build-sandboxes
   ```

   `docker-build-sandboxes` depends on `validate-image-mapping`, so a stale
   mapping must stop the build before Docker tries to pull a missing image.
   `docker-reload` has the same validation as its first prerequisite, so a
   failed mapping check prevents network creation, container cleanup, and all
   service startup steps.

## Deployment Safety

- The runtime containers use UID/GID `10001:10001` and group
  `cygnusx-sandbox`; do not switch them to root to work around a mount problem.
- Keep `/workspace/input` read-only and `/workspace/output` writable according
  to the existing mount contract. Validate permissions with the probes in
  `deploy/docker/README.md` after changing runtime users or mounts.
- A local Docker daemon may be unavailable in CI or the development sandbox.
  In that case, report that `--check-local` could not run; do not treat a static
  configuration pass as proof that an image exists in the deployment registry.
- For the original `pull access denied` failure, check both the exact image tag
  and whether the image was built locally. A missing tag is a configuration
  synchronization error, not an R/Seurat package error.

## Router Packaging and Dispatch Contract

The Router is an LLM classifier, not a frontend keyword router and not a
server-side domain rules engine. Preserve this separation when changing routing:

- The runtime entrypoint is `ChatService._route_to_agent()` in
  `src/cygnusx/application/services/chat_service.py`.
- The LLM receives `ROUTER_SYSTEM_PROMPT` plus a runtime-generated candidate
  catalog from `AgentTeamsCapabilityRegistry.snapshot()["chat_router_catalog"]`.
  Do not maintain a second hard-coded Agent list in the Router.
- Candidate descriptions, `capability_scope`, `capability_tags`,
  `routing_hints`, `routing_notes`, `default_role`, and persona summaries are
  the LLM's routing evidence. Domain-specific guidance belongs in
  `data/ai/agent_ability.yaml`, `data/ai/<agent>.yaml`, or
  `data/ai/domains/*.yaml`, not in post-hoc keyword overrides.
- The model must return one JSON object with `agent_id`, `reason`,
  `collaboration_intent`, `confidence`, and the optional handoff/fan-out fields.
  `_extract_route_json()` tolerates surrounding reasoning, while
  `normalize_decision()` only validates the schema and candidate IDs.
- The backend may reject an unknown/unavailable target and fall back to the
  runtime general candidate. It must not replace a valid LLM target merely
  because the user text contains a domain keyword, file extension, or visual
  request. Domain selection remains the LLM's decision.

### Router output budget

`ROUTER_MAX_TOKENS` is currently `10000`. This is intentional: DeepSeek V4 can
emit reasoning tokens even when `deep_thinking=False`; with a 200-token budget,
the model frequently reached `finish_reason=length` before emitting its JSON and
the normal validator then appeared to route everything to `agent-general`.
The production call and `scripts/evaluate_router_20.py` must use the same
constant. Keep reasoning chunks out of `route_text`; only final text should be
parsed as the routing JSON.

Do not lower this budget without a live regression run. Also check provider/model
context limits before raising it further: the injected catalog and flow catalog
already consume several thousand prompt tokens. The provider's generic
`OpenAICompatibleProvider` has no hidden 200-token cap; the important limits are
the explicit Router budget, the model's context/output limits, and the JSON
candidate validation described above.

### Router evaluation

Use the project interpreter, not the host `python3`:

```bash
.venv/bin/python scripts/evaluate_router_20.py
```

The script prints the original question, `model_agent`, validated `final_agent`,
`intent`, `confidence`, and `reason`. `expected_agent` is only an evaluation
benchmark; it must never be used to alter production routing. A missing or
truncated model JSON is a failed model call and will be reported as the normal
general fallback, not silently repaired by keyword rules.
