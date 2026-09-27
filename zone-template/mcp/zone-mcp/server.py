"""zone-mcp: thin MCP wrappers over the Core API.

- Reads are open to the signed-in user.
- Writes: the model can only REQUEST a plan (ZONE_MCP_WRITES=1). There is no confirm tool.
  The API returns a one-time confirm token; this server strips it from the tool result and writes it to
  a side channel (.pending/<plan_id>, mode 0600) that only the orchestrator (assistant.py) reads.
  The model never sees the token, so it cannot approve its own writes.
- Identity: forwards the signed-in user's ZONE_TOKEN. There is no fixed role.
"""
import os, pathlib, httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("ZONE_API", "http://127.0.0.1:8080")
PENDING = pathlib.Path(os.environ.get("ZONE_PENDING_DIR", pathlib.Path(__file__).resolve().parents[2] / ".pending"))
mcp = FastMCP("zone-mcp")

def H(): return {"Authorization": f"Bearer {os.environ.get('ZONE_TOKEN', '')}"}
def get(path, **params):
    r = httpx.get(f"{API}{path}", params=params, headers=H()); return r.json()

@mcp.tool()
def get_record(record_id: int) -> dict:
    """Get one record (e.g. a work order) by numeric ID, including stage and notes."""
    return get(f"/records/{record_id}")

@mcp.tool()
def search_records(query: str = "") -> list:
    """Search records by keyword in title or notes. Empty query lists all."""
    return get("/records", q=query)

@mcp.tool()
def search_kb(query: str) -> list:
    """Search the knowledge base (procedures). Cite the returned `id` in answers."""
    return get("/kb", q=query)

def _save_token(plan_id: int, token: str):
    PENDING.mkdir(mode=0o700, exist_ok=True)
    f = PENDING / str(int(plan_id))
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh: fh.write(token)

if os.environ.get("ZONE_MCP_WRITES") == "1":
    @mcp.tool()
    def request_plan(action: str, params: dict) -> dict:
        """Request a change. Nothing happens until the human approves it outside this conversation.
        action: "add_note" (params: record_id, text) or "advance_stage" (params: record_id).
        Returns plan_id and a summary. Tell the user what you requested; you cannot approve it yourself."""
        r = httpx.post(f"{API}/plans", json={"action": action, "params": params}, headers=H())
        data = r.json()
        if r.status_code != 200: return {"error": data.get("error", "request failed"), "status": r.status_code}
        _save_token(data["plan_id"], data.pop("confirm_token"))
        return {"plan_id": data["plan_id"], "summary": data["summary"]}

if __name__ == "__main__":
    mcp.run()
