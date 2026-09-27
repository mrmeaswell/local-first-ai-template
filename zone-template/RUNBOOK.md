# Runbook
- Reset data: `python api/app.py --seed ../examples/bay-log/seed.sql`
- Add a user: `python api/app.py --add-user NAME ROLE` (token printed once). Service users: `--add-user NAME service --owner HUMAN`
- Start: `python api/app.py`
- Health: `curl -H "Authorization: Bearer $TOKEN" localhost:8080/whoami`
- Evals: `python evals/run_evals.py` (isolated; never touches zone.db)
- Pending plans: `curl -H "Authorization: Bearer $TOKEN" localhost:8080/plans/<id>`
- Rollback AI change: (Phase 2) `control-mcp.rollback`

## Plan integrity and permissions
- A plan stores the exact change (for example `from_stage: Diagnosis → to_stage: Approval`) and a hash of the record. If the record changes in any way before confirm, confirm returns `409 record changed, re-plan` and the plan is marked `stale`. Request a new plan.
- The approval prompt shows every field that will be written, in full. Free-text fields over 2000 characters are rejected with 422. Confirm checks a hash of (action, params, summary shown, record snapshot) and refuses if anything changed.
- Who may read the audit log, read others' plans, confirm plans, and request host actions is set in `zone.yaml` under `permissions`. `service_roles` lists non-human roles that need a human `--owner`. If any of these names a role not in `roles`, the API refuses to start with a clear error.
- Host actions: `mcp/host-mcp` → `POST /plans {"action":"host_action"}` → `helper/service.py` on a Unix socket (`ZONE_HELPER_SOCK`, mode 0660). New kinds register themselves: add a module in `helper/kinds/` defining `KIND_NAME` and `KIND`.
- Zone extensions: an optional `zone_actions.py` at the zone root can add actions (`ACTIONS`) and read routes (`get()`). It must not edit the standard files.
