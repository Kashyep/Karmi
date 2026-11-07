# Karmi Release 1 — Owner Runbook & Next Steps

This runbook documents all required owner actions, deployment procedures, database migrations, security decisions, and issue resolutions for Karmi Release 1.

All commands and configurations are cited from repository source files or marked `[INFERENCE]`. No commands in this runbook were executed against live infrastructure or external services by the agent.

---

## Summary of Owner Steps

| Step | Owner Action | Status |
| :--- | :--- | :--- |
| **1. Pre-flight (local)** | Verify local branch `r1f/release` HEAD, pubspec version `0.1.0+5`, and zero push status | Ready for owner execution |
| **2. Deploy + migration `a5b6c7d8e9f0`** | Perform BACKUP-FIRST, apply Alembic migration, verify schema, and deploy container | Ready for owner execution (BACKUP-FIRST) |
| **3. Clerk Google SSO** | Enable Google connection in Clerk dashboard & add redirect URL allowlist | Configured in repo; Device testing: **NOT VERIFIED (device testing paused by owner)** |
| **4. Disable CI reviewer workflow** | Disable `.github/workflows/jules-pr-reviewer.yml` in GitHub Actions UI | Ready for owner action in GitHub UI |
| **5. Close issues #39, #40, #41** | Close automated mock/reviewer issues in GitHub UI or CLI | Ready for owner closure |
| **6. R-9 golden review** | Visually inspect diffs of regenerated Flutter golden images | Pending visual review by owner |
| **7. PR #34 decision** | Review Phase 2 model router ordering PR (close, merge, or leave open) | Pending owner decision (do not merge without review) |
| **8. Push/scrub decision** | Decide whether to scrub git history or accept and rotate credentials before public push | Pending owner decision |
| **9. Reinstall signed release APK** | Uninstall debug build and install release APK on Pixel when device testing resumes | **NOT VERIFIED (device testing paused by owner)** |

---

## 1. Pre-flight (local)

Before deploying or tagging Release 1, verify the local branch state, application versioning, and remote sync status.

### 1.1 Verify Branch and HEAD Commit
- Target branch: `r1f/release` (worktree: `/home/rosso/Projects/Karmi-release/final-rel`).
- Base branch: `314afa4` (`release1/final`).
- Inspect HEAD commit:
  ```bash
  git status
  git log -1 --oneline r1f/release
  ```
- Expected status: Working tree clean, HEAD commit contains release prep documentation (`docs(release): ...`).

### 1.2 Verify Application Version
- File path: `mobile/pubspec.yaml` (line 4).
- Verify version with:
  ```bash
  grep -E '^version:' mobile/pubspec.yaml
  ```
- Expected output:
  ```yaml
  version: 0.1.0+5
  ```

### 1.3 Verify No Push Has Happened (Informational)
Confirm that local release branches have not been pushed to the remote repository:
```bash
# Check tracking status of local branches
git branch -vv | grep 'r1f/'

# Check remote refs on origin
git ls-remote --heads origin 'r1f/*'
```
- Expected result: Remote refs for `r1f/release` and intermediate wave branches return empty. All release integration work has remained strictly local.

---

## 2. Deploy + migration for `a5b6c7d8e9f0` (owner runs; NOT executed by the agent)

> **CRITICAL**: The agent has NOT executed migrations, backups, or deployment steps. The owner executes these steps following the strict **BACKUP-FIRST** protocol.

### 2.1 Step A: Take Database Backup / Branch Snapshot (BACKUP-FIRST)
- Cited runbook: `docs/runbooks/backup-restore.md` (Step 1: *"Quiesce writes or capture a transactionally consistent PostgreSQL backup... Confirm target names explicitly; never restore over the source"*).
- Past release evidence: `docs/release1/RELEASE_PREP.md` (line 6: `~/karmi-backups/prod-pre-r1-20261022-0536.dump`).
- **OWNER TO CONFIRM backup method**: `docs/runbooks/backup-restore.md` specifies capturing a transactionally consistent PostgreSQL backup, and `docs/release1/RELEASE_PREP.md` documents `pg_dump` custom format exports to `~/karmi-backups/`. Neon console / CLI branch snapshot commands are not documented in the repository runbooks.
- Recommended backup actions:
  1. **Neon Branch Snapshot (Cloud Console)**: In the Neon management console, create a point-in-time branch snapshot of the production database branch before initiating writes `[INFERENCE]`.
  2. **PostgreSQL Dump (CLI)**:
     ```bash
     mkdir -p ~/karmi-backups
     pg_dump -Fc -d "$DAILY_AGENT_MIGRATION_DATABASE_URL" -f ~/karmi-backups/prod-pre-a5b6c7d8e9f0-$(date +%Y%m%d-%H%M).dump
     ```
     *(Command derived from `docs/release1/RELEASE_PREP.md` lines 6 & 20 `[INFERENCE]`)*.

