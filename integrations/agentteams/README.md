# AgentTeams integration boundary

This directory contains the non-invasive AgentTeams integration defined in
`docs/26.7.30/AgentTeams_非侵入式多Agent协作编排实施方案.md`.

- `bridge/`: independently deployable REST adapter; it never imports OmicHub internals.
- `teams/`: AgentTeams role identities and capability boundaries.
- `skills/`: stable input/output and failure-handling contracts.
- `demo/`: repeatable preflight success/block and staging-only full workflow driver.

The Bridge covers Phase 1 operations (`list_flows`, `preflight`, task submit/get/cancel) and
Phase 2 foundations (role identity, human-gateway-issued scoped short-lived approvals,
idempotency, Case state persistence, quality decisions, evidence events, and delivery
manifests). The Agent 协作中心 UI reads and creates Cases through an authenticated OmicHub
server-side proxy. A production database-backed Bridge store remains follow-up work; it must
preserve the same Bridge contracts rather than reaching into OmicHub services or its database.

The browser never receives a Bridge secret or invokes Worker operations. OmicHub filters Case
reads by `requester_ref` using a server-only Manager identity; high-risk operations remain in
AgentTeams and the dedicated approval gateway.

For a separately deployed staging Bridge, run the safe preflight success and blocked demos from
`demo/README.md`. The full workflow mode requires explicit staging approval opt-in and a real
OmicHub demo task payload; it is not a substitute for human approval in production.
