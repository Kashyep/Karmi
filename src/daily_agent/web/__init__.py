"""Owned-channel web/PWA shell primitives.

The shell deliberately has no provider or model selection surface.  The server
is authoritative for identity, plan entitlements, usage, and task state.
"""

from .shell import PLAN_LABELS, TaskState, WebTask, render_shell

__all__ = ["PLAN_LABELS", "TaskState", "WebTask", "render_shell"]