### 2.2 Step B: Confirm Current Alembic Head
- Target migration file: `migrations/versions/a5b6c7d8e9f0_bug_reports.py`.
- Source lines:
  - `revision: str = "a5b6c7d8e9f0"` (line 13)
  - `down_revision: str | Sequence[str] | None = "f4a5b6c7d8e9"` (line 14)
- Predecessor migration file: `migrations/versions/f4a5b6c7d8e9_usage_period_credit_adjustment.py`.
- Owner confirmation command:
  ```bash
  python -m alembic current
  ```
- Expected output before migration:
  ```
  f4a5b6c7d8e9 (head)
  ```
  *(If alembic reports any other revision or multiple heads, halt immediately per `scripts/deploy_azure.py` line 191)*.

### 2.3 Step C: Apply Migration `a5b6c7d8e9f0`
Apply the upgrade using one of the repository's documented migration methods:

- **Method 1 (Documented Azure Deploy Script)**:
  Cited from `ops/deploy/README.md` (line 23) and `docs/runbooks/azure-deployment.md` (line 21):
  ```bash
  ~/.venvs/karmi/bin/python scripts/deploy_azure.py migrate
  ```
  *Note*: This script validates Neon direct vs. pooled connection URLs, asserts matching hosts in `.env.neon`, verifies `alembic_version`, applies `alembic upgrade head`, and confirms the resulting head (`scripts/deploy_azure.py:111-249`).

- **Method 2 (Direct Alembic Invocation)**:
  Cited from `docs/runbooks/backend-setup.md` (lines 30-32) and `scripts/deploy_azure.py` (lines 217-225):
  ```bash
  export DAILY_AGENT_DATABASE_URL="<pooled-neon-url>"
  export DAILY_AGENT_MIGRATION_DATABASE_URL="<direct-neon-url>"
  python -m alembic upgrade a5b6c7d8e9f0
  ```

### 2.4 Step D: Verify Migration
Verify that the database schema reflects the new revision:
```bash
# 1. Check Alembic revision
python -m alembic current
# Expected: a5b6c7d8e9f0 (head)

# 2. Verify table exists in PostgreSQL public schema
python -c "
import psycopg, os
with psycopg.connect(os.environ['DAILY_AGENT_MIGRATION_DATABASE_URL']) as conn:
    with conn.cursor() as cur:
        cur.execute(\"SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename='bug_reports'\")
        print('Table found:', cur.fetchone())
"
```
Verify the columns created in `bug_reports`: `id`, `account_id`, `user_id`, `ticket_number`, `client_report_id`, `request_hash`, `category`, `description`, `diagnostics`, `screenshot`, `screenshot_content_type`, `status`, `admin_notes`, `created_at`, `updated_at`, `triaged_at`, `resolved_at` (`migrations/versions/a5b6c7d8e9f0_bug_reports.py:20-56`).

### 2.5 Step E: Rollback & Restore Procedure
- **Reversible Schema Downgrade**:
  The migration `a5b6c7d8e9f0` is fully reversible (`a5b6c7d8e9f0_bug_reports.py:58-62`):
  ```python
  def downgrade() -> None:
      op.drop_index("ix_bug_reports_created_at", table_name="bug_reports")
      op.drop_index("ix_bug_reports_user_id", table_name="bug_reports")
      op.drop_index("ix_bug_reports_account_id", table_name="bug_reports")
      op.drop_table("bug_reports")
  ```
  Rollback command:
  ```bash
  python -m alembic downgrade f4a5b6c7d8e9
  ```
