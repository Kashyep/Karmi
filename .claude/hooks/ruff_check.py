"""PostToolUse hook: ruff-check an edited Python file. Silent on success; exit 2 feeds errors back."""

import json
import os
import subprocess
import sys
from pathlib import Path

path = json.load(sys.stdin).get("tool_input", {}).get("file_path", "")
project = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
if not path.endswith(".py") or not Path(path).resolve().is_relative_to(project):
    sys.exit(0)
result = subprocess.run(  # noqa: S603
    [sys.executable, "-m", "ruff", "check", "--quiet", path],
    capture_output=True,
    text=True,
    check=False,
)
if result.returncode == 1:  # 1 = lint findings; 2 = ruff itself failed (not our business)
    sys.stderr.write(result.stdout[-2000:])
    sys.exit(2)
