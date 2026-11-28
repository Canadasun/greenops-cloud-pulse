# Sign-in token API – Role 5 (Idowu Ayeni)

`GET /api/token` runs inside **Azure Static Web Apps** next to the dashboard (Part 4, F12). Static Web Apps signs the person in with
their Microsoft account and passes who they are in the `x-ms-client-principal` header; this function turns that into a
**15-minute session token** (HS256, signed with `SESSION_SIGNING_KEY`, which Terraform creates and stores only in the app settings).

* No sign-in → `401`; the token holds only the email address, issuer, audience and expiry.
* The dashboard keeps the token in memory and sends it to the Fleet API, which checks it with `functions/shared/session.py`.
  Any signed-in account may read; only `OPERATOR_EMAILS` may act (`functions/shared/auth.py`).
* `src/token.js` is also used by `local-auth/` (the local stand-in for the Microsoft sign-in) and by the live Azure check,
  so all three issue exactly the same token.
* Deployed with the dashboard: `scripts/deploy_azure_app.sh` passes `--api-location swa-api`.

Tests: `npm install && node --test` (10 tests, including a check that Python's `session.verify` accepts the tokens this code makes;
set `GREENOPS_PYTHON` to an interpreter with the Functions requirements).
