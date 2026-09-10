import json

from model_lab.core import (
    LabStore,
    candidate_record,
    coverage_metrics,
    exact_json_grade,
    fake_run,
    import_attempts,
    prompt_hash,
    render_report,
    router_recommendation,
    static_svg_chart,
    validate_cases,
)


def test_seed_suite_validates_and_candidate_export_is_protected(tmp_path):
    from pathlib import Path
    cases = [json.loads(line) for line in Path("benchmarks/seed_cases.jsonl").read_text(encoding="utf-8").splitlines()]
    assert validate_cases(cases) == []
    assert len(cases) == 60
    exported = candidate_record(cases[0])
    assert "evaluation" not in exported
    assert "split" not in exported
    assert exported["prompt_hash"] == prompt_hash(cases[0]["messages"])


def test_exact_json_and_html_escaping():
    assert exact_json_grade({"total": 3}, '{"total": 3}')[0] == "pass"
    assert exact_json_grade({"total": 3}, '{"total": 4}')[0] == "fail"
    html = render_report([{"case_id": "x", "response": "<script>alert(1)</script>"}], [{"case_id": "x", "status": "fail", "evidence": "bad"}], "html")
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html


def test_import_preserves_unknowns_and_quarantines_duplicates(tmp_path):
    source = tmp_path / "responses.jsonl"
    source.write_text('\n'.join([
        json.dumps({"case_id": "x", "response": "{}"}),
        json.dumps({"case_id": "x", "response": "{}"}),
        json.dumps({"case_id": "y"}),
    ]))
    attempts, quarantine = import_attempts(source, "fixture")
    assert len(attempts) == 1
    assert attempts[0]["latency_ms"] is None
    assert len(quarantine) == 2


def test_fake_run_is_bounded_and_sqlite_attempts_are_immutable(tmp_path):
    cases = [
        {"case_id": "a", "messages": [{"content": "x"}], "evaluation": {"method": "exact_json", "reference_answer": 1}},
        {"case_id": "b", "messages": [{"content": "y"}], "evaluation": {"method": "exact_json", "reference_answer": 2}},
        {"case_id": "c", "messages": [{"content": "z"}], "evaluation": {"method": "exact_json", "reference_answer": 3}},
    ]
    attempts = fake_run(cases, budget=2, fail_every=2)
    assert len(attempts) == 2 and attempts[1]["status"] == "failed"
    assert coverage_metrics(cases, attempts)["missing_cases"] == ["c"]
    store = LabStore(tmp_path / "lab.sqlite")
    store.add_attempt(attempts[0])
    try:
        store.add_attempt(attempts[0])
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate attempt was accepted")
    assert len(store.attempts()) == 1
    store.close()


def test_router_draft_and_svg_are_local_artifacts():
    attempts = [{"case_id": "a", "status": "completed"}]
    grades = [{"case_id": "a", "status": "pass", "evidence": "exact", "grader": "test"}]
    recommendation = router_recommendation([{"case_id": "a"}], attempts, grades, "fake-v1")
    assert recommendation["draft"] is True and recommendation["eligible"] is True
    assert "<svg" in static_svg_chart(grades)
