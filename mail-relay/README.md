# Mail relay – Role 3 (Shi Wang)

Local stand-in for two Azure services, so alerts can be seen on one computer without an email or SMS provider:

| Azure (deployed) | Local request | Result in the Mailpit inbox (http://localhost:8025) |
|---|---|---|
| Email Logic App → Azure Communication Services | `POST /` with the alert JSON | one email per alert |
| SMS Logic App → Azure Monitor action group (Part 4, F13) | `POST /sms` with `{"alert_id","truck_id","type","text"}` | one message marked `[SMS]` |

* Requests must carry `Authorization: Bearer <MAIL_RELAY_TOKEN>` (created by `scripts/init_local.py`).
* Each alert ID is sent **once**: receipts are kept in a small SQLite file on a volume (`RECEIPTS_DB`), so a retried request
  after a lost reply does not send a second email or text.
* The Functions app treats the relay exactly like the Logic Apps; only the address changes (`LOGIC_APP_URL`, `SMS_URL`).

Tests: `python -m pytest` (13 tests: email and SMS format, duplicate suppression across restarts, retries, credential checks).
