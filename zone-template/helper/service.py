"""Privileged helper: runs declared host actions only, on a Unix socket (no TCP).

Runs as its own user (e.g. zonehelper). It is the only process that reads host secrets.
The Core API is its only client (socket mode 0660, group shared with the API).
Ops: plan(action_id, params) -> summary; apply(action_id, params) -> handle; status(action_id, handle)."""
import json, os, pathlib, socketserver, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import actions as HA

SOCK = os.environ.get("ZONE_HELPER_SOCK", "/run/zone-helper/helper.sock")
ACTIONS = HA.load(os.environ.get("ZONE_HOST_ACTIONS", HA.FILE))  # loaded once so per-action locks are shared


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            req = json.loads(self.rfile.readline())
            act = HA.get(req.get("action_id"), ACTIONS)
            op, params = req.get("op"), req.get("params") or {}
            if op == "plan": res = act.plan(params)
            elif op == "apply": res = act.apply(params)
            elif op == "status": res = act.status(req.get("handle") or {})
            else: raise ValueError(f"unknown op {op!r}")  # there is no rollback/teardown op for clients
            out = {"ok": True, "result": res}
        except HA.UndeclaredAction as e: out = {"ok": False, "code": 400, "error": str(e)}
        except ValueError as e: out = {"ok": False, "code": getattr(e, "http_code", 400), "error": str(e)}
        except Exception as e: out = {"ok": False, "code": 502, "error": f"{type(e).__name__}: {e}"}
        self.wfile.write((json.dumps(out) + "\n").encode())


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


if __name__ == "__main__":
    pathlib.Path(SOCK).unlink(missing_ok=True)
    old = os.umask(0o117)  # socket created as 0660
    srv = Server(SOCK, Handler); os.umask(old); os.chmod(SOCK, 0o660)
    print(f"helper listening on {SOCK} with actions {sorted(ACTIONS)}", flush=True)
    srv.serve_forever()
