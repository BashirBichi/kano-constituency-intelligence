# Kano Constituency Intelligence (KCI)

**Local knowledge. Reliable data.**

KCI is a constituency-level field research and data intelligence platform. It demonstrates a structured workflow for collecting community observations, attributing sources, reviewing evidence, analysing issue patterns and exporting records for reporting.

## Current MVP
- Authentication and role-gated access (admin, analyst, field agent, viewer)
- Observation registry organized by LGA, ward, category and date
- Source attribution and optional evidence links
- Verification workflow: pending, verified and rejected
- Dashboard KPIs and charts by category and LGA
- Search and filtering
- CSV export
- CSRF protection, password hashing and audit-relevant attribution fields
- PostgreSQL in deployment; SQLite fallback for local development

## Important data-integrity note
Any seeded records are explicitly illustrative demonstration data. They are not official Kano State statistics, verified field findings or statements about actual communities. Replace them only with properly sourced information and retain source details.

## Local setup
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
flask --app app init-db
flask --app app seed-demo
flask --app app run
```

Set `SECRET_KEY` and `DEMO_PASSWORD` before creating a demo account. The seed command creates `demo@kci.local` only when the database has no users. Do not use the default development password in production.

## Render deployment
The application binds to Render's `PORT` and uses `DATABASE_URL`. Set:
- `SECRET_KEY`: long random secret
- `DATABASE_URL`: Render PostgreSQL internal connection string
- `COOKIE_SECURE=true`

After first deployment, run `flask --app app seed-demo` as a one-off command only if you intentionally want sample data. Configure a strong `DEMO_PASSWORD` first, then remove or disable the demo account after onboarding.

## Roadmap
- Kano State's official constituency/LGA/ward reference data import
- Structured survey instruments and multilingual Hausa/English forms
- Evidence attachments with private object storage
- Change history and immutable verification audit events
- PDF analytical briefs with transparent methodology
- Geographic visualization after validated boundary datasets are sourced
- Automated data-quality checks and time-series comparisons

## Disclaimer
This is an independent portfolio demonstration. It is not affiliated with Skymirror, Kano State Government, INEC or any political organization. The platform does not contain official constituency data unless explicitly sourced and labelled.
