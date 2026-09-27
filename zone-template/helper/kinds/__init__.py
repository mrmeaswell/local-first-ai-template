"""Typed host-action kinds. Every kind implements the ActionKind interface and declares its rollback semantics."""
from .base import ActionKind, ROLLBACK_MODES
from .systemd_restart import SystemdRestart

KINDS = {"systemd_restart": SystemdRestart}
