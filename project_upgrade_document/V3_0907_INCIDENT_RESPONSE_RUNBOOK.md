# V3-0907 Backup Restore and Incident-Response Runbook

**Status:** Rehearsed successfully on 1 September 2026  
**Scope:** Version 3 MVP local/pilot SQLite deployment  
**Safety rule:** Never restore directly over `instance/dealuxe_game.db`. Restore and verify a separate file first. Promotion requires the application to be stopped and explicit operator approval.

## When to use this runbook

Use this procedure when important records appear missing or damaged, the database fails an integrity check, a faulty deployment changes stored data, or a privacy/security incident requires the Hybrid features to be contained while gameplay availability is assessed.

## Immediate response

1. Stop making non-essential changes. Record the incident start time, reporter and symptoms.
2. If Hybrid privacy, matching or chat may be involved, use the administrator settings to turn off the Hybrid parent switch. This also disables profiles, live/shadow matching and Q-messànger chat.
3. Confirm that ordinary gameplay pages remain available. Do not re-enable Hybrid until the cause and data state are understood.
4. Preserve relevant application and administrator audit logs. Do not copy message bodies, contact details, captions, credentials or raw private preferences into the incident report.
5. Create a verified SQLite backup before attempting repair. A backup is evidence as well as a recovery source; do not modify it.

## Safe backup and restore rule

The recovery utility is `tools/database_recovery.py`.

- `backup` reads the source through SQLite's read-only backup interface and writes a new destination file.
- `restore` first verifies the backup, then creates a new side-by-side restored file.
- `verify` returns only table counts and SHA-256 content hashes. It does not print row contents.
- Existing destinations are never overwritten.
- Any restore destination ending in `instance/dealuxe_game.db` is rejected.

The live database may be used as a read-only backup source. It may not be an automated restore destination.

## Verification gate

Before a restored database can be considered for promotion, verify:

- SQLite reports `integrity_check = ok`.
- Critical table sets, row counts and privacy-safe content hashes match the selected backup.
- Users and password hashes exist.
- Promotional-credit balances and expiries exist.
- Tournaments, participants and active game-room records exist.
- Discovery profiles, blocks/reports where applicable, Hybrid settings and aggregate metrics exist.
- Pricing settings, paid-plan purchase records and entitlement expiries exist.
- Administrator audit records exist.
- Authentication, one ordinary game page and the required Hybrid-disabled fallback behave correctly in a test process bound to the restored file.

If any check differs unexpectedly, reject the restore and retain both files for investigation.

## Promotion to active service

Promotion is intentionally outside the automated utility.

1. Obtain explicit owner/operator approval for the exact verified restored file.
2. Stop the application and all workers so no connection can write during replacement.
3. Preserve the damaged database and its `-wal`/`-shm` companions as incident evidence; never silently delete them.
4. Move the verified restored file into place using the host's approved recoverable file procedure.
5. Start one controlled application instance with Hybrid still disabled.
6. Re-run critical smoke checks and inspect logs before allowing users back.
7. Re-enable individual Hybrid switches only after privacy, matching and chat checks pass and the incident owner approves recovery.

## 1 September 2026 rehearsal evidence

The automated exercise used only uniquely named temporary SQLite files. It created representative records covering fifteen critical tables, including referral codes, referral attribution, wallet transactions, pricing settings, paid-plan purchases and entitlements, produced a consistent backup, disabled all editable Hybrid switches, confirmed the ordinary game page still rendered, deliberately removed tournament/profile/referral/pricing records and promotional balances from the disposable source, restored the backup into a second file and compared privacy-safe manifests.

- Backup: **28.319 ms**
- Side-by-side restore plus verification: **25.097 ms**
- Critical tables verified: **15**
- Protected live-path overwrite attempts rejected: **yes**
- Local pilot database SHA-256 unchanged: **yes**

These timings prove the small isolated rehearsal, not a production recovery-time commitment. A larger real backup must be measured on the deployment host.

## After the incident

Record the timeline, affected features, evidence locations, containment actions, backup chosen, verification results, approvals and final recovery time. Identify the underlying cause and create follow-up actions before closing the incident. Do not include secrets or unnecessary personal information in the report.
