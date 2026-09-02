# V3-0908 Pilot Operations Runbook

**Status:** Ready for Version 3 pilot use  
**Scope:** Customer support, moderation escalation, feature rollback, data retention and the future openWA boundary  
**Related recovery procedure:** `V3_0907_INCIDENT_RESPONSE_RUNBOOK.md`

## 1. Operating principles

1. Preserve ordinary card gameplay before optional Hybrid services.
2. Protect players before preserving profile visibility, matching or messaging.
3. Collect the minimum information needed to resolve a case.
4. Never ask a player for a password, one-time PIN, full identity document or payment secret through chat or WhatsApp.
5. Record administrator decisions in the existing audit trail.
6. Treat openWA as unavailable until a separately approved implementation slice is complete.

## 2. Roles

- **Support operator:** acknowledges cases, assigns a case reference, records a minimal summary and gathers safe reproduction details.
- **Moderator:** reviews private player reports and custom captions, applies the documented decision states and records a reason.
- **Technical operator:** investigates service faults, uses feature rollback controls and verifies ordinary gameplay.
- **Incident lead:** coordinates critical incidents, maintains the timeline and approves restoration or re-enablement.
- **Privacy/compliance owner:** approves retention exceptions, legal holds, data-access requests and the final openWA rollout.

One person may perform several roles during the local pilot, but the audit must still identify the administrator who made each decision.

## 3. Severity and response targets

| Level | Examples | Target action |
| --- | --- | --- |
| Critical | Active data exposure, account takeover, destructive database event, unsafe messages reaching multiple users | Contain immediately; disable the affected optional service; notify the incident lead |
| High | Credible harassment or threat, repeated unauthorized contact, wrong-recipient message, Hybrid failure affecting many users | Acknowledge within 1 hour; contain and begin review |
| Normal | Individual support problem, caption review, isolated report, tournament question | Acknowledge within 1 business day |
| Low | Product feedback, wording suggestion, non-urgent usability issue | Record and review within 3 business days |

These are internal pilot targets, not contractual service guarantees.

## 4. Customer-support procedure

1. Create a case reference and record the channel, time, broad category and assigned operator.
2. Verify the player using the signed-in account and safe account facts. Do not authenticate from a WhatsApp display name or telephone number alone.
3. Ask only for the tournament ID, match ID, approximate time and a description of what the player saw. Remove passwords, PINs, identity images, payment secrets and unrelated contact details if supplied.
4. Categorise the case as account access, gameplay, tournament/Cup, promotional credit, Hybrid profile, Q-messànger, safety, privacy or feedback.
5. For a safety report, preserve its private in-application report reference and transfer the case to moderation. Do not copy its details into public notes or alerts.
6. For a technical fault, reproduce against a disposable database where possible. Never use the active pilot database for destructive diagnosis.
7. Tell the player what was decided and what they can expect next. Do not promise a cash award, payout or guaranteed commercial match.
8. Close the case with a short outcome code and no unnecessary message transcript.

## 5. Moderation procedure

### Private player reports

1. Review reports only through the administrator-authorised report queue.
2. Confirm the report concerns the recorded player and context; avoid searching unrelated account data.
3. Use `in_review` while evidence is being assessed.
4. For an immediate safety concern, keep the involved profiles and Q-messànger interaction unavailable by using blocks or the relevant Hybrid rollback switch. Ordinary gameplay must remain available unless the account itself requires a separately authorised restriction.
5. Finish as `resolved` when action was required or `rejected` when the report is unsupported or invalid. Record a concise resolution without copying message bodies, identity documents or contact details.
6. The reporter may see their own report state. Full reporter details remain administrator-only.

### Custom captions

1. Keep new or changed custom captions hidden while `pending_review`.
2. Approve only content that is relevant to lawful selling, seeking or collaboration and contains no prohibited contact harvesting, impersonation, harassment, hate, sexual exploitation, fraud or dangerous claims.
3. Reject unsafe content with a short actionable reason. A rejected caption must remain invisible even if an older profile-visibility value is stale.
4. Prefer an administrator-managed structured caption when a safe rewrite is possible.

### Escalation

- Escalate threats, exploitation, credible fraud, repeated evasion or suspected criminal conduct to the incident lead and privacy/compliance owner immediately.
- Preserve only the minimum evidence required. A legal hold must name the case, approving owner, scope, start date and review date.
- Do not confront a reported player through another player's contact details.

## 6. Feature rollback procedure

Use the administrator Hybrid controls. Every change must create or be accompanied by an administrator audit entry and an incident/case reference.

1. **Q-messànger problem:** disable `HYBRID_CHAT_ENABLED` first.
2. **Bad or unsafe matching:** disable `HYBRID_MATCHING_ENABLED`. Use shadow observation only when investigation requires it; otherwise leave shadow off as well.
3. **Profile/contact exposure concern:** disable `HYBRID_PROFILE_ENABLED`. Dependent matching and chat controls must become disabled.
4. **Unknown or multi-service Hybrid incident:** disable `HYBRID_ENABLED`, which disables all editable Hybrid child services.
5. Confirm an authenticated ordinary game page still loads and the active game remains playable.
6. Confirm the administrator metrics page remains readable for privacy-safe incident evidence.
7. If data integrity is in doubt, follow V3-0907: read-only backup, integrity check, side-by-side restoration and explicit stopped-application promotion approval.
8. Re-enable one service at a time only after the cause is understood, regression checks pass and the incident lead records approval.

