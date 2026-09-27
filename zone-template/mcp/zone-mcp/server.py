"""zone-mcp: thin MCP wrappers over the Core API. Reads are open; writes are gated.

Phase 1 is read-only by default. Set ZONE_MCP_WRITES=1 to expose write tools (Phase 3).
Write tools have NO confirmation parameter: the model cannot approve its own writes.
Human confirmation is enforced by the MCP client (assistant.py) before any write tool runs.
The API identifies the caller by ZONE_TOKEN (the signed-in user's token), not by a claimed role."""
import os, httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("ZONE_API", "http://127.0.0.1:8080")
TOKEN = os.environ.get("ZONE_TOKEN", "")
H = {"Authorization": f"Bearer {TOKEN}"}
mcp = FastMCP("zone-mcp")
WRITE_TOOLS = {"add_note", "advance_stage"}

@mcp.tool()
def get_record(record_id: int) -> dict:
    """Get one record (e.g. a work order) by numeric ID, including stage and notes."""
    return httpx.get(f"{API}/records/{record_id}").json()

@mcp.tool()
def search_records(query: str = "") -> list:
    """Search records by keyword in title or notes. Empty query lists all."""
    return httpx.get(f"{API}/records", params={"q": query}).json()

@mcp.tool()
def search_kb(query: str) -> list:
    """Search the knowledge base (procedures). Cite the returned `id` in answers."""
    return httpx.get(f"{API}/kb", params={"q": query}).json()

if os.environ.get("ZONE_MCP_WRITES") == "1":
    @mcp.tool()
    def add_note(record_id: int, text: str) -> dict:
        """WRITE. Add a note to a record. The user will be asked to approve before it runs."""
        return httpx.post(f"{API}/records/{record_id}/notes", json={"text": text}, headers=H).json()

    @mcp.tool()
    def advance_stage(record_id: int) -> dict:
        """WRITE. Move a record to its next workflow stage. The user will be asked to approve before it runs."""
        return httpx.post(f"{API}/records/{record_id}/advance", headers=H).json()

if __name__ == "__main__":
    mcp.run()
