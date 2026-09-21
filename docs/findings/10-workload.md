# Task 10 — Workload: tool services and agent

## Built

- Four tool servers: `records`, `docs`, `search`, `notify` (notify = irreversible append log).
- Orchestrator with 30 explicit steps. Seeded plan implements 40/30/20/10 as 12/9/6/3. The matcher only picks among declared tools named in the instruction.
- Declaration `{records, search, notify}` is produced from the plan before step 1.
- Tests: clean full run completes 30 steps, `|S|=3`, write counts within ±1.

## Deviations

- Deterministic matcher, not a hosted model (NEW-MATTER).
- HTTP `/tools/call` rather than stdio MCP (NEW-MATTER).

## Manuscript impact

Declared services for long-multistep are `records`, `search`, `notify`. `docs` is the undeclared injection target. If the manuscript names a different triple, change the manuscript or this inventory — not both silently.
