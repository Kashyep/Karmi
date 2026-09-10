import json

from model_lab.core import candidate_record, exact_json_grade, import_attempts, prompt_hash, render_report, validate_cases


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
