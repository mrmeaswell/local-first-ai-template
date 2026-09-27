# host-mcp (standard, do not fork)
The AI's only path to host changes. Tools: `request_plan(action_id, params)` and `get_status(plan_id)`. There is no confirm tool; the confirm token never reaches the model.

Flow: host-mcp → Core API `POST /plans {"action":"host_action"}` (allowed only for roles in `permissions.host_actions`) → privileged helper over a Unix socket (`helper/service.py`, `ZONE_HELPER_SOCK`) → typed kind declared in `helper/host-actions.yaml`. A human confirms, and only then does the helper apply.

Run: `ZONE_TOKEN=... ZONE_API=http://127.0.0.1:8080 python mcp/host-mcp/server.py`
