from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent.config import Settings, get_settings
from daily_agent.gateway import Gateway, build_gateway
from daily_agent.models import Run
from daily_agent.ratelimit import SlidingWindowLimiter
from daily_agent.security import Principal, require_principal


def gateway_dependency(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Gateway:
    # One gateway per app so circuit-breaker and cooldown state survive across requests.
    gateway: Gateway | None = getattr(request.app.state, "gateway", None)
    if gateway is None:
        gateway = build_gateway(settings)
        request.app.state.gateway = gateway
    return gateway


def limited_principal(
    request: Request,
    principal: Principal = Depends(require_principal),
    settings: Settings = Depends(get_settings),
) -> Principal:
    limiter: SlidingWindowLimiter | None = getattr(request.app.state, "limiter", None)
    if limiter is None:
        limiter = SlidingWindowLimiter(limit=settings.rate_limit_per_minute)
        request.app.state.limiter = limiter
    retry_after = limiter.check(principal.user_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "too many requests; slow down"},
            headers={"Retry-After": str(retry_after)},
        )
    return principal


def own_run(session: Session, principal: Principal, run_id: str) -> Run:
    run = session.scalar(
        select(Run).where(
            Run.id == run_id,
            Run.account_id == principal.account_id,
            Run.user_id == principal.user_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="reply not found")
    return run
