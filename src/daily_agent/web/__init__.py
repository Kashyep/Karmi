"""Owned-channel web/PWA shell primitives.

The shell deliberately has no provider or model selection surface.  The server
is authoritative for identity, plan entitlements, usage, and task state.
"""

from .admin_page import render_admin_page
from .manifest import TIER_PALETTES, build_manifest
from .shell import PLAN_LABELS, TaskState, WebTask, render_shell

__all__ = [
    "PLAN_LABELS",
    "TIER_PALETTES",
    "TaskState",
    "WebTask",
    "build_manifest",
    "render_admin_page",
    "render_shell",
]
