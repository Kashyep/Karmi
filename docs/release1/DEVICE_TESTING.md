# Device testing harness

Drive the Android app on a USB-connected phone against a local Karmi API that answers from a
fake OpenAI/OpenRouter-compatible provider. No real model is called, no key is needed, and
the backend refuses to talk to `openrouter.ai`.

Files:

- `scripts/dev_fake_provider.py` — `fake` runs the canned provider; `serve-backend` runs the
  Karmi API on `127.0.0.1:<port>` with a fresh SQLite DB at `data/device-test-<UTC ts>.db`.
- `scripts/device_smoke.py` — adb driver: sign in (development sign-in), new chat, render /
  long-scroll / slow / fail prompts, history, dark mode. Writes screenshots and `log.json` to
  `docs/release1/device-runs/<UTC ts>/`.

## Fake provider reply keywords

The keyword is searched in the last user message, in this priority order:

| Keyword in prompt | Reply |
| --- | --- |
| `fail` | HTTP 503 from the provider (the app shows its error card) |
| `slow` | 12 s pause before the first token, then a short reply |
| `long` | about 3000 words with `#`/`##` headings, paragraphs and bullets |
| `render` | markdown probe: `**bold**` line followed by a single newline, a `>` quote, a ```` ```python ```` fence containing `"`, `<`, `&`, and `2³² → x` |
| `hindi` | long Devanagari reply |
| anything else | `Fake echo from <model>: <prompt>` |

The `model` field of the request is echoed back in every response. Streaming uses
`data:` SSE chunks ending with `data: [DONE]`; `stream: false` returns one JSON completion.
Token pacing is `FAKE_TOKEN_DELAY` seconds per chunk (default `0.012`).

## Guards

`serve-backend` sets the adapter's `OPENROUTER_BASE_URL` and `OPENROUTER_CHAT_URL` to the fake
**before** importing the app, exits with status 2 if either still contains `openrouter.ai`,
and wraps `httpx.HTTPTransport.handle_request` so any request to `openrouter.ai` is refused
(`[guard] BLOCKED ...` on stderr). The key is the literal `fake-local-key`, passed through
`DAILY_AGENT_OPENROUTER_API_KEY`; the launcher reads no `.env*` file.

## Run it

Ports: the phone reaches the host through `adb reverse`. The app's build-time
`API_BASE_URL=http://127.0.0.1:8000` means the device's port 8000 must map to the backend.

```sh
# 1. fake provider (terminal A)
.venv/bin/python scripts/dev_fake_provider.py fake            # 127.0.0.1:8900

# 2. backend (terminal B); use 8001 if another API already holds 8000
.venv/bin/python scripts/dev_fake_provider.py serve-backend --port 8001

# 3. route the phone's 8000 to that backend
adb -s 5B271XEBF3XDF0 reverse tcp:8000 tcp:8001

# 4. prove the fake path (expects message.delta events and no openrouter.ai contact)
TOK=$(curl -s -X POST http://127.0.0.1:8001/dev/token | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -sN -X POST http://127.0.0.1:8001/v1/chat/stream \
  -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
  -d '{"text":"render test","clientMessageId":"devharness-probe-001"}'

# 5. profile build from the worktree (run alone; the build needs .env.clerk in the repo root)
.venv/bin/python mobile/tool/run_android_dev.py build apk --profile \
  --dart-define=API_BASE_URL=http://127.0.0.1:8000
adb -s 5B271XEBF3XDF0 install -r mobile/build/app/outputs/flutter-apk/app-profile.apk

# 6. drive the app and keep evidence
.venv/bin/python scripts/device_smoke.py --serial 5B271XEBF3XDF0
```

Profile builds keep development sign-in (`KARMI_DEV_AUTH` defaults on outside release mode),
so the smoke run signs in itself. If a build shows only Clerk sign-in, `device_smoke.py`
stops with `manual sign-in needed` and writes that into `log.json`.

When finished, restore the phone's mapping: `adb reverse tcp:8000 tcp:8000` (or whichever
backend the team uses), and stop the backend and fake provider.

## Outputs

`docs/release1/device-runs/<UTC ts>/`:

- `NN-<name>.png` — screenshots in order (`empty-chat`, `render`, `long-midstream-scrolled`,
  `long-done`, `slow-11s`, `fail-error-retry`, `history`, `dark-mode`).
- `log.json` — per-step status, timings, the pill label seen, whether streaming was still
  active at the scroll, and the theme restored.

Keep the combined screenshot size under 3 MB before committing a run.
