"""zone-mcp: thin MCP wrappers over the Core API. Reads are open; writes are gated.
Phase 1 is read-only by default. Set ZONE_MCP_WRITES=1 to expose write tools (Phase 3)."""
import os, httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("ZONE_API", "http://127.0.0.1:8080")
USER, ROLE = os.environ.get("ZONE_USER", "assistant"), os.environ.get("ZONE_ROLE", "student")
mcp = FastMCP("zone-mcp")
H = {"X-User": USER, "X-Role": ROLE}

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
    def add_note(record_id: int, text: str, confirmed: bool = False) -> dict:
        """Add a note to a record. Requires confirmed=true after the user explicitly agrees."""
        if not confirmed: return {"needs_confirmation": f"Add note to #{record_id}: {text!r}?"}
        return httpx.post(f"{API}/records/{record_id}/notes", json={"text": text}, headers=H).json()

    @mcp.tool()
    def advance_stage(record_id: int, confirmed: bool = False) -> dict:
        """Move a record to its next workflow stage. Requires confirmed=true after the user agrees."""
        if not confirmed: return {"needs_confirmation": f"Advance #{record_id} to the next stage?"}
        return httpx.post(f"{API}/records/{record_id}/advance", headers=H).json()

if __name__ == "__main__":
    mcp.run()