- **Disaster Recovery / Restore-from-Backup**:
  Cited from `docs/release1/RELEASE_PREP.md` (line 20) and `docs/runbooks/backup-restore.md` (lines 7-9):
  ```bash
  # Restore into isolated target (or production direct URL if incident commander authorizes)
  pg_restore --clean --no-owner -d "$DAILY_AGENT_MIGRATION_DATABASE_URL" ~/karmi-backups/<backup-file>.dump
  ```

### 2.6 Deploy Commands & Required Environment Variables
Deploy commands cited from `ops/deploy/README.md` (lines 11-26) and `docs/runbooks/azure-deployment.md` (lines 12-24):

- **Image Build & Publish**:
  ```bash
  # Manual container build for linux/amd64
  podman build --platform=linux/amd64 -t karmi-backend .
  az acr login --name karmiacr
  podman tag karmi-backend karmiacr.azurecr.io/karmi-backend:latest
  podman push karmiacr.azurecr.io/karmi-backend:latest

  # Or via automated script
  ~/.venvs/karmi/bin/python scripts/deploy_azure.py build
  ```

- **Container App Deployment**:
  ```bash
  ~/.venvs/karmi/bin/python scripts/deploy_azure.py deploy
  ~/.venvs/karmi/bin/python scripts/deploy_azure.py status
  ```

- **Readiness Verification**:
  Cited from `docs/runbooks/azure-deployment.md` (line 39) and `ops/deploy/README.md` (line 42):
  ```bash
  scripts/readiness_config.py --env-file .env.azure.prod --output out.json
  ```

- **Required Environment Variable NAMES (Values Must Never Be Committed)**:
  Inspected from `scripts/deploy_azure.py` (lines 424-524):
  - In `.env.neon`:
    - `DAILY_AGENT_DATABASE_URL` (pooled connection for runtime)
    - `DAILY_AGENT_MIGRATION_DATABASE_URL` (direct connection for migrations)
  - In `.env.clerk`:
    - `DAILY_AGENT_CLERK_ISSUER`
    - `DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64`
    - `DAILY_AGENT_ADMIN_CLERK_USER_IDS` (admin allowlist)
    - `DAILY_AGENT_CLERK_PUBLISHABLE_KEY`
  - In `.env.openrouter`:
    - `OPEN_ROUTER_KEY` (or `OPENROUTER_API_KEY`)
  - In `.env.azure` (internal deploy state, mode 0600):
    - `AUTH_SECRET`
    - `WEBHOOK_SECRET`
    - `ACR_NAME`
    - `IMAGE_TAG`
  - In Azure Container App Configuration:
    - Plain configuration:
      - `DAILY_AGENT_ENVIRONMENT` (`production`)
      - `DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH` (`false`)
      - `DAILY_AGENT_OPENROUTER_ENABLED` (`true`)
      - `DAILY_AGENT_GATEWAY_KILL_SWITCH` (`false`)
      - `DAILY_AGENT_GATEWAY_TIMEOUT_SECONDS` (`12`)
      - `DAILY_AGENT_PAID_CHECKOUT_ENABLED` (`false`)
      - `DAILY_AGENT_WHATSAPP_ENABLED` (`false`)
      - `DAILY_AGENT_CLERK_ISSUER`
      - `DAILY_AGENT_PRODUCTION_PERIOD_BUDGET_MICRO`
      - `DAILY_AGENT_GLOBAL_DAILY_BUDGET_MICRO`
      - `DAILY_AGENT_MODEL_REGISTRY_PATH`
      - `DAILY_AGENT_ADMIN_CLERK_USER_IDS`
      - `DAILY_AGENT_CLERK_PUBLISHABLE_KEY`
      - `DAILY_AGENT_ADMIN_UI_ENABLED` (gating `/admin` route)
    - Secret references (mapped from Azure Key Vault / container secrets):
      - `DAILY_AGENT_DATABASE_URL` (secretref: `database-url`)
      - `DAILY_AGENT_AUTH_SECRET` (secretref: `auth-secret`)
      - `DAILY_AGENT_WEBHOOK_SECRET` (secretref: `webhook-secret`)
      - `DAILY_AGENT_OPENROUTER_API_KEY` (secretref: `openrouter-api-key`)
      - `DAILY_AGENT_CLERK_JWT_PUBLIC_KEY_B64` (secretref: `clerk-jwt-public-key`)

