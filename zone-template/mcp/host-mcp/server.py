"""host-mcp (standard, do not fork): the AI's ONLY door to host actions. Tools: request_plan, get_status.
There is no confirm tool. The confirm token is stripped and written to .pending/<plan_id> (0600) for the
orchestrator. A human always confirms. Identity comes from the signed-in ZONE_TOKEN; the API allows host
actions only for roles in zone.yaml permissions.host_actions."""
import os, pathlib, httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("ZONE_API", "http://127.0.0.1:8080")
PENDING = pathlib.Path(os.environ.get("ZONE_PENDING_DIR", pathlib.Path(__file__).resolve().parents[2] / ".pending"))
mcp = FastMCP("host-mcp")
def H(): return {"Authorization": f"Bearer {os.environ.get('ZONE_TOKEN', '')}"}


@mcp.tool()
def request_plan(action_id: str, params: dict | None = None) -> dict:
    """Propose a host action declared in host-actions.yaml. Returns plan_id and the full summary.
    Nothing happens until a human confirms outside this conversation."""
    r = httpx.post(f"{API}/plans", headers=H(), json={"action": "host_action", "params": {"action_id": action_id, "params": params or {}}})
    d = r.json()
    if r.status_code != 200: return {"error": d.get("error"), "status": r.status_code}
    PENDING.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(PENDING / str(int(d["plan_id"])), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: f.write(d.pop("confirm_token"))
    return {"plan_id": d["plan_id"], "summary": d["summary"]}


@mcp.tool()
def get_status(plan_id: int) -> dict:
    """Read a plan's status and result (pending, executed, expired, stale, failed)."""
    return httpx.get(f"{API}/plans/{plan_id}", headers=H()).json()


if __name__ == "__main__":
    mcp.run()
