from __future__ import annotations

import csv
import hashlib
import html
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REQUIRED_CASE_FIELDS = {"case_id", "family_id", "split", "complexity_level", "domain", "messages", "evaluation"}


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"line {line_no}: record must be an object")
        records.append(value)
    return records


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def prompt_hash(messages: list[dict[str, Any]]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_cases(cases: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    prompts: set[str] = set()
    for index, case in enumerate(cases, 1):
        missing = REQUIRED_CASE_FIELDS - case.keys()
        if missing:
            errors.append(f"record {index}: missing fields {sorted(missing)}")
            continue
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"record {index}: case_id must be a non-empty string")
        elif case_id in ids:
            errors.append(f"record {index}: duplicate case_id {case_id}")
        ids.add(case_id)
        messages = case["messages"]
        if not isinstance(messages, list) or not messages or any(not isinstance(m, dict) for m in messages):
            errors.append(f"record {index}: messages must be a non-empty list of objects")
        else:
            signature = json.dumps(messages, ensure_ascii=False, sort_keys=True)
            if signature in prompts:
                errors.append(f"record {index}: duplicate prompt")
            prompts.add(signature)
        if case.get("split") not in {"train", "calibration", "holdout"}:
            errors.append(f"record {index}: invalid split")
        if case.get("complexity_level") not in {1, 2, 3, 4}:
            errors.append(f"record {index}: complexity_level must be 1..4")
        evaluation = case["evaluation"]
        if not isinstance(evaluation, dict) or not evaluation.get("method"):
            errors.append(f"record {index}: evaluation.method is required")
    return errors


def candidate_record(case: dict[str, Any]) -> dict[str, Any]:
    # Explicit allow-list prevents evaluation, split and future protected fields leaking.
    return {
        "case_id": case["case_id"],
        "suite_version": case.get("suite_version"),
        "messages": case["messages"],
        "limits": case.get("limits", {}),
        "prompt_hash": prompt_hash(case["messages"]),
    }


def exact_json_grade(expected: Any, response: str) -> tuple[str, str]:
    try:
        actual = json.loads(response)
    except (TypeError, json.JSONDecodeError):
        return "fail", "response is not valid JSON"
    return ("pass", "exact JSON match") if actual == expected else ("fail", "JSON differs from reference")


def grade_attempt(case: dict[str, Any], response: str) -> dict[str, Any]:
    evaluation = case.get("evaluation", {})
    method = evaluation.get("method")
    if method == "exact_json":
        status, evidence = exact_json_grade(evaluation.get("reference_answer"), response)
    else:
        # Rubrics require human/semantic review; retain an explicit abstention rather than guessing.
        status, evidence = "abstain", "rubric requires human or calibrated semantic review"
    return {
        "case_id": case["case_id"],
        "grader": "model_lab.deterministic.v1",
        "method": method,
        "status": status,
        "evidence": evidence,
    }


def import_attempts(path: str | Path, source_label: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        with source.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    else:
        rows = read_jsonl(source)
    attempts: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for index, row in enumerate(rows, 1):
        case_id = row.get("case_id")
        response = row.get("response")
        key = (str(case_id), row.get("attempt_id"))
        reason = None
        if not case_id:
            reason = "missing case_id"
        elif response is None:
            reason = "missing response"
        elif key in seen:
            reason = "duplicate attempt"
        if reason:
            quarantine.append({"row": index, "reason": reason, "record": row})
            continue
        seen.add(key)
        attempts.append({
            "attempt_id": row.get("attempt_id") or f"{source_label}-{index}",
            "case_id": str(case_id),
            "response": str(response),
            "source_label": source_label,
            "prompt_hash": row.get("prompt_hash"),
            "status": row.get("status"),
            "finish_reason": row.get("finish_reason"),
            "latency_ms": _number_or_none(row.get("latency_ms")),
            "input_tokens": _number_or_none(row.get("input_tokens")),
            "output_tokens": _number_or_none(row.get("output_tokens")),
            "provenance": row.get("provenance") or {"kind": "imported", "source": str(source)},
        })
    return attempts, quarantine


def _number_or_none(value: Any) -> int | float | None:
    if value in (None, "", "null", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _csv_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def render_report(attempts: list[dict[str, Any]], grades: list[dict[str, Any]], fmt: str) -> str:
    rows = [{**attempt, **{f"grade_{k}": v for k, v in grade.items() if k != "case_id"}}
            for attempt in attempts for grade in grades if grade["case_id"] == attempt["case_id"]]
    if fmt == "json":
        return json.dumps({"attempts": rows}, ensure_ascii=False, indent=2, sort_keys=True)
    if fmt == "csv":
        fields = sorted({key for row in rows for key in row})
        import io
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: _csv_safe(row.get(field)) for field in fields} for row in rows)
        return stream.getvalue()
    if fmt == "html":
        cells = "".join(f"<th>{html.escape(str(field))}</th>" for field in sorted({k for r in rows for k in r}))
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in sorted({k for r in rows for k in r})) + "</tr>" for row in rows)
        return f"<html><body><table><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table></body></html>"
    lines = ["# ModelLab report", "", f"Attempts: {len(attempts)}", "", "| Case | Grade | Evidence |", "|---|---|---|"]
    lines.extend(f"| {g['case_id']} | {g['status']} | {g['evidence']} |" for g in grades)
    return "\n".join(lines) + "\n"


