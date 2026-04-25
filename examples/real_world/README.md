# Real-World Scenarios

This folder contains modifiable starting points for production-like PMS usage.

Every maintained scenario:

- writes its artifacts under `PMS_DATA_DIR` (or a generated `.tmp/*` directory)
- emits one machine-readable `*.summary.json` file you can inspect or archive
- has a flow script for the practical path and a contract smoke for strict validation

<a id="scenario-dropin"></a>

## Drop In -> Start -> Go -> Extend -> Grow

Use the platform scenario runner:

```bash
./scripts/run_dropin_start_go_extend_grow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_dropin_contract_smoke.sh
```

To customize values, copy `examples/real_world/dropin.env.example` and export
its variables before running the script.

Summary artifact:

- `dropin-grow.summary.json`

<a id="scenario-team-handoff"></a>

## Team Handoff (Build -> Release)

Use the cross-team scenario runner:

```bash
./scripts/run_team_handoff_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_team_handoff_contract_smoke.sh
```

To customize values, copy `examples/real_world/team_handoff.env.example` and export
its variables before running the script.

Summary artifact:

- `team-handoff.summary.json`

<a id="scenario-incident-response"></a>

## Incident Response (Triage -> Mitigation -> Comms -> Postmortem)

Use the incident scenario runner:

```bash
./scripts/run_incident_response_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_incident_response_contract_smoke.sh
```

To customize values, copy `examples/real_world/incident_response.env.example` and
export its variables before running the script.

Summary artifact:

- `incident.summary.json`

<a id="scenario-user-start-go-observe"></a>

## User Bootstrap + Observability (Start -> Go -> Observe)

Use the user-centric onboarding/observability runner:

```bash
./scripts/run_user_start_go_observe_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_user_start_go_observe_contract_smoke.sh
```

To customize values, copy
`examples/real_world/user_start_go_observe.env.example` and export its
variables before running the script.

Optional API checkpoint against the default local server:

- `http://127.0.0.1:27541/api/v1/observability/overview`

Summary artifact:

- `user-start.summary.json`

<a id="scenario-operational-review"></a>

## Operational Review (Review -> Decide -> Continue)

Use the recurring operator-review runner:

```bash
./scripts/run_operational_review_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_operational_review_contract_smoke.sh
```

To customize values, copy
`examples/real_world/operational_review.env.example` and export its
variables before running the script.

Summary artifact:

- `operational-review.summary.json`

<a id="scenario-backlog-triage"></a>

## Backlog Triage (Prioritize -> De-duplicate -> Continue)

Use the backlog-triage runner:

```bash
./scripts/run_backlog_triage_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_backlog_triage_contract_smoke.sh
```

To customize values, copy
`examples/real_world/backlog_triage.env.example` and export its
variables before running the script.

Summary artifact:

- `backlog-triage.summary.json`

<a id="scenario-portfolio-steering"></a>

## Portfolio Steering (Roll Up -> Inspect -> Coordinate)

Use the multi-project steering runner:

```bash
./scripts/run_portfolio_steering_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_portfolio_steering_contract_smoke.sh
```

To customize values, copy
`examples/real_world/portfolio_steering.env.example` and export its
variables before running the script.

Summary artifact:

- `portfolio-steering.summary.json`

<a id="scenario-agent-execution-loop"></a>

## Agent Execution Loop (Plan -> Loop -> Prove -> Close)

Use the agent-loop scenario runner:

```bash
./scripts/run_agent_execution_loop_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_agent_execution_loop_contract_smoke.sh
```

To customize values, copy
`examples/real_world/agent_execution_loop.env.example` and export its
variables before running the script.

Summary artifact:

- `agent-loop.summary.json`

<a id="scenario-release-readiness"></a>

## Release Readiness (Launch Control)

Use the release-readiness scenario runner:

```bash
./scripts/run_release_readiness_flow.sh
```

Validate the same flow with strict output-contract checks:

```bash
./scripts/run_release_readiness_contract_smoke.sh
```

To customize values, copy
`examples/real_world/release_readiness.env.example` and export its variables
before running the script.

Summary artifact:

- `release-readiness.summary.json`
