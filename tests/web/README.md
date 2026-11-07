# Web Admin Tests & Screenshot Generation

This directory contains automated tests and asset generators for the Karmi web admin console (`/admin`).

## Running Tests

Automated web tests run via `pytest`:

```bash
export TMPDIR=~/.cache/karmi-tmp PATH=$PWD/.venv/bin:$PATH
flock /tmp/karmi-heavy.lock python -m pytest tests/web -rs -v
```

### Prerequisites
- **Python**: virtual environment with project dependencies installed.
- **Node.js**: The JavaScript tests (`test_admin_js_inr_formatting_and_xss_safety`) execute `admin.js` inside a Node VM sandbox to verify INR currency formatting, DOM XSS safety, and DOM element clearing without requiring full browser instrumentation. **Node.js runtime (`node`) on PATH is required** (CI and development workstations must have it).

## Screenshot Generation (`generate_screenshots.py`)

`generate_screenshots.py` captures visual documentation screenshots of the web admin dashboard (overview monitor, bug inbox list, and bug detail views across desktop and mobile viewports) into `docs/release1/admin-web/`.

### Manual Tooling & Requirements
- **Manual only**: This script is executed manually when updating release documentation; it is **not** run as part of the automated test suite or CI gate.
- **Dependencies**: Neither Playwright nor browser binaries are specified in `pyproject.toml` or `requirements.lock`.
- **Node.js & Playwright**: Requires Node.js and the `playwright` npm package installed externally.
- **Chromium**: Requires a Chromium/Chrome binary.

### Environment Variables
Configure the paths using the following environment variables if they are not in default system locations:

- `KARMI_CHROMIUM_PATH`: Path to the Chromium or Google Chrome executable (e.g. `/usr/bin/chromium` or a Playwright-managed browser binary).
- `KARMI_NODE_MODULES`: Path to the directory containing installed node modules (specifically `playwright`), e.g. `/path/to/project/node_modules`. Alternatively, standard `NODE_PATH` can be set.

Example invocation:
```bash
KARMI_CHROMIUM_PATH=/usr/bin/chromium \
KARMI_NODE_MODULES=/path/to/node_modules \
python tests/web/generate_screenshots.py
```
