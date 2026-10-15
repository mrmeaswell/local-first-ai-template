"""baylog-mcp: read-only MCP tools over the live Bay Log API.

Thin wrappers only: every fact comes from Bay Log's own HTTP API (/api/tickets,
/api/board, /api/kb). No database access, no write tools. Results are trimmed so a
small local model on CPU gets just what it needs.

Env: BAYLOG_API (default http://127.0.0.1:8080)
"""
import os
import re

import httpx
from mcp.server.fastmcp import FastMCP

API = os.environ.get("BAYLOG_API", "http://127.0.0.1:8080").rstrip("/")
mcp = FastMCP("baylog-mcp")
TICKET_RE = re.compile(r"^T-\d{3,6}$", re.I)


def _get(path: str, **params):
    r = httpx.get(f"{API}{path}", params={k: v for k, v in params.items() if v is not None}, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _kb_view(e: dict) -> dict:
    return {
        "kb_id": f"KB-{e['entry_id']}",
        "category": e.get("category"),
        "symptom": e.get("trigger_or_symptom"),
        "likely_causes": e.get("likely_causes"),
        "diagnostic_steps": e.get("diagnostic_steps"),
        "common_resolution": e.get("common_resolution"),
        "instructor_note": e.get("notes"),
    }


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Get one repair order by its ticket ID (format "T-1001"): vehicle, current stage,
    complaint, notes and codes from each stage, what is blocking the next stage, and the
    full linked knowledge-base procedures. Use ONLY with an ID the student stated, that is
    shown as open on their screen, or that search_tickets returned. Never guess an ID."""
    tid = ticket_id.strip().upper()
    if not TICKET_RE.match(tid):
        return {"error": f"'{ticket_id}' is not a ticket ID (expected like T-1001). Use search_tickets."}
    t = _get(f"/api/tickets/{tid}")
    if t is None:
        return {"error": f"No ticket {tid}. Use search_tickets to find the right one."}
    kb_all = {e["entry_id"]: e for e in (_get("/api/kb") or [])}
    linked = [_kb_view(kb_all[k["entry_id"]]) for k in t.get("knowledge_links", []) if k["entry_id"] in kb_all]
    return {
        "ticket_id": t["ticket_id"],
        "vehicle": t["subject"]["label"],
        "mileage": t["subject"]["attributes"].get("mileage"),
        "title": t.get("title"),
        "priority": t.get("priority"),
        "assigned_to": t.get("assigned_to"),
        "current_stage": t["stage_label"],
        "next_stage": t.get("next_stage"),
        "blocking_next_stage": t.get("blockers", []),
        "current_stage_notes": t.get("stage_data", {}),
        "history": [{"stage": h["stage_label"], "notes": h["data"]} for h in t.get("history", [])],
        "parts_used": [f"{r['name']} x{r['quantity']}" for r in t.get("resources", [])],
        "linked_procedures": linked,
    }


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"[-_/]", "", str(text).lower()))


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 3 and w.endswith("s") else w


@mcp.tool()
def search_tickets(query: str) -> dict:
    """Find repair orders by keyword: vehicle make/model/year, plate, complaint, or stage.
    Use this whenever the student describes a vehicle or job without giving its ticket ID.
    Returns matching tickets with their IDs, best match first."""
    words = [_stem(w) for w in _norm(query).split() if len(w) > 1]
    scored = []
    for t in _get("/api/tickets") or []:
        hay = _norm(" ".join(str(x) for x in (
            t["ticket_id"], t["subject_label"], t.get("title"), t["stage_key"],
            *(t.get("subject_attributes") or {}).values())))
        score = sum(w in hay for w in words) if words else 1
        if score:
            scored.append((score, {"ticket_id": t["ticket_id"], "vehicle": t["subject_label"], "stage": t["stage_key"],
                                   "title": t.get("title"), "done": bool(t.get("done"))}))
    scored.sort(key=lambda x: -x[0])
    return {"results": [r for _, r in scored[:5]]} if scored else {"results": [], "note": f"No tickets match '{query}'."}


@mcp.tool()
def get_board() -> dict:
    """Overview of all open repair orders and the stage each one is in (the shop status board).
    Use for questions like "what's waiting on QC?" or "what's in the bay right now?"."""
    return {"open_tickets": [{"ticket_id": r["ticket_id"], "vehicle": r["subject"], "stage": r["stage"],
                              "title": r.get("title"), "priority": r.get("priority"), "assigned_to": r.get("assigned_to")}
                             for r in _get("/api/board") or []]}


@mcp.tool()
def search_kb(query: str) -> dict:
    """Search the shop knowledge base for diagnostic procedures by symptom, system or code
    (e.g. "misfire", "brake grinding", "no crank"). Returns procedures with a kb_id; cite the
    kb_id (e.g. KB-1) when you use one."""
    hits = _get("/api/kb", q=query) or []
    if not hits:  # fall back to individual words ("P0303 misfire" -> "misfire")
        seen = {}
        for w in re.split(r"\W+", query):
            if len(w) > 3:
                for e in _get("/api/kb", q=w) or []:
                    seen[e["entry_id"]] = e
        hits = list(seen.values())
    return {"results": [_kb_view(e) for e in hits]} if hits else \
        {"results": [], "note": f"No procedure matches '{query}'. Ask your instructor."}


if __name__ == "__main__":
    mcp.run()
