from __future__ import annotations

import csv
import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


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


def render_report(attempts: list[dict[str, Any]], grades: list[dict[str, Any]], fmt: str) -> str:
    rows = [{**attempt, **{f"grade_{k}": v for k, v in grade.items() if k != "case_id"}}
            for attempt in attempts for grade in grades if grade["case_id"] == attempt["case_id"]]
    if fmt == "json":
        return json.dumps({"attempts": rows}, ensure_ascii=False, indent=2, sort_keys=True)
    if fmt == "csv":
        fields = sorted({key for row in rows for key in row})
        output: list[str] = []
        import io
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()
    if fmt == "html":
        cells = "".join(f"<th>{html.escape(str(field))}</th>" for field in sorted({k for r in rows for k in r}))
        body = "".join("<tr>" + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in sorted({k for r in rows for k in r})) + "</tr>" for row in rows)
        return f"<html><body><table><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table></body></html>"
    lines = ["# ModelLab report", "", f"Attempts: {len(attempts)}", "", "| Case | Grade | Evidence |", "|---|---|---|"]
    lines.extend(f"| {g['case_id']} | {g['status']} | {g['evidence']} |" for g in grades)
    return "\n".join(lines) + "\n"

