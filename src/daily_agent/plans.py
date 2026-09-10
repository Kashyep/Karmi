from dataclasses import dataclass


@dataclass(frozen=True)
class PlanPolicy:
    plan_id: str
    display_name: str
    everyday_limit: int
    input_tokens: int
    output_tokens: int
    request_cost_cap_micro: int
    period_cost_cap_micro: int
    allowed_routes: tuple[str, ...]


# These values are deliberately synthetic development fixtures, never production tariffs.
SYNTHETIC_POLICIES: dict[str, PlanPolicy] = {
    "ananta": PlanPolicy("ananta", "Ananta", 20, 4_000, 512, 2_000, 20_000, ("fake-economy",)),
    "yanta": PlanPolicy("yanta", "Yanta", 100, 8_000, 1_024, 4_000, 80_000, ("fake-economy", "fake-balanced")),
    "trika": PlanPolicy("trika", "Trika", 250, 16_000, 2_048, 8_000, 200_000, ("fake-balanced",)),
    "part": PlanPolicy("part", "Part", 500, 32_000, 4_096, 16_000, 500_000, ("fake-balanced", "fake-advanced")),
}

