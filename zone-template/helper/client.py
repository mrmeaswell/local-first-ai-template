"""Tiny client for the privileged helper's Unix socket (one JSON request, one JSON reply)."""
import json, os, socket

SOCK = os.environ.get("ZONE_HELPER_SOCK", "/run/zone-helper/helper.sock")


class HelperError(Exception):
    def __init__(self, code, msg): super().__init__(msg); self.code, self.msg = code, msg


def call(op, **kw):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(120); s.connect(SOCK)
        s.sendall((json.dumps({"op": op, **kw}) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk: break
            buf += chunk
    r = json.loads(buf)
    if not r.get("ok"): raise HelperError(r.get("code", 500), r.get("error", "helper error"))
    return r["result"]
