"""Pure LinUCB scoring shared by the bundle self-test and BanditRoutingPolicy.

One implementation on purpose: the verifier's self-test proves that Karmi's scoring agrees
with the scores Parakh computed, which is only meaningful if the live policy uses the same
function.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from daily_agent.policy_artifacts.schema import LinUCBPolicyV1


def linucb_score(policy: LinUCBPolicyV1, model: str, features: Sequence[float]) -> float:
    """UCB score ``theta . x + alpha * sqrt(x^T A_inv x)`` for one arm."""
    arm = policy.arms[model]
    if len(features) != len(arm.theta):
        raise ValueError("feature dimension does not match the policy")
    mean = math.fsum(weight * value for weight, value in zip(arm.theta, features, strict=True))
    variance = math.fsum(
        features[i] * math.fsum(row[j] * features[j] for j in range(len(features)))
        for i, row in enumerate(arm.a_inv)
    )
    score = mean + policy.alpha * math.sqrt(max(0.0, variance))
    if not math.isfinite(score):
        raise ValueError("non-finite score")
    return score


def greedy_model(
    policy: LinUCBPolicyV1, models: Iterable[str], features: Sequence[float]
) -> str | None:
    """Highest-scoring scoreable model; ties break on the lexicographically smallest id.

    Models without an arm in the policy are ignored. ``None`` when nothing is scoreable.
    """
    best: tuple[float, str] | None = None
    for model in sorted(set(models)):
        if model not in policy.arms:
            continue
        score = linucb_score(policy, model, features)
        if best is None or score > best[0]:
            best = (score, model)
    return None if best is None else best[1]
