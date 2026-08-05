# OmicHub AgentTeams sidecar deployment

> 协作档位、Bridge 前置条件和专业 Worker 边界请参阅
> `docs/configuration/多Agent协作配置指南.md`。

This Compose project is deliberately independent of `deploy/docker/docker-compose.yml`.
It deploys only the OmicHub Bridge: AgentTeams Controller, Matrix, MinIO, and optional
Higress remain AgentTeams-owned services and should join `omichub_agentteams_control`
through a dedicated gateway rather than the OmicHub application network.

## Run the Bridge

```bash
cp bridge.env.example bridge.env
cp gateway.env.example gateway.env
# Replace every placeholder with deployment-managed secrets.
docker network create omichub_bridge_gateway
docker compose -f docker-compose.agentteams.yml up --build -d
```

For a local development-only startup, `gateway.env` may use
`GATEWAY_ENVIRONMENT=development` with Matrix settings left empty. Production requires
deployment-managed Gateway and Matrix credentials; do not commit either environment file.

The host health port binds to `127.0.0.1:8088` by default. OmicHub reaches the Bridge over the
dedicated Docker network; do not change `AGENTTEAMS_BRIDGE_BIND_HOST` to `0.0.0.0` unless an
approved gateway/firewall policy requires a host-facing endpoint.

### Controlled multi-Worker acceptance check

For a non-production integration check, the `agentteams-acceptance` Compose profile starts three
separate constrained Workers for `agent-code`, `agent-viz`, and `agent-scrna`:

```bash
docker compose -f docker-compose.agentteams.yml \
  --profile agentteams-acceptance up --build -d
```

These Workers only poll their own Bridge identity. Their auto-complete behavior is explicitly
enabled only in this profile and accepts only read-only Work Items whose Case ID begins with
`agentteams-acceptance-`; all other Work Items remain for the configured official Worker skill
runtime. A successful acceptance Case contains, for each identity, ordered Case audit events
`worker.inbox_polled`, `work_item.claimed`, and `skill.finished`. Do not enable this profile for
production scientific work.

Use `.env.agentteams.example` as the separately managed environment template for the
version-specific AgentTeams Controller/Manager/Worker, Matrix, MinIO, and optional Higress
deployment. Those services must not be added to the OmicHub main Compose project.

The Bridge must be given a restricted OmicHub service identity. It may call only public
OmicHub HTTP endpoints and must not receive PostgreSQL, Redis, Docker socket, user-data
volume, or workflow-directory access. The external `omichub_bridge_gateway` is a dedicated
gateway network: expose only the OmicHub API gateway on it, never the database, Redis, or
Worker services. The `agentteams_control` network remains internal to AgentTeams services.

## Element collaboration room in OmicHub AI

After Matrix and Element Web are deployed and a user-accessible collaboration room exists,
configure its **public room URL** in `AGENTTEAMS_ELEMENT_URL` or in the administrator UI at
**Settings → AgentTeams Bridge → Element collaboration room URL**. Users can then select
**协作聊天室** from the existing OmicHub AI assistant page to open the Element room in a drawer;
the drawer also provides a new-window fallback for deployments that deny iframe embedding.

Do not place a Matrix password, access token, login token, or invite-secret URL in this field.
Element remains responsible for authentication, room membership, and message authorization;
OmicHub only exposes the configured public room URL to authenticated OmicHub users.

## AgentTeams wiring

- Team identities: `integrations/agentteams/teams/bioops-delivery.yaml`
- Skill contracts: `integrations/agentteams/skills/contracts.yaml`
- Bridge API: `http://omichub-agentteams-bridge:8080/v1`

Use a separate secret per Worker through `X-Bridge-Identity` and `X-Bridge-Token`.
Task submission and cancellation also require a short-lived, action-scoped approval token
issued only by the separate `approval-authority` gateway after a human approval card is
resolved. The Bridge writes its own append-only JSONL audit index; OmicHub remains
authoritative for task state, logs, and artifacts. The Bridge volume persists only Case
references, approval/audit evidence, and delivery manifests—never FASTQ, BAM, reference
genomes, or raw user files.

### Worker work inbox

