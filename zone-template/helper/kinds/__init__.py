"""Typed host-action kinds. Every kind implements the ActionKind interface and declares its rollback semantics.
Kinds are discovered automatically: any module in this package that defines KIND_NAME and KIND is registered."""
import importlib, pkgutil
from .base import ActionKind, ROLLBACK_MODES

KINDS = {}
for _m in pkgutil.iter_modules(__path__):
    mod = importlib.import_module(f"{__name__}.{_m.name}")
    if hasattr(mod, "KIND_NAME"): KINDS[mod.KIND_NAME] = mod.KIND