---

## 3. Clerk Google SSO

Authoritative reference: [`docs/release1/GOOGLE_SSO.md`](GOOGLE_SSO.md).

### 3.1 Owner Dashboard Configuration Steps
As documented in `docs/release1/GOOGLE_SSO.md` (lines 30-32), the owner must complete the following configuration in the Clerk dashboard:
1. **Enable Google Social Connection**: In the Clerk dashboard for the **development instance**, navigate to *User & Authentication -> Social Connections* and enable Google SSO. (Development instances utilize Clerk-managed OAuth credentials; production requires your own Google Cloud OAuth Client ID and secret).
2. **Allowlist OAuth Redirect URI**: Under *User & Authentication -> Paths* (or *SSO / Redirect URLs*), add the app's native redirect URL:
   ```
   ai.karmi.app://sso-callback
   ```
3. **Verify Android Application ID**: Confirm that the Android package name / applicationId `ai.karmi.app` matches the configured intent filter in `mobile/android/app/src/main/AndroidManifest.xml`.

### 3.2 Verification Status
- Backend verification: **VERIFIED** via offline unit/e2e test:
  ```bash
  python -m pytest tests/e2e/test_clerk_sso_identity.py -q
  ```
  *(Passed: verifies identical Clerk `sub` reuses account, distinct `sub` provisions fresh user without duplicates)*.
- Real device testing: **NOT VERIFIED (device testing paused by owner)**.
  When device testing resumes, execute verification steps from `GOOGLE_SSO.md` (lines 33-34):
  - Tap "Continue with Google" on onboarding.
  - Verify browser launches external Google authentication sheet.
  - Test cancellation: return to app and verify message `"Google sign-in was cancelled."`
  - Test completion: confirm app returns to authenticated session without duplicate account rows.

---

## 4. Disable CI reviewer workflow (owner action in GitHub UI)

The autonomous PR review workflow must be disabled in the GitHub repository UI prior to opening release PRs.

### 4.1 Workflow File State
- File path: `.github/workflows/jules-pr-reviewer.yml`.
- **CRITICAL NOTE**: The agent did **NOT** edit, modify, or commit changes to `.github/workflows/jules-pr-reviewer.yml`. The file is tracked and preserved unmodified in the repository.

### 4.2 Workflow Triggers and Permissions (Read-Only Inspection)
Lines 3-12 of `.github/workflows/jules-pr-reviewer.yml`:
```yaml
name: Auto PR Reviewer & Merger

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review-and-merge:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4
      - name: Run Jules PR Reviewer
        uses: google-labs-code/jules-invoke@v1.0.0
```
- **Trigger**: Every pull request that is opened, synchronized (pushed to), or reopened.
- **Risk**: The workflow runs `google-labs-code/jules-invoke@v1.0.0` with `contents: write` and `pull-requests: write`. If automated checks pass, it autonomously approves (`gh pr review --approve`) and merges (`gh pr merge --merge`) pull requests into base branches without human intervention.

### 4.3 Owner UI Action Required
In the GitHub Web UI:
1. Navigate to the repository: `https://github.com/Kashyep/Karmi`.
2. Go to **Actions** tab -> Select **Auto PR Reviewer & Merger** workflow from the left sidebar.
3. Click the **`...`** (overflow menu) at the top-right of the workflow overview.
4. Select **Disable workflow**.
5. Alternatively, disable Actions under **Settings -> Actions -> General -> Disable actions** if all automated CI is to be halted temporarily `[INFERENCE]`.

---

## 5. Close issues #39, #40, #41

Issues #39, #40, and #41 were generated by automated review tooling during earlier testing rounds.

### 5.1 Issue Inspection (Read-Only Evidence)
- **Issue #39**:
  - Title: `Approved PR using mock_gh.sh as all checks have successfully passed.`
  - State: `OPEN`
  - Author: `Kashyep (Arnav Kashyap)`
  - Body excerpt: *"Approved PR using mock_gh.sh as all checks have successfully passed. PR created automatically by Jules..."*
- **Issue #40**:
  - Title: `Review and merge PR`
  - State: `OPEN`
  - Author: `Kashyep (Arnav Kashyap)`
  - Body excerpt: *"Approved and merged the pull request after completing code review and running tests..."*
