from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from daily_agent.models import BugReport, uuid_str
from daily_agent.schemas import BugReportCreate
from daily_agent.security import Principal

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
MAX_SCREENSHOT_BYTES = 5_242_880  # 5 MB


def compute_bug_report_hash(
    category: str,
    description: str,
    diagnostics: dict[str, Any],
    screenshot_b64: str | None,
) -> str:
    payload = {
        "category": category,
        "description": description.strip(),
        "diagnostics": diagnostics,
        "screenshot": screenshot_b64,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _idempotency_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="idempotency key was reused with a different payload",
    )


def create_bug_report(
    session: Session,
    principal: Principal,
    body: BugReportCreate,
) -> tuple[BugReport, bool]:
    screenshot_b64 = body.screenshot.data_base64 if body.screenshot else None
    request_hash = compute_bug_report_hash(
        body.category,
        body.description,
        body.diagnostics.model_dump(),
        screenshot_b64,
    )

    # 1. Replay / idempotency check
    existing = session.scalar(
        select(BugReport).where(
            BugReport.user_id == principal.user_id,
            BugReport.client_report_id == body.client_report_id,
        )
    )
    if existing is not None:
        if existing.request_hash == request_hash:
            return existing, True
        raise _idempotency_conflict()

    # 2. Screenshot validation
    raw_screenshot: bytes | None = None
    screenshot_content_type: str | None = None
    if body.screenshot is not None:
        ct = body.screenshot.content_type.strip().lower()
        if ct not in ("image/png", "image/jpeg"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="unsupported screenshot content type; must be image/png or image/jpeg",
            )
        try:
            raw_screenshot = base64.b64decode(body.screenshot.data_base64, validate=True)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid base64 in screenshot data",
            ) from None

        if len(raw_screenshot) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="screenshot exceeds 5 MB limit",
            )

        if ct == "image/png" and not raw_screenshot.startswith(PNG_MAGIC):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="content_type is image/png but file magic does not match PNG",
            )
        if ct == "image/jpeg" and not raw_screenshot.startswith(JPEG_MAGIC):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="content_type is image/jpeg but file magic does not match JPEG",
            )
        screenshot_content_type = ct

    # 3. Rate limit check: max 3 new reports per rolling 24 hours per user
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=24)
    recent_reports = session.scalars(
        select(BugReport)
        .where(
            BugReport.user_id == principal.user_id,
            BugReport.created_at >= window_start,
        )
        .order_by(BugReport.created_at.asc())
    ).all()

    if len(recent_reports) >= 3:
        oldest_in_window = recent_reports[0]
        oldest_created = oldest_in_window.created_at
        if oldest_created.tzinfo is None:
            oldest_created = oldest_created.replace(tzinfo=UTC)
        reset_time = oldest_created + timedelta(hours=24)
        retry_after = max(1, int((reset_time - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="bug report rate limit exceeded (maximum 3 per 24 hours)",
            headers={"Retry-After": str(retry_after)},
        )

    # 4. Safe concurrent ticket allocation
    for attempt in range(10):
        try:
            with session.begin_nested():
                max_ticket = session.scalar(select(func.max(BugReport.ticket_number))) or 0
                ticket_number = max_ticket + 1
                report = BugReport(
                    id=uuid_str(),
                    account_id=principal.account_id,
                    user_id=principal.user_id,
                    ticket_number=ticket_number,
                    client_report_id=body.client_report_id,
                    request_hash=request_hash,
                    category=body.category,
                    description=body.description,
                    diagnostics=body.diagnostics.model_dump(),
                    screenshot=raw_screenshot,
                    screenshot_content_type=screenshot_content_type,
                    status="new",
                    created_at=now,
                    updated_at=now,
                )
                session.add(report)
                session.flush()
            session.commit()
            return report, False
        except IntegrityError:
            # Check if this user retried client_report_id in a race
            recovered = session.scalar(
                select(BugReport).where(
                    BugReport.user_id == principal.user_id,
                    BugReport.client_report_id == body.client_report_id,
                )
            )
            if recovered is not None:
                if recovered.request_hash == request_hash:
                    return recovered, True
                raise _idempotency_conflict() from None
            if attempt == 9:
                raise

    raise RuntimeError("failed to allocate bug report ticket after retries")


def get_bug_report(session: Session, principal: Principal, report_id: str) -> BugReport:
    report = session.get(BugReport, report_id)
    if (
        report is None
        or report.account_id != principal.account_id
        or report.user_id != principal.user_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bug report not found")
    return report
