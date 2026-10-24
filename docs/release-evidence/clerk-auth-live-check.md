# Clerk live FAPI check (Release 1 onboarding/auth)

Date: 2026-10-24. Target: live Clerk development instance used by the app (publishable key from `.env.clerk`; host not recorded). Probe: curl against `/v1/client/sign_ups` and `/v1/client/sign_ins`, with `__clerk_db_jwt` from `POST /v1/dev_browser`. Test identities: `karmi.qa.<random>+clerk_test@example.com`, code 424242. No secrets recorded.

## Observed codes

| Step | Request | HTTP | Result |
|---|---|---|---|
| Sign-up create (email, username, password, first/last) | `POST /client/sign_ups` | 200 | `status=missing_requirements`, `missing_fields=[]`, `unverified_fields=[email_address]`, `created_session_id=null` |
| Sign-up create without first/last name | `POST /client/sign_ups` | 200 | same as above |
| prepare_verification `email_code` | `POST /client/sign_ups/{id}/prepare_verification` | 200 | `unverified_fields=[email_address]` |
| attempt_verification code `424242` | `POST /client/sign_ups/{id}/attempt_verification` | 200 | email verified (`verifications.email_address.status=verified`), but `status` **stays `missing_requirements`**, `unverified_fields=[]`, `created_user_id=null`, `created_session_id=null`. Not `complete`. |
| Same, with `legal_accepted=true` at create | `POST /client/sign_ups` | 200 | `legal_accepted_at` set; verification still `missing_requirements` |
| `PATCH /client/sign_ups/{id}` after verify | PATCH | 200 | still `missing_requirements` |
| `GET /client` after verify | GET | 200 | `sign_up.status=missing_requirements`, `sessions=[]` |
| Weak: length (`Kq7-v`) | sign_ups | 422 | `form_password_length_too_short` (param `password`) |
| Weak: no uppercase | sign_ups | 422 | `form_password_no_uppercase` |
| Weak: no lowercase | sign_ups | 422 | `form_password_no_lowercase` |
| Weak: no number | sign_ups | 422 | `form_password_no_number` |
| Weak: no special char | sign_ups | 422 | `form_password_no_special_char` |
| Weak: zxcvbn (`Password12345678`) | sign_ups | 422 | `form_password_no_special_char` (only this code returned; zxcvbn not isolated) |
| Pwned-like `Password123!` | sign_ups | 422 | `form_password_not_strong_enough` (zxcvbn; HIBP code not observed) |
| Sign-up with missing username only | sign_ups | 422/401 | not observed (request hit dev-browser auth error before fix) |

## Not verified (blocked)

- Duplicate email / duplicate username (`form_identifier_exists` expected): no user was ever created, because sign-ups never reached `complete`; the duplicate sign-ups returned 200. Codes unobserved.
- Sign-in (`identifier=email` / `username`, `attempt_first_factor` password correct/incorrect, unknown identifier): the batch timed out before these ran. Codes unobserved.
- Clerk CLI cleanup: `npx clerk@4.0.0 api` needs a secret key (not provided to this run). No users were created, so none should exist; the unverified sign-up attempts are not users.

## Mismatches against `mobile/lib/auth/account_rules.dart` and `clerk_email_code_actions.dart`

1. **Sign-up completion**: `ClerkSdkEmailCodeActions.verifySignUpCode` assumes a verified sign-up is then complete (session created). Live, the sign-up stays `missing_requirements` with no missing or unverified fields and no session. The app would not reach a signed-in state without handling this status. This is the blocking finding.
2. **Password issue mapping**: `issueFromClerkError` maps any code containing `password` to the password field. Live codes are all `form_password_*`, so the mapping works. But the pwned-branch (`has('pwned')`) is not exercised: `Password123!` returned `form_password_not_strong_enough`, not a pwned code.
3. **Special-character set**: `clerkPasswordSpecialChars` is a local constant. Clerk's live special-char set was not verified against the constant.
4. **Duplicate and sign-in codes** (`identifier_exists`, `identifier_not_found`, `password_incorrect`, `verification_code*`, `code_incorrect`): unverified. Matching cannot be confirmed.

## Next steps

- Determine why sign-up does not complete after email verification on this dev instance (check Clerk dashboard sign-up settings, required fields, and what the Flutter SDK does with `missing_requirements`).
- Re-run the duplicate and sign-in matrix once a verified test user exists, with a secret key available for cleanup.