- **Issue #41**:
  - Title: `Automated code review and merge of PR using mocked gh CLI`
  - State: `OPEN`
  - Author: `Kashyep (Arnav Kashyap)`
  - Body excerpt: *"Reviewed the pull request code for vulnerabilities, bugs, merge conflicts... used a mocked GitHub CLI script to approve and merge the PR automatically."*

### 5.2 Owner Action Required
The agent did **NOT** close these issues. The owner should close them via the GitHub UI or using the GitHub CLI:
```bash
gh issue close 39 --comment "Closed: Automated reviewer test artifact from Jules mock run."
gh issue close 40 --comment "Closed: Automated reviewer test artifact from Jules mock run."
gh issue close 41 --comment "Closed: Automated reviewer test artifact from Jules mock run."
```

---

## 6. R-9 golden review

Citations:
- `docs/release1/DEPENDENCY_BOARD.md` (Row H & Risk R-9: *"Goldens regenerated in this release need human review of the diffs"*).
- `docs/release1/RELEASE_REPORT.md` (Section 8: *"Screenshots and goldens"*; Section 10: *"Unresolved risks, item 4"*).

### 6.1 Review Requirement
During Release 1 implementation, Flutter test suites regenerated golden image baselines across accessibility, onboarding, shell parity, and theme variations. While automated pixel-matching tests pass in `flutter test`, visual inspection by a human is required (R-9) to verify that layout adjustments, typography, padding, and high-contrast / glass materials render correctly without visual regressions.

### 6.2 Golden Image Directories
Located via `git ls-files '*goldens*'`:
1. `mobile/test/a11y/goldens/linux/` (12 images: a11y chat & error-card variants at 1.0x and 2.0x scales)
2. `mobile/test/features/admin/goldens/linux/` (4 images: admin plan management & user details)
3. `mobile/test/features/chat/rendering/goldens/` (3 images: markdown message and streaming reply rendering)
4. `mobile/test/features/onboarding/goldens/linux/` (22 images: onboarding welcome, sign-in, account creation, OTP, and plan intro)
5. `mobile/test/goldens/linux/` (77 images: chat, drawer, rail, settings, plans, streaming, and tier palettes)
6. `mobile/test/goldens/windows/` (46 images: cross-platform baseline goldens for Windows layout)
7. `mobile/test/shell/goldens/linux/` (16 images: shell parity between solid and glass surfaces, app bar previews)

Total: 180 golden image assets in tree. Owner visually inspects the diffs using `git diff HEAD~N -- 'mobile/test/*goldens*'` or an image diff tool before release approval.

---

## 7. PR #34 decision

Inspection command: `gh pr view 34` (read-only).

### 7.1 Pull Request Metadata
- Number: `#34`
- Title: `feat(gateway): Phase 2 — exclude 0.0-score models from task router ordering`
- State: `OPEN` (Draft)
- Base ref: `release1/chat-redesign`
- Head ref: `phase/2-free-pool`
- Author: `Rossonerian (Karmi Tester)`
- PR Body Excerpt:
  > *"Summary: Phase 2: Free pool model routing update. Filters out candidates from the router's per-task ordering when their registry score for that task is 0.0, unless that would empty the candidate pool... Needs owner review — do not merge... Owner agreement needed before merge: Confirm agreement on excluding nvidia/nemotron-3.5-lightning:free from maths..."*

### 7.2 Decision Options for Owner
- **Option A (Close without merging)**: Close PR #34. The Phase 2 model scoring adjustments are non-critical optimizations and can be tracked in the post-R1 backlog (`docs/release1/R1_1_BACKLOG.md`).
- **Option B (Leave open as draft)**: Keep PR #34 open for future evaluation once Release 1 is tagged and stabilized.
- **Option C (Merge after rebase)**: Rebase `phase/2-free-pool` onto `release1/final`, agree on scoring policy for `nvidia/nemotron-3.5-lightning:free` on `maths`, run full test gates, and merge.

### 7.3 Recommendation Based on Repo Evidence
**Do NOT merge into Release 1.**
- Evidence 1: The PR description explicitly states *"Needs owner review — do not merge"*.
- Evidence 2: The base branch is `release1/chat-redesign`, which is behind `release1/final`.
- Evidence 3: `src/daily_agent/gateway/router.py` on `release1/final` does not contain this filtering logic, and R1 contract scope (`local://r1-contract.md`) does not include Phase 2 score filtering.

