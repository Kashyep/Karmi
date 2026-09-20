from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from .core import (
    LabStore,
    candidate_record,
    coverage_metrics,
    fake_run,
    grade_attempt,
    import_attempts,
    read_jsonl,
    render_report,
    router_recommendation,
    static_svg_chart,
    validate_cases,
    write_jsonl,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)
suite_app = typer.Typer(no_args_is_help=True)
app.add_typer(suite_app, name="suite")


def quarantine_unknown_cases(
    attempts: list[dict[str, Any]],
    cases: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    known: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for attempt in attempts:
        case_id = str(attempt["case_id"])
        if case_id in cases:
            known.append(attempt)
        else:
            quarantine.append({"record": attempt, "reason": "unknown case_id"})
    return known, quarantine


@suite_app.command("validate")
def validate(path: Annotated[Path, typer.Argument(exists=True, readable=True)]) -> None:
    cases = read_jsonl(path)
    errors = validate_cases(cases)
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(1)
    typer.echo(f"valid: {len(cases)} cases")


@suite_app.command("export")
def export_candidates(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    candidate_only: Annotated[bool, typer.Option("--candidate-only/--include-protected")] = True,
) -> None:
    cases = read_jsonl(path)
    errors = validate_cases(cases)
    if errors:
        raise typer.BadParameter("suite is invalid: " + "; ".join(errors[:3]))
    records = [candidate_record(case) for case in cases] if candidate_only else cases
    write_jsonl(out, records)
    typer.echo(f"exported: {len(records)} candidate records -> {out}")


@app.command("import")
def import_command(
    path: Annotated[Path, typer.Argument(exists=True, readable=True)],
    source_label: Annotated[str, typer.Option("--source-label")],
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    attempts, quarantine = import_attempts(path, source_label)
    payload = {"attempts": attempts, "quarantine": quarantine}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    else:
        typer.echo(rendered)
    typer.echo(f"imported={len(attempts)} quarantined={len(quarantine)}", err=True)


@app.command("grade")
def grade(
    suite: Annotated[Path, typer.Option("--suite", exists=True, readable=True)],
    responses: Annotated[Path, typer.Option("--responses", exists=True, readable=True)],
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    cases = {case["case_id"]: case for case in read_jsonl(suite)}
    attempts, quarantine = import_attempts(responses, "grade-input")
    known, unknown = quarantine_unknown_cases(attempts, cases)
    quarantine.extend(unknown)
    grades = [grade_attempt(cases[a["case_id"]], a["response"]) for a in known]
    payload = {"grades": grades, "quarantine": quarantine}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if out:
        out.write_text(rendered + "\n", encoding="utf-8")
    else:
        typer.echo(rendered)


@app.command("report")
def report(
    responses: Annotated[Path, typer.Option("--responses", exists=True, readable=True)],
    suite: Annotated[Path, typer.Option("--suite", exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    fmt: Annotated[str, typer.Option("--format")] = "md",
) -> None:
    if fmt not in {"md", "json", "csv", "html"}:
        raise typer.BadParameter(f"unsupported format {fmt!r}; use md, json, csv, or html")
    cases = {case["case_id"]: case for case in read_jsonl(suite)}
    attempts, quarantine = import_attempts(responses, "report-input")
    known, unknown = quarantine_unknown_cases(attempts, cases)
    quarantine.extend(unknown)
    grades = [grade_attempt(cases[a["case_id"]], a["response"]) for a in known]
    for item in quarantine:
        record = item.get("record", {})
        if isinstance(record, dict) and "case_id" in record:
            grades.append(
                {
                    "case_id": record["case_id"],
                    "status": "quarantined",
                    "evidence": item["reason"],
                    "grader": "import-validator-v1",
                }
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(attempts, grades, fmt), encoding="utf-8")
    typer.echo(f"report: {out}")


@app.command("run")
def run_fake(
    suite: Annotated[Path, typer.Option("--suite", exists=True, readable=True)],
    db: Annotated[Path, typer.Option("--db")],
    model: Annotated[str, typer.Option("--model")] = "fake-v1",
    budget: Annotated[int, typer.Option("--budget", min=0)] = 60,
    fail_every: Annotated[int, typer.Option("--fail-every", min=0)] = 0,
) -> None:
    cases = read_jsonl(suite)
    store = LabStore(db)
    attempts = fake_run(cases, model, budget, fail_every)
    case_map = {case["case_id"]: case for case in cases}
    for attempt in attempts:
        store.add_attempt(attempt)
        if attempt["status"] == "completed":
            store.add_grade(attempt["attempt_id"], grade_attempt(case_map[attempt["case_id"]], attempt["response"]))
    typer.echo(json.dumps({"attempts": len(attempts), "coverage": coverage_metrics(cases, attempts)}, sort_keys=True))
    store.close()


@app.command("db-report")
def db_report(
    suite: Annotated[Path, typer.Option("--suite", exists=True, readable=True)],
    db: Annotated[Path, typer.Option("--db", exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    fmt: Annotated[str, typer.Option("--format")] = "md",
) -> None:
    if fmt not in {"md", "json", "svg"}:
        raise typer.BadParameter(f"unsupported format {fmt!r}; use md, json, or svg")
    cases = read_jsonl(suite)
    store = LabStore(db)
    attempts, grades = store.attempts(), store.grades()
    grade_rows = [{"case_id": row["case_id"], "status": row["status"], "evidence": row["evidence"], "grader": row["grader"]} for row in grades]
    content = render_report(attempts, grade_rows, fmt)
    if fmt == "svg":
        content = static_svg_chart(grade_rows)
    elif fmt == "json":
        payload = json.loads(content)
        payload["coverage"] = coverage_metrics(cases, attempts)
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    elif fmt == "md":
        content += f"\nCoverage: {json.dumps(coverage_metrics(cases, attempts), sort_keys=True)}\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content + ("\n" if not content.endswith("\n") else ""), encoding="utf-8")
    typer.echo(f"report: {out}")
    store.close()


router_app = typer.Typer(no_args_is_help=True)
app.add_typer(router_app, name="router")


@router_app.command("recommend")
def recommend(
    suite: Annotated[Path, typer.Option("--suite", exists=True, readable=True)],
    db: Annotated[Path, typer.Option("--db", exists=True, readable=True)],
    out: Annotated[Path, typer.Option("--out")],
    model: Annotated[str, typer.Option("--model")] = "fake-v1",
) -> None:
    cases = read_jsonl(suite)
    store = LabStore(db)
    attempts, grades = store.attempts(), store.grades()
    payload = router_recommendation(cases, attempts, grades, model)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"draft recommendation: {out}")
    store.close()


if __name__ == "__main__":
    app()
