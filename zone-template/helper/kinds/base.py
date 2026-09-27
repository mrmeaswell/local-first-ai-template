"""ActionKind interface.

rollback_mode declares what "undo" means for this kind (reference architecture, Section 6):
  auto_revert  the helper reverts automatically if verification fails or the admin doesn't confirm
  ttl_flag     the change is flagged with an expiry for a human to review; never auto-destroyed
  none         no rollback is possible; the action must be read-only or trivially safe
"""
ROLLBACK_MODES = {"auto_revert", "ttl_flag", "none"}


class ActionKind:
    rollback_mode: str = "none"
    param_schema: dict = {}   # declared fields from host-actions.yaml that this kind accepts

    def __init__(self, action_id: str, config: dict):
        if self.rollback_mode not in ROLLBACK_MODES:
            raise ValueError(f"{type(self).__name__}: invalid rollback_mode {self.rollback_mode!r}")
        unknown = set(config) - {"kind", "risk"} - set(self.param_schema)
        if unknown: raise ValueError(f"{action_id}: unknown fields {sorted(unknown)}")
        self.action_id, self.config = action_id, config

    def plan(self, params: dict) -> str: raise NotImplementedError       # dry run: exact change, no side effects
    def apply(self, params: dict) -> dict: raise NotImplementedError     # returns a handle
    def status(self, handle: dict) -> dict: raise NotImplementedError
    def rollback(self, handle: dict) -> dict: raise NotImplementedError