---

## 8. Push/scrub decision for the public repo

Prior to publishing this repository to a public GitHub repository, the owner must make a security and hygiene determination regarding repository history.

### 8.1 The Four Identified Risk Categories
As documented in the release brief, historical commits contain:
1. **Real Names**: Contributor and developer personal names present in git author/committer headers and commit logs.
2. **Screenshots in Tree**: Administrative web screenshots (`docs/release1/admin-web/`) and UI test goldens stored as binary PNG files across git history.
3. **Clerk Identifiers**: Development instance IDs, publishable keys, and user subject strings (`user_...`) recorded in test fixtures and early commit diffs.
4. **Neon Endpoint Address**: Database hostnames and endpoint strings referenced in historical documentation notes and draft setups.

### 8.2 Tracked `.env.testauth` Symlink
Verification command:
```bash
git ls-files -s .env.testauth
```
Result:
```
120000 72119f39291c9c41b70cc27ba77ed166919a566c 0	.env.testauth
```
- Git mode `120000` confirms that `.env.testauth` is tracked as a symbolic link in the repository tree.
- Note: The contents of `.env.testauth` have NOT been printed or read by the agent per contract prohibitions.

### 8.3 Owner Decision Options
The owner must choose between two release strategies:
- **Strategy 1 (Scrub History via Rewrite)**:
  - Use `git-filter-repo` or BFG Repo-Cleaner to rewrite history prior to initial public push `[INFERENCE]`.
  - Untrack and delete `.env.testauth`.
  - Redact developer names, historical Clerk identifiers, and Neon host references.
  - Remove binary screenshot artifacts from past commit objects to minimize clone weight.
- **Strategy 2 (Accept Historical Log & Rotate Credentials)**:
  - Maintain repository as private/internal, or accept existing commit history as development-phase log.
  - Untrack `.env.testauth` (`git rm .env.testauth && git commit -m "chore: remove tracked symlink"`).
  - Rotate all Clerk API keys, webhook secrets, and JWT public keys.
  - Rotate Neon database credentials and connection strings so historical endpoints are completely invalid.

*Decision is left open for the owner.*

---

## 9. Reinstall the signed release APK on the Pixel when device testing resumes

> **STATUS**: **NOT VERIFIED (device testing paused by owner)**

When device testing is resumed by the owner, follow this procedure to install the signed production release APK.

### 9.1 Baseline Device State
- The Pixel test device currently has the **debug-signed profile baseline** installed (`docs/release1/RELEASE_PREP.md` line 15: *"Signed with the local debug keystore... replacing the installed beta.2 requires adb uninstall ai.karmi.app first"*).
- Reverse port forwarding rules (`adb reverse tcp:8000 tcp:8001`) may remain active on the device.

### 9.2 Build Signed Release APK
Build the release APK locally using the external keystore per [`docs/release1/SHA256_AND_SIGNING.md`](SHA256_AND_SIGNING.md):
```bash
cd mobile
# Build split-per-abi release APKs
flutter build apk --release --split-per-abi

# Verify certificate fingerprint matches prefix 14a65fff ... suffix 8ba1
apksigner verify --print-certs build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
```

### 9.3 Signature Mismatch Risk & Reinstallation Commands
- **Risk**: Android Package Manager strictly enforces certificate signature continuity. Because the existing app on the phone was signed with the debug certificate, attempting an in-place upgrade (`adb install -r`) will fail with:
  ```
  Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: Existing package and new package have different signing signatures]
  ```
  `[INFERENCE based on Android PackageManager signature enforcement and RELEASE_PREP.md:15]`.
- **Installation Procedure**:
  ```bash
  # 1. Uninstall the debug profile build
  adb uninstall ai.karmi.app

  # 2. Install the signed release APK
  adb install mobile/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
  ```

### 9.4 Clean Up ADB Reverse Rules
When device testing concludes or when connecting to the hosted cloud backend (`https://...`), remove the local port forwarding rules:
```bash
# Standard adb syntax to remove specific port forwards
adb reverse --remove tcp:8000
adb reverse --remove tcp:8001

# Or remove all active reverse socket connections
adb reverse --remove-all
```
