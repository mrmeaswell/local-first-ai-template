"""Core API: workflow engine, notes, knowledge base search, and audit. Stdlib only."""
import argparse, json, sqlite3, pathlib, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZONE = yaml.safe_load((ROOT / "zone.yaml").read_text())
DB = ROOT / "zone.db"  # overridden by --db
RANK = {r: i for i, r in enumerate(ZONE["roles"])}

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); return c

def whoami(c, headers):
    """Resolve the caller from a bearer token in the users table. Client-sent role headers are ignored."""
    auth = headers.get("Authorization", "")
    tok = auth[7:] if auth.startswith("Bearer ") else ""
    u = c.execute("SELECT name, role FROM users WHERE token=? AND token<>''", (tok,)).fetchone() if tok else None
    return (u["name"], u["role"]) if u else (None, None)

def init(seed=None):
    c = db()
    for f in sorted((ROOT / "schema").glob("*.sql")): c.executescript(f.read_text())
    if seed: c.executescript(pathlib.Path(seed).read_text())
    c.commit()

def audit(c, actor, action, rid, detail):
    c.execute("INSERT INTO events(actor,action,record_id,detail) VALUES(?,?,?,?)", (actor, action, rid, json.dumps(detail)))

class H(BaseHTTPRequestHandler):
    def send(self, code, obj):
        b = json.dumps(obj, default=dict).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); c = db()
        if u.path == "/zone": return self.send(200, ZONE)
        if u.path == "/records":
            s = f"%{q.get('q', [''])[0]}%"
            rows = c.execute("SELECT * FROM records WHERE title LIKE ? OR notes LIKE ? ORDER BY id", (s, s)).fetchall()
            return self.send(200, [dict(r) for r in rows])
        if m := re.fullmatch(r"/records/(\d+)", u.path):
            r = c.execute("SELECT * FROM records WHERE id=?", (m[1],)).fetchone()
            return self.send(200, dict(r)) if r else self.send(404, {"error": "not found"})
        if u.path == "/kb":
            s = f"%{q.get('q', [''])[0]}%"
            rows = c.execute("SELECT id,title,body FROM kb WHERE title LIKE ? OR body LIKE ?", (s, s)).fetchall()
            return self.send(200, [dict(r) for r in rows])
        if u.path == "/events":
            return self.send(200, [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT 50")])
        self.send(404, {"error": "no route"})

    def do_POST(self):
        u = urlparse(self.path); c = db()
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)) or "{}")
            if not isinstance(body, dict): raise ValueError
        except (ValueError, json.JSONDecodeError):
            return self.send(400, {"error": "body must be a JSON object"})
        actor, role = whoami(c, self.headers)
        if not actor: return self.send(401, {"error": "sign in required (Authorization: Bearer <token>)"})
        if role not in RANK: return self.send(403, {"error": "unknown role"})
        if m := re.fullmatch(r"/records/(\d+)/notes", u.path):
            if not isinstance(body.get("text"), str) or not body["text"].strip():
                return self.send(400, {"error": "text is required"})
            c.execute("UPDATE records SET notes = notes || ? || char(10), updated=CURRENT_TIMESTAMP WHERE id=?", (f"[{actor}] {body['text']}", m[1]))
            audit(c, actor, "add_note", int(m[1]), body); c.commit(); return self.send(200, {"ok": True})
        if m := re.fullmatch(r"/records/(\d+)/advance", u.path):
            r = c.execute("SELECT stage FROM records WHERE id=?", (m[1],)).fetchone()
            if not r: return self.send(404, {"error": "not found"})
            st = ZONE["stages"]; i = st.index(r["stage"])
            if i == len(st) - 1: return self.send(409, {"error": "already at final stage"})
            nxt = st[i + 1]; need = ZONE.get("gated_transitions", {}).get(nxt)
            if need and RANK[role] < RANK[need]: return self.send(403, {"error": f"moving to {nxt} requires {need}"})
            c.execute("UPDATE records SET stage=?, updated=CURRENT_TIMESTAMP WHERE id=?", (nxt, m[1]))
            audit(c, actor, "advance_stage", int(m[1]), {"from": r["stage"], "to": nxt}); c.commit()
            return self.send(200, {"ok": True, "stage": nxt})
        self.send(404, {"error": "no route"})

    def log_message(self, *a): pass

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--seed"); p.add_argument("--port", type=int, default=8080)
    p.add_argument("--reset", action="store_true"); p.add_argument("--db"); a = p.parse_args()
    if a.db: DB = pathlib.Path(a.db)
    if a.reset or a.seed: DB.unlink(missing_ok=True)
    init(a.seed); print(f"{ZONE['title']} API on http://127.0.0.1:{a.port}")
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
