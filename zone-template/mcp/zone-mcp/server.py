"""zone-mcp: thin MCP wrappers over the Core API.

- Reads are open to the signed-in user.
- Writes: the model can only REQUEST a plan (ZONE_MCP_WRITES=1) via request_add_note /
  request_advance_stage. There is no confirm tool.
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
    """Get one record (e.g. a work order) by its numeric ID, including stage and notes.
    Use ONLY with an ID the user stated or that search_records returned. Never guess an ID:
    if you only have a description (vehicle, customer, symptom), call search_records first."""
    return get(f"/records/{record_id}")

@mcp.tool()
def search_records(query: str = "") -> list:
    """Find records (e.g. work orders) by keyword in title or notes, such as a vehicle make/model,
    customer, or symptom. Use this whenever the user describes a record without giving its ID.
    Returns matching records with their IDs. Empty query lists all."""
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

def _request(action: str, params: dict) -> dict:
    """POST a plan, move the confirm token to the side channel, return only plan_id + summary."""
    r = httpx.post(f"{API}/plans", json={"action": action, "params": params}, headers=H())
    data = r.json()
    if r.status_code != 200: return {"error": data.get("error", "request failed"), "status": r.status_code}
    _save_token(data["plan_id"], data.pop("confirm_token"))
    return {"plan_id": data["plan_id"], "summary": data["summary"]}

# One narrow tool per write action, each with a strict typed schema.
# A generic request_plan(action, params: dict) let models guess the shape (e.g. params=3); typed
# arguments make a malformed call impossible to express. Approval works exactly as before:
# the model gets plan_id + summary only, and the human approves outside the conversation.
if os.environ.get("ZONE_MCP_WRITES") == "1":
    @mcp.tool()
    def request_add_note(record_id: int, text: str) -> dict:
        """Request adding a note to one record (e.g. a work order). Nothing is saved until the human
        approves it outside this conversation. Returns plan_id and a summary; you cannot approve it yourself."""
        return _request("add_note", {"record_id": record_id, "text": text})

    @mcp.tool()
    def request_advance_stage(record_id: int) -> dict:
        """Request moving one record to its next workflow stage. Nothing moves until the human approves
        it outside this conversation. Returns plan_id and a summary; you cannot approve it yourself."""
        return _request("advance_stage", {"record_id": record_id})

if __name__ == "__main__":
    mcp.run()
