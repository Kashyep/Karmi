from dataclasses import dataclass

# Budget accounting unit: every *_micro amount is millionths of one Indian rupee (INR). The
# free-model gateway settles zero-cost calls, but the labels stay so paid models can be added.
BUDGET_UNIT = "INR_MICRO"


@dataclass(frozen=True)
class PlanPolicy:
    plan_id: str
    display_name: str
    # Monthly list price in whole rupees (one price for everyone; no verification or discounts).
    price_inr: int
    everyday_limit: int
    # Daily token quota (estimated input plus output cap at admission, settled to actuals).
    daily_token_limit: int
    input_tokens: int
    output_tokens: int
    request_cost_cap_micro: int
    period_cost_cap_micro: int
    # Gateway model classes this plan may use, and the cheapest class it starts from.
    model_classes: tuple[str, ...]
    min_class: str


# Request/token quotas and cost caps are provisional development values pending the approved
# Revenue_model; prices are the owner's decision of record (Ananta 0, Yanta 149, Trika 399, Part 899).
# Owner decision 2026-10-21: no per-plan reply-length cap while models are free; every plan uses
# the gateway maximum (4,096 output tokens).
SYNTHETIC_POLICIES: dict[str, PlanPolicy] = {
    "ananta": PlanPolicy(
        "ananta", "Ananta", 0, 20, 40_000, 4_000, 4_096, 2_000, 20_000, ("economy",), "economy"
    ),
    "yanta": PlanPolicy(
        "yanta", "Yanta", 149, 100, 300_000, 8_000, 4_096, 4_000, 80_000,
        ("economy", "balanced"), "economy",
    ),
    "trika": PlanPolicy(
        "trika", "Trika", 399, 250, 800_000, 16_000, 4_096, 8_000, 200_000,
        ("economy", "balanced", "advanced"), "balanced",
    ),
    "parth": PlanPolicy(
        "parth", "Parth", 899, 500, 2_000_000, 32_000, 4_096, 16_000, 500_000,
        ("balanced", "advanced"), "balanced",
    ),
}
