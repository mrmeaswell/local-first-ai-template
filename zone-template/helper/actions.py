"""Loads host-actions.yaml. Anything not declared there does not exist."""
import pathlib, yaml
from kinds import KINDS

FILE = pathlib.Path(__file__).with_name("host-actions.yaml")


class UndeclaredAction(Exception): pass


def load(path=FILE):
    spec = yaml.safe_load(pathlib.Path(path).read_text()) or {}
    out = {}
    for aid, cfg in (spec.get("actions") or {}).items():
        if "cmd" in cfg or "argv" in cfg or "shell" in cfg:
            raise ValueError(f"{aid}: raw commands are not allowed; use a typed kind")
        kind = KINDS.get(cfg.get("kind"))
        if not kind: raise ValueError(f"{aid}: unknown kind {cfg.get('kind')!r}; known: {sorted(KINDS)}")
        out[aid] = kind(aid, cfg)
    return out


def get(action_id, actions=None):
    actions = load() if actions is None else actions
    if action_id not in actions: raise UndeclaredAction(f"{action_id!r} is not declared in host-actions.yaml")
    return actions[action_id]