openWA has no live rollback action in Version 3 because it is not implemented. All five `OPENWA_*` settings must remain false.

## 7. Pilot data-retention schedule

This is the minimum-data Version 3 pilot operating schedule. The compliance owner must confirm it during V3-0909 and approve any legal hold or change.

| Data | Pilot retention | Handling rule |
| --- | --- | --- |
| Q-messànger message bodies | 24 hours | Automatic Redis expiry; no ordinary application-log copy |
| Q-messànger aggregate counters | 180 days | Counts only; no body, caption, contact or preference data |
| Open support cases and private safety reports | While active | Restrict to assigned support, moderators and administrators |
| Closed support-case narrative | 90 days after closure | Keep outcome and minimal troubleshooting facts; remove unnecessary sensitive content |
| Resolved/rejected safety reports | 180 days after closure | Keep for repeat-abuse review and appeals; restrict reporter identity |
| Caption moderation decisions | Profile lifetime plus 180 days | Keep decision, reason and administrator; do not add identity documents |
| Administrator audit logs | 365 days | Immutable operational record; access restricted to administrators |
| Privacy-safe matcher audits and pilot metrics | 180 days | No raw captions, locations, contacts, messages or preferences |
| Recovery backups | 30 days unless incident hold applies | Encrypt and restrict outside local development; verify before deletion |
| openWA/WhatsApp content | Not stored in Version 3 | No integration exists; future design must avoid transcript storage by default |

Account, tournament, credit, qualification, KYC and legally regulated records are not silently deleted by this operational schedule. A verified access, correction or deletion request goes to the privacy/compliance owner for scoped execution and an auditable decision. Legal and integrity obligations may require retaining a limited record.

Run a monthly pilot review for records that passed their retention date. Record the record class, date range, count, approver and outcome—never the deleted private content itself. A future automated deletion job requires its own tested implementation slice.

## 8. Future openWA scaffold

### Approved future purposes

- Customer-support intake and case updates.
- Opted-in operational alerts, such as tournament start or service restoration notices.
- Customer-feedback collection.
- Necessary one-to-one service messages.

It must not replace Q-messànger, expose opponent contact details, relay private game chat, automate moderation decisions, send marketing without consent or affect cards, brackets, results, promotional credits or Cup qualification.

### Current code boundary

- `config.build_openwa_scaffold_config` defines one master and four purpose switches; startup refuses activation.
- `integrations.openwa_scaffold` defines provider-neutral purposes, an outbound request contract and a disabled adapter.
- There is no openWA package dependency, Node worker, session, QR/link login, credential, route, webhook, database table, background job or send capability.

### Required design before implementation

1. Run openWA in a separately supervised Node service or container so a provider/browser failure cannot affect the Flask game process.
2. Use a dedicated business-support number; never a player's number or an administrator's personal account.
3. Accept inbound events only over HTTPS with a secret or stronger request authentication, replay protection, size limits, strict event allowlisting and idempotency.
4. Treat telephone-based chat IDs, names, message text and media metadata as personal information. Never put them in ordinary logs or administrator audit summaries.
5. Map telephone numbers to opaque internal references in a restricted store. Do not expose those mappings to gameplay, matching or Q-messànger.
6. Use approved templates and consent records for outbound alerts; honour opt-out and quiet-hour rules. Human support replies must remain clearly attributable.
7. Store only delivery state, purpose, timestamps, an opaque recipient reference and an idempotency key unless a separately approved case requires content.
8. Quarantine media and links; do not download or open them automatically.
9. Add queue limits, retry bounds, a dead-letter review path and an independent kill switch for every purpose.
10. Make provider outage or account restriction degrade to in-app support without interrupting gameplay.

### Approval gates

Before installing or connecting openWA, obtain:

- product approval for the four message purposes and user wording;
- privacy/compliance approval for consent, retention, access and deletion;
- security review of webhook authentication, secret storage, network boundaries and operator access;
- an assessment of WhatsApp/Meta terms and the operational risk of using an unofficial automation project;
- a pinned, reviewed openWA release and license decision;
- a disposable-number test, failure rehearsal and documented uninstall/rollback path.

The current openWA documentation describes webhook integrations and warns that the project is unofficial and automation may lead to account restrictions. Review the current primary documentation before implementation: <https://openwa.dev> and <https://github.com/open-wa/wa-automate-nodejs>.

## 9. Monthly rehearsal checklist

- [ ] Support can create, categorise, escalate and close a test case without collecting secrets.
- [ ] A moderator can privately review a synthetic report and caption decision with an audit record.
- [ ] Chat-only rollback leaves gameplay active.
- [ ] Master Hybrid rollback leaves gameplay active and metrics readable.
- [ ] Re-enablement follows the dependency order and records approval.
- [ ] Records due for retention review are counted and handled without exposing their contents.
- [ ] All openWA settings remain false and the disabled adapter rejects sending.
- [ ] If recovery is rehearsed, only a disposable database is used and the active database fingerprint remains unchanged.

## 10. Required incident record

Record the case or incident reference, severity, start/detection/containment/recovery times, affected service, affected population estimate, rollback switches used, administrator, minimal evidence references, privacy impact, player communication, root cause, corrective action, re-enable approval and retention/legal-hold decision.
