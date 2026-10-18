"""Reviewed model registry (``model-registry.v1``), produced offline by Parakh.

Only zero-price models are accepted while Karmi runs on free models. A registry that lists a
non-zero price, an unknown provider, or claims private-data eligibility without explicit
no-training terms fails to load rather than being partially trusted.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib import resources
from pathlib import Path
from typing import Any

from daily_agent.gateway.types import ModelClass

SCHEMA_VERSION = "model-registry.v1"
KNOWN_PROVIDERS = frozenset({"openrouter", "opencode"})


class RegistryError(ValueError):
    """The registry file is malformed or violates a Karmi safety rule."""


@dataclass(frozen=True)
class RegistryModel:
    model_id: str
    provider: str
    model_class: ModelClass
    context_length: int
    private_data_allowed: bool
    supports_structured_output: bool
    scores: Mapping[str, float]
    snapshot_date: str

    @property
    def action(self) -> str:
        """Parakh action id (``provider/model``) for routing evidence."""
        return f"{self.provider}/{self.model_id}"

    def score(self, task_type: str) -> float:
        """Measured score for the task type; falls back to the mean of what was measured."""
        if task_type in self.scores:
            return self.scores[task_type]
        return sum(self.scores.values()) / len(self.scores) if self.scores else 0.0


@dataclass(frozen=True)
class ModelRegistry:
    models: tuple[RegistryModel, ...]
    snapshot_date: str
    provisional: bool

    def get(self, provider: str, model_id: str) -> RegistryModel | None:
        for model in self.models:
            if model.provider == provider and model.model_id == model_id:
                return model
        return None

    def for_providers(self, providers: frozenset[str]) -> ModelRegistry:
        return ModelRegistry(
            tuple(m for m in self.models if m.provider in providers),
            self.snapshot_date,
            self.provisional,
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def _zero_price(value: Any, field: str, model_id: str) -> None:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RegistryError(f"{model_id}: {field} is not a number") from None
    _require(price == 0, f"{model_id}: {field} is non-zero; only free models are allowed")


def parse_registry(document: Any) -> ModelRegistry:
    _require(isinstance(document, dict), "registry must be a JSON object")
    _require(
        document.get("schema_version") == SCHEMA_VERSION, "unsupported registry schema_version"
    )
    snapshot = document.get("snapshot_date")
    _require(isinstance(snapshot, str) and len(snapshot) == 10, "snapshot_date must be YYYY-MM-DD")
    rows = document.get("models")
    _require(isinstance(rows, list), "models must be a list")
    models: list[RegistryModel] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        _require(isinstance(row, dict), "model entry must be an object")
        model_id = row.get("model_id")
        provider = row.get("provider")
        _require(
            isinstance(model_id, str) and bool(model_id), "model_id must be a non-empty string"
        )
        _require(provider in KNOWN_PROVIDERS, f"{model_id}: unknown provider {provider!r}")
        _require((provider, model_id) not in seen, f"{model_id}: duplicate entry")
        seen.add((provider, model_id))
        _zero_price(row.get("prompt_price_usd"), "prompt_price_usd", model_id)
        _zero_price(row.get("completion_price_usd"), "completion_price_usd", model_id)
        try:
            model_class = ModelClass(row.get("class"))
        except ValueError:
            raise RegistryError(f"{model_id}: unknown class {row.get('class')!r}") from None
        context = row.get("context_length")
        _require(
            isinstance(context, int) and not isinstance(context, bool) and context > 0,
            f"{model_id}: context_length must be a positive integer",
        )
        private = row.get("private_data_allowed")
        _require(isinstance(private, bool), f"{model_id}: private_data_allowed must be a boolean")
        if private:
            _require(
                row.get("data_terms") == "no_training",
                f"{model_id}: private data requires explicit data_terms 'no_training'",
            )
        structured = row.get("supports_structured_output", False)
        _require(
            isinstance(structured, bool),
            f"{model_id}: supports_structured_output must be a boolean",
        )
        scores = row.get("scores", {})
        _require(isinstance(scores, dict), f"{model_id}: scores must be an object")
        for key, value in scores.items():
            _require(
                isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1,
                f"{model_id}: score {key!r} must be within 0..1",
            )
        models.append(
            RegistryModel(
                model_id=model_id,
                provider=provider,
                model_class=model_class,
                context_length=context,
                private_data_allowed=private,
                supports_structured_output=structured,
                scores=dict(scores),
                snapshot_date=snapshot,
            )
        )
    return ModelRegistry(tuple(models), snapshot, bool(document.get("provisional", True)))


def load_registry(path: Path | None = None) -> ModelRegistry:
    """Load the registry at ``path`` or the packaged seed."""
    try:
        if path is None:
            text = (
                resources.files("daily_agent.gateway")
                .joinpath("data/model_registry.json")
                .read_text(encoding="utf-8")
            )
        else:
            text = path.read_text(encoding="utf-8")
        document = json.loads(text)
    except (OSError, ValueError) as exc:
        raise RegistryError(f"model registry cannot be read: {exc}") from exc
    return parse_registry(document)
