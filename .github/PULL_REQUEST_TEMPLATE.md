## Summary

<!-- What changes, and why. Link the issue if there is one. -->

## Area

- [ ] Backend (`src/`)
- [ ] Web shell (`src/daily_agent/web/`)
- [ ] Mobile (`mobile/`)
- [ ] Docs
- [ ] CI or tooling

## Checks

List each check as PASS, FAIL, or NOT RUN (with the reason). See `CONTRIBUTING.md`.

- [ ] `lint`, `typecheck`, `test-unit`, `test-e2e`
- [ ] `test-integration` (money or concurrency changes, or NOT RUN with reason)
- [ ] Mobile gates (for `mobile/` changes)

## Notes

- [ ] Database migration added (new Alembic revision; no applied migration edited)
- [ ] UI change: screenshots use a synthetic test account and show no emails, sign-in codes, phone numbers, or server addresses
- [ ] No secrets, `.env` files, keystores, or personal data in this change
