NORTHBROWN 2.0.14 — Connected Mailbox & Reply Inbox
====================================================

STATUS: STAGED RELEASE. The live NORTHBROWN OTA feed remains intentionally paused at 2.0.8 while the older recovery chain is protected. This release does NOT change northbrown/update.json.

New in 2.0.14
- Send the first approved personalised outreach email from the configured NORTHBROWN SMTP mailbox.
- Record Message-ID / thread metadata for reliable reply matching.
- New in-app Inbox with Interested, Needs Reply, Demo Requested, Not Interested and Do Not Contact views.
- Pull matched IMAP replies into prospect conversation threads.
- AI/rule reply classification with confidence and suggested action.
- Editable AI reply drafts; human approval is always required before a reply sends.
- Two safe follow-ups after the first email is human-approved: +4 business days and +11 business days from the first send.
- Any genuine human reply cancels queued/scheduled outreach before AI classification runs.
- Explicit opt-outs suppress the address and cancel all future outreach.
- Hard bounces suppress the failed address.
- Out-of-office messages pause the sequence and resume after the detected return date (or a safe seven-day fallback).
- One-business/domain lock prevents simultaneous sequences to multiple contacts at the same small-business domain.
- Manual pause, stop, Do Not Contact and Mark Client controls.
- Existing email_log/replies remain visible in merged thread history where available.

Safety / compatibility
- OTA ZIP is intended for NORTHBROWN 2.0.13 -> 2.0.14.
- The separate SAFE INSTALLER can start from 2.0.8, 2.0.11, 2.0.12 or 2.0.13: it runs the already-verified 2.0.13 recovery first when needed, then installs 2.0.14.
- data/, .env, .venv, prospects, scans, API keys and stored SMTP/IMAP settings are not replaced.
- The installer verifies both embedded package sizes and SHA-256 hashes before changing app code and creates a rollback backup.

Release ZIP SHA-256:
9bf81a3495b54aac35cc9610a23b8e9614fb53c1132da75206587d6fc6913126

Safe installer size: 275334 bytes
Safe installer SHA-256: 87888047a48df5bc967bb2903d378d9da7e349a6b618bda31bba260183a0e92c
