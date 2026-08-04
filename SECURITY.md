# Security Policy for Lakebranch

Lakebranch is a **local-first** developer tool. Its threat model assumes the stack runs on your own machine with default, non-secret credentials — but the `aws-s3` profile raises real-cloud stakes, so this policy is explicit about scope and expectations.

## Reporting a vulnerability

- **Do NOT open a public GitHub issue** for security problems. That alerts attackers before maintainers can respond.
- **Report via a private security advisory** — GitHub's Security tab, "Report a vulnerability". Reports route privately to the maintainers.
- **Include:** commit hash/version, OS, Python version, reproduction steps, expected vs. actual behavior, and a severity assessment if you have one.

We aim to acknowledge reports within 7 days and to issue a fix in a timely manner depending on severity.

## In scope

- The Python core (`src/lakebranch/`)
- The FastAPI GUI backend (`src/lakebranch/api/`)
- The Docker Compose profiles and any secrets they handle
- The Airflow provider package (`airflow-providers-lakebranch/`)

## By design, not vulnerabilities

- **No authentication in the GUI.** The web UI is a localhost developer preview binding to `127.0.0.1` by default. **Do not expose the Lakebranch GUI or lakehouse ports (8787, 19120, 9000) to untrusted networks.** The API is read/query-first with no auth layer by design.
- **Default object-store credentials.** SeaweedFS/Nessie default to `minioadmin`/`minioadmin` for local development. Change or keep them strictly local when exposing the stack.
- **Local-only demo dataset.** `lakebranch init-demo` writes sample data (users, orders, events). Do not treat it as production data.

## Credential safety

- `.env` is git-ignored and must never be committed. Only `.env.example` is tracked.
- For the `aws-s3` (BYOC) profile: use least-privilege IAM credentials scoped to the warehouse bucket, never commit `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, and rotate them if ever exposed.

## Supported versions

Lakebranch is pre-1.0 (v0.1.0). Security fixes apply to the current `master` and the latest released version; no LTS releases yet.