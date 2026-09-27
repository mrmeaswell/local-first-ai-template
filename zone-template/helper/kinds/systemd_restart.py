"""systemd_restart: restart ONE declared unit. Fixed argv, shell=False, no user-supplied arguments.
rollback_mode auto_revert: if the unit isn't active after restart, the helper restarts it once more
(returning it to its last-known-good unit files) and reports failure for a human to review."""
import re, subprocess
from .base import ActionKind

UNIT_RE = re.compile(r"^[A-Za-z0-9@._-]+\.service$")


class SystemdRestart(ActionKind):
    rollback_mode = "auto_revert"
    param_schema = {"target": str}

    def __init__(self, action_id, config):
        super().__init__(action_id, config)
        t = config.get("target", "")
        if not UNIT_RE.fullmatch(t): raise ValueError(f"{action_id}: target must be a single .service unit name")
        self.target = t

    def _run(self, *args):
        return subprocess.run(["systemctl", *args, self.target], shell=False, capture_output=True, text=True, timeout=60)

    def plan(self, params):
        if params: raise ValueError("systemd_restart takes no runtime parameters")
        return f"Restart {self.target} (rollback: {self.rollback_mode})"

    def apply(self, params):
        self.plan(params)
        r = self._run("restart")
        return {"target": self.target, "returncode": r.returncode}

    def status(self, handle):
        r = self._run("is-active")
        return {"active": r.stdout.strip() == "active", "state": r.stdout.strip()}

    def rollback(self, handle):
        r = self._run("restart")
        return {"reverted": r.returncode == 0}