An AgentTeams/HiClaw Worker must not list every Case and then self-select work. After its
official release-specific Team/Worker resource is created, configure the Worker to poll its own
Bridge identity against `GET /v1/work-items/assigned`. The endpoint returns only that identity's
`pending` or `in_progress` Work Items plus logical project/task references; it never exposes the
preflight input snapshot, raw task specification, requester identity, or another Worker's items.
For each `pending` item, first call
`POST /v1/cases/{case_id}/work-items/{work_item_id}/claim`. The Bridge atomically changes the
target Work Item to `in_progress`; a second Worker receives `409`, and the item can be reclaimed
only after its configured deadline expires. Then use the returned `case_id` and `work_item_id`
when calling the matching skill contract. Manager uses the normal Case APIs to assign work and
cannot call the Worker inbox or claim endpoints.

### OmicHub 上游身份

Bridge 调用 OmicHub 现有 HTTP API 时必须以一个专用、最小权限的 OmicHub 集成用户执行，
使任务归属、取消权限和审计记录可追溯。生产 `bridge.env` 在
`BRIDGE_OMICHUB_SERVICE_TOKEN`（Bearer）和 `BRIDGE_OMICHUB_API_KEY`（`X-API-Key`）之间
**只能配置一个**；推荐后者。通过该集成用户登录 OmicHub 后，在
`POST /api/v1/auth/api-keys` 创建专用 Key，写入部署管理的 `bridge.env`，明文只保存到
受控 secret store。不要复用个人用户 JWT，也不要把 Key 写入仓库、前端环境变量或
AgentTeams Worker 配置。建议该 Key 仅声明 `flows:read`、`tasks:read`、
`tasks:submit` 与 `tasks:cancel` 四个 scopes；OmicHub 会在对应 API 路径上执行此限制。

## OmicHub 协作中心代理

The browser never calls the Bridge directly and must never receive a Worker or Manager secret.
To enable the authenticated Case list, detail, event evidence, and Case creation page in OmicHub,
copy the tracked root `.env.example` block into the deployment-managed `.env`, then configure
the following server-side environment variables:

```bash
AGENTTEAMS_BRIDGE_ENABLED=true
AGENTTEAMS_BRIDGE_URL=http://omichub-agentteams-bridge:8080
AGENTTEAMS_BRIDGE_MANAGER_TOKEN=replace-with-bioops-manager-token
AGENTTEAMS_BRIDGE_DATA_STEWARD_TOKEN=replace-with-data-steward-token
AGENTTEAMS_BRIDGE_APPROVAL_TOKEN=replace-with-approval-authority-token
AGENTTEAMS_BRIDGE_WORKFLOW_OPERATOR_TOKEN=replace-with-workflow-operator-token
AGENTTEAMS_BRIDGE_TIMEOUT_SECONDS=10
```

Then bring the main OmicHub stack up with the optional network override. Start the Bridge stack
first so it creates `omichub_bridge_gateway`:

```bash
docker compose \
  -f deploy/docker/docker-compose.yml \
  -f deploy/agentteams/docker-compose.omichub-proxy.yml \
  up -d web
```

The main `deploy/docker/docker-compose.yml` does not join this network by default, so local and
existing deployments remain unchanged until this override is selected. OmicHub uses the Manager
token only inside its backend to filter Case records by the current authenticated user. On Case
creation it uses the separate Data Steward token solely to assign and run the read-only
`project-preflight` Work Item. Approval, submission, cancellation, quality decisions, and manifest
closure remain controlled by the dedicated AgentTeams identities and approval gateway.

The optional override explicitly preserves the Web service's existing app, data, Worker, and
Sandbox networks before adding `omichub_bridge_gateway`; do not replace it with a one-network
override, or the Web service will lose access to its existing dependencies.

When the Case owner confirms a `approval_pending` Case in OmicHub, the backend—not the browser—
uses the separate approval-authority identity to mint a short-lived, case-scoped approval token and
the separate workflow-operator identity to submit the task. The browser never receives either
identity secret or the approval token.

## Deployment preflight

Before starting a real staging demonstration, validate the deployment-managed files rather than
the committed templates. This command refuses `replace-*` / `change-me-*` values and missing
Worker identities; it does not start containers or submit any tasks.