class LabStore:
    """Small SQLite evidence store; raw attempts are append-only by attempt_id."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, model_id TEXT NOT NULL,
                response TEXT, status TEXT NOT NULL, prompt_hash TEXT, latency_ms REAL,
                input_tokens INTEGER, output_tokens INTEGER, provenance_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS grades (
                attempt_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, status TEXT NOT NULL,
                evidence TEXT NOT NULL, grader TEXT NOT NULL,
                FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
            );"""
        )
        self.connection.commit()

    def add_attempt(self, attempt: dict[str, Any]) -> None:
        try:
            self.connection.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (attempt["attempt_id"], attempt["case_id"], attempt.get("model_id", "fake"),
                 attempt.get("response"), attempt.get("status", "completed"), attempt.get("prompt_hash"),
                 attempt.get("latency_ms"), attempt.get("input_tokens"), attempt.get("output_tokens"),
                 json.dumps(attempt.get("provenance", {}), sort_keys=True),
                 attempt.get("created_at", "1970-01-01T00:00:00Z")),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"attempt already exists: {attempt['attempt_id']}") from exc
        self.connection.commit()

    def add_grade(self, attempt_id: str, grade: dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO grades VALUES (?, ?, ?, ?, ?)",
            (attempt_id, grade["case_id"], grade["status"], grade["evidence"], grade["grader"]),
        )
        self.connection.commit()

    def attempts(self) -> list[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM attempts ORDER BY rowid").fetchall()
        return [dict(row, provenance=json.loads(row["provenance_json"])) for row in rows]

    def grades(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM grades ORDER BY rowid")]

    def close(self) -> None:
        self.connection.close()


def fake_run(cases: list[dict[str, Any]], model_id: str = "fake-v1", budget: int = 60,
             fail_every: int = 0) -> list[dict[str, Any]]:
    """Produce deterministic attempts without network access or provider credentials."""
    if budget < 0 or fail_every < 0:
        raise ValueError("budget and fail_every must be non-negative")
    attempts: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        if index >= budget:
            break
        failed = fail_every > 0 and (index + 1) % fail_every == 0
        evaluation = case.get("evaluation", {})
        response = "" if failed else json.dumps(evaluation.get("reference_answer"), ensure_ascii=False)
        attempts.append({
            "attempt_id": f"fake-{model_id}-{index + 1}", "case_id": case["case_id"], "model_id": model_id,
            "response": response, "status": "failed" if failed else "completed",
            "prompt_hash": prompt_hash(case["messages"]), "latency_ms": 1.0 + index,
            "input_tokens": sum(len(str(message.get("content", "")).split()) for message in case["messages"]),
            "output_tokens": 0 if failed else len(response.split()),
            "provenance": {"kind": "deterministic_fake", "seed": 0, "failure_injected": failed},
            "created_at": "1970-01-01T00:00:00Z",
        })
    return attempts


def coverage_metrics(cases: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {case["case_id"] for case in cases}
    observed = {attempt["case_id"] for attempt in attempts}
    missing = sorted(expected - observed)
    return {"expected_cases": len(expected), "observed_cases": len(expected & observed),
            "missing_cases": missing, "coverage_rate": (len(expected & observed) / len(expected) if expected else 1.0)}


def static_svg_chart(grades: list[dict[str, Any]]) -> str:
    counts = {"pass": 0, "fail": 0, "abstain": 0}
    for grade in grades:
        counts[grade.get("status", "abstain")] = counts.get(grade.get("status", "abstain"), 0) + 1
    colors = {"pass": "#2e7d32", "fail": "#c62828", "abstain": "#616161"}
    x = 20
    bars = []
    for label in ("pass", "fail", "abstain"):
        height = counts[label] * 8
        bars.append(f'<rect x="{x}" y="{100-height}" width="45" height="{height}" fill="{colors[label]}"/><text x="{x}" y="120">{label}</text>')
        x += 75
    return '<svg xmlns="http://www.w3.org/2000/svg" width="260" height="140" role="img" aria-label="grade counts"><line x1="10" y1="100" x2="250" y2="100" stroke="#333"/>' + "".join(bars) + "</svg>"


def router_recommendation(cases: list[dict[str, Any]], attempts: list[dict[str, Any]], grades: list[dict[str, Any]], model_id: str) -> dict[str, Any]:
    coverage = coverage_metrics(cases, attempts)
    passed = sum(1 for grade in grades if grade.get("status") == "pass")
    eligible = coverage["coverage_rate"] == 1.0 and bool(grades) and passed == len(grades)
    return {"draft": True, "model_id": model_id, "eligible": eligible, "observed_passes": passed,
            "observed_grades": len(grades), "coverage": coverage,
            "reason": "fixture-only evidence; production router was not modified"}
