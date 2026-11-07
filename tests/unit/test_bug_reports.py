from __future__ import annotations

from daily_agent.bug_reports import compute_bug_report_hash


def test_bug_report_hash_identical_body() -> None:
    diagnostics = {"os": "android", "app_version": "1.0"}
    b64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    h1 = compute_bug_report_hash(
        category="ui",
        description="Button not clicking",
        diagnostics=diagnostics,
        screenshot_b64=b64_data,
        screenshot_content_type="image/png",
    )
    h2 = compute_bug_report_hash(
        category="ui",
        description="Button not clicking",
        diagnostics=diagnostics,
        screenshot_b64=b64_data,
        screenshot_content_type="image/png",
    )
    assert h1 == h2


def test_bug_report_hash_different_screenshot_content_type() -> None:
    diagnostics = {"os": "android", "app_version": "1.0"}
    b64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    h_png = compute_bug_report_hash(
        category="ui",
        description="Button not clicking",
        diagnostics=diagnostics,
        screenshot_b64=b64_data,
        screenshot_content_type="image/png",
    )
    h_jpeg = compute_bug_report_hash(
        category="ui",
        description="Button not clicking",
        diagnostics=diagnostics,
        screenshot_b64=b64_data,
        screenshot_content_type="image/jpeg",
    )
    assert h_png != h_jpeg


def test_bug_report_hash_without_screenshot() -> None:
    diagnostics = {"os": "android", "app_version": "1.0"}
    h1 = compute_bug_report_hash(
        category="crash",
        description="App crashed",
        diagnostics=diagnostics,
        screenshot_b64=None,
    )
    h2 = compute_bug_report_hash(
        category="crash",
        description="App crashed",
        diagnostics=diagnostics,
        screenshot_b64=None,
    )
    assert h1 == h2
