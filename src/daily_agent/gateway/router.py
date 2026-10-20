"""Stage-1 rules router: classify the request, then order eligible registry models.

Pure functions only (no I/O, no randomness) so every routing decision is reproducible and
unit-testable. Health (breaker/cooldown) is injected as a predicate.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass

from daily_agent.gateway.registry import ModelRegistry, RegistryModel
from daily_agent.gateway.types import ModelClass, TaskType
from daily_agent.plans import PlanPolicy

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_LATIN = re.compile(r"[A-Za-z]")
_CODE = re.compile(
    r"```|\bdef \w+\(|traceback|stack trace|segmentation fault|"
    r"\b(python|javascript|typescript|java|c\+\+|rust|sql|html|css|bug|compile|compiler|"
    r"syntax error|regex|algorithm|function in)\b",
    re.IGNORECASE,
)
_MATHS = re.compile(
    r"\b(solve|integral|integrate|derivative|differentiate|equation|probability|matrix|"
    r"theorem|simplify|factori[sz]e|calculate|percentage|trigonometry|sin|cos|tan|log)\b|"
    r"\d\s*[-+*/^=]\s*[\dxyz(]|गणित|हल कर",
    re.IGNORECASE,
)
_SUMMARY = re.compile(r"\b(summari[sz]e|summary|tl;?dr|key points)\b|सारांश", re.IGNORECASE)
SUMMARY_MIN_CHARS = 1_500

_HARD = frozenset({TaskType.CODE, TaskType.MATHS, TaskType.SUMMARY})


def classify_task(text: str) -> TaskType:
    """Rule-based task type. Language wins over topic only when there is no code or maths cue."""
    if len(text) >= SUMMARY_MIN_CHARS and _SUMMARY.search(text):
        return TaskType.SUMMARY
    if _CODE.search(text):
        return TaskType.CODE
    if _MATHS.search(text):
        return TaskType.MATHS
    devanagari = len(_DEVANAGARI.findall(text))
    latin = len(_LATIN.findall(text))
    letters = devanagari + latin
    if devanagari and letters:
        share = devanagari / letters
        if share >= 0.6:
            return TaskType.HINDI
        if share >= 0.1:
            return TaskType.MIXED
    return TaskType.STUDY


@dataclass(frozen=True)
class RouteRequest:
    plan: PlanPolicy
    task_type: TaskType
    prompt_tokens: int
    max_output_tokens: int
    structured_output: bool = False
    # Regenerate/validation-failure: start one class above the plan floor.
    escalate: bool = False


def allowed_classes(plan: PlanPolicy) -> tuple[ModelClass, ...]:
    return tuple(sorted((ModelClass(name) for name in plan.model_classes), key=lambda c: c.rank))


def start_class(request: RouteRequest) -> ModelClass | None:
    """Cheapest allowed class for this request: plan floor, +1 for hard tasks or escalation."""
    classes = allowed_classes(request.plan)
    floor = ModelClass(request.plan.min_class)
    ladder = [c for c in classes if c.rank >= floor.rank]
    if not ladder:
        return None
    steps = int(request.task_type in _HARD) + int(request.escalate)
    return ladder[min(steps, len(ladder) - 1)]


def eligible_models(
    registry: ModelRegistry,
    request: RouteRequest,
    *,
    is_available: Callable[[RegistryModel], bool],
    exclude: Collection[str] = (),
    min_rank: int | None = None,
    min_class_floor: ModelClass | None = None,
) -> list[RegistryModel]:
    """Eligible models, cheapest class first, then best task score, then id (stable)."""
    classes = {c for c in allowed_classes(request.plan)}
    floor = min_class_floor if min_class_floor is not None else start_class(request)
    if floor is None:
        return []
    needed = request.prompt_tokens + request.max_output_tokens
    rank_floor = floor.rank if min_rank is None else max(floor.rank, min_rank)
    chosen = [
        m
        for m in registry.models
        if m.model_class in classes
        and m.model_class.rank >= rank_floor
        and m.context_length >= needed
        and (not request.structured_output or m.supports_structured_output)
        and m.action not in exclude
        and is_available(m)
    ]
    chosen.sort(key=lambda m: (m.model_class.rank, -m.score(request.task_type.value), m.action))
    return chosen
