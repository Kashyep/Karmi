from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .core import candidate_record, grade_attempt, import_attempts, read_jsonl, render_report, validate_cases, write_jsonl

app = typer.Typer(no_args_is_help=True, add_completion=False)
suite_app = typer.Typer(no_args_is_help=True)
app.add_typer(suite_app, name="suite")


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
    grades = [grade_attempt(cases[a["case_id"]], a["response"]) for a in attempts if a["case_id"] in cases]
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
    cases = {case["case_id"]: case for case in read_jsonl(suite)}
    attempts, _ = import_attempts(responses, "report-input")
    grades = [grade_attempt(cases[a["case_id"]], a["response"]) for a in attempts if a["case_id"] in cases]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(attempts, grades, fmt), encoding="utf-8")
    typer.echo(f"report: {out}")


if __name__ == "__main__":
    app()

