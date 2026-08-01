# AgentTeams Worker claim adapter

`claim_next.py` is a controller-agnostic Worker entrypoint. It retrieves the authenticated
Worker's Bridge inbox, atomically claims one `pending` Work Item, and prints a JSON task envelope
to stdout. It neither executes analysis tools nor contains OmicHub database, Docker, filesystem,
or shell capabilities.

The AgentTeams/HiClaw release-specific Worker resource can use the container image built from this
directory as a pre-skill command or invoke the script directly. Pass secrets through the target
platform's secret reference, never command-line arguments or a committed environment file:

```bash
export AGENTTEAMS_BRIDGE_BASE_URL=https://bridge.example.internal/v1
export AGENTTEAMS_WORKER_IDENTITY=quality-auditor
export AGENTTEAMS_BRIDGE_TOKEN=...
python3 integrations/agentteams/worker/claim_next.py
```

The command prints `{"assignment":null}` when no pending Work Item exists. A `409` from the Claim
endpoint means another Worker already claimed the item; run the command again to read the current
inbox. Use `--dry-run` only to inspect the next assignment without claiming it.
