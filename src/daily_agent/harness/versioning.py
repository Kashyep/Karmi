"""Versioned agent-harness data: prompt text and recovery settings.

The built-in harness is the prompt set Karmi shipped before learned policies existed. A
verified PolicyBundle may carry a replacement (``harness/prompts.json``); it only takes
effect while that bundle is the *active* live policy, never in shadow mode.
"""

from __future__ import annotations

import hashlib
import json

from daily_agent.policy_artifacts.schema import (
    HarnessBundleV1,
    HarnessPromptsV1,
    RecoveryPolicyV1,
)

HARNESS_VERSION = "karmi-harness-v1"

_BUILTIN_PROMPT_TEXT: dict[str, object] = {
    "intent_instructions": (
        "What is the primary action the user is asking the assistant to take?"
    ),
    "intent_criteria": {
        "query_memory": "The user is asking to retrieve, search, or recall saved facts.",
        "store_memory": "The user is providing a new fact or note to be remembered.",
        "create_task": (
            "The user is instructing the assistant to create a to-do, task, or reminder."
        ),
        "general_draft": "The user is asking for text generation, drafting, or general chat.",
    },
    "relevance_instructions_template": (
        "How relevant is `{note_ref}` to answering the user's query?"
    ),
    "relevance_criteria": ["Irrelevant", "Tangential", "Directly Relevant"],
}


def prompt_digest(prompts: dict[str, object]) -> str:
    canonical = json.dumps(prompts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


BUILTIN_PROMPTS = HarnessPromptsV1.model_validate(
    {
        "schema": "HarnessPromptsV1",
        "prompt_version": f"builtin-{prompt_digest(_BUILTIN_PROMPT_TEXT)}",
        **_BUILTIN_PROMPT_TEXT,
    }
)
BUILTIN_RECOVERY = RecoveryPolicyV1.model_validate(
    {"schema": "RecoveryPolicyV1", "max_provider_retries": 1, "fallback_to_local": True}
)
BUILTIN_HARNESS = HarnessBundleV1(prompts=BUILTIN_PROMPTS, recovery=BUILTIN_RECOVERY)


def relevance_instructions(prompts: HarnessPromptsV1, note_ref: str) -> str:
    """Plain placeholder substitution; bundle text is data and is never ``str.format``-ed."""
    return prompts.relevance_instructions_template.replace("{note_ref}", note_ref)