```bash
python3 deploy/agentteams/preflight.py \
  --bridge-env deploy/agentteams/bridge.env \
  --omichub-env .env \
  --gateway-env deploy/agentteams/gateway.env
```

After the Bridge is running, add a read-only health probe. Use the host-reachable port or an
internal service URL appropriate for the environment:

```bash
python3 deploy/agentteams/preflight.py \
  --bridge-env deploy/agentteams/bridge.env \
  --omichub-env .env \
  --gateway-env deploy/agentteams/gateway.env \
  --check-health \
  --bridge-url http://127.0.0.1:8088 \
  --gateway-url http://127.0.0.1:8089
```

健康探针默认会在 Bridge 刚启动时重试 5 次；如需只检查一次可传
`--health-retries 1`。

## Matrix / Element round-trip smoke test

After the Bridge and Matrix Gateway health probes succeed, an operator can verify the real
room path without placing Matrix credentials in OmicHub. The command creates one disposable
Matrix room and posts one marker message, so it requires an explicit confirmation flag. The
Gateway Manager token can be supplied from the deployment secret store through the process
environment; it is never written by the script.

```bash
export AGENTTEAMS_GATEWAY_MANAGER_TOKEN="<deployment-managed-manager-token>"
python3 deploy/agentteams/matrix_gateway_smoke.py \
  --gateway-url http://127.0.0.1:8089 \
  --confirm-write
```

To verify Element-to-OmicHub return traffic, open the printed Element room URL in an authorized
Element session, send any message, then run the same command with a bounded wait window:

```bash
python3 deploy/agentteams/matrix_gateway_smoke.py \
  --gateway-url http://127.0.0.1:8089 \
  --wait-external-seconds 120 \
  --confirm-write
```

## AgentTeams / HiClaw Controller deployment

For a shared or production deployment, install the official AgentTeams Helm chart into a
separate Kubernetes namespace. Its default profile owns the AgentTeams Controller, Higress AI
Gateway, Tuwunel Matrix, MinIO, and Element Web. Keep the Controller API, Matrix homeserver,
MinIO, and Higress console private; expose only the authenticated Matrix/Element gateway and
Bridge endpoint required by the approved network policy.

```bash
helm repo add higress.io https://higress.io/helm-charts
helm repo update
helm install agentteams higress.io/agentteams \
  --namespace agentteams-system --create-namespace \
  --render-subchart-notes \
  --set credentials.llmApiKey="$AGENTTEAMS_LLM_API_KEY" \
  --set credentials.adminPassword="$AGENTTEAMS_ADMIN_PASSWORD" \
  --set gateway.publicURL="https://agentteams.example.internal"
```

The exact Worker, Team, Manager, and Human resource schema is release-specific. Apply the
role boundaries in `integrations/agentteams/teams/bioops-delivery.yaml` and the API contracts
in `integrations/agentteams/skills/contracts.yaml` when creating those official resources; do
not invent a local CRD format or mount the OmicHub Worker data volume into AgentTeams Workers.

### Control-plane acceptance gate

Before assigning a real Worker or starting the repeatable demo, apply the namespace-wide
default-deny policy after installing the official chart. Then add release-specific allow policies
only for Controller/Worker-to-Bridge traffic, Controller internal services, and the approved
Matrix/MinIO gateways. Do not allow direct egress to OmicHub PostgreSQL, Redis, Docker, or data
volumes.

```bash
kubectl apply -f deploy/agentteams/kubernetes/network-policy.default-deny.yaml
python3 deploy/agentteams/verify_control_plane.py \
  --namespace agentteams-system
```

`verify_control_plane.py` is read-only and controller-schema agnostic. It checks that the target
namespace exists, that a namespace-wide ingress/egress default-deny policy is active, and that
running Pods are non-privileged with no host-network, Docker socket, OmicHub data, database,
Redis, or workflow mounts. A failure is a deployment gate: fix the Helm values or explicit
allow policies before creating Team/Worker resources. The verifier deliberately does not claim
that a Controller release's Team CRD is valid; validate those resources with the official chart
version's CRDs and admission webhooks.
