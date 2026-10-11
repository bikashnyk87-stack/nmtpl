# NMTPL HRMS Render Staging (synthetic data)

This `hrms_dev/` directory is a **temporary, isolated testing workspace**, not the full HRMS application from the Windows PC.

- Branch: `hrms-render-staging` (do not merge into TIOM production main).
- No real employees, payroll, banking, PII, .env files or database backups.
- Python/FastAPI, SQLite under /tmp. **All changes may disappear on restart or redeploy.**
- Set a secret environment variable `HRMS_STAGING_PASSWORD` (at least 16 characters).
- Build: `pip install -r hrms_dev/requirements.txt`
- Start: `cd hrms_dev && uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers`
- Health: `/health`.
- Only a Superadmin test login; all user names and cases in the app are synthetic.
- Atomic Select All bulk approval in one SQLite transaction, audit trail, standard roles, site assignments, master dropdowns.
- A separate persistent private PostgreSQL staging environment and private repository are still needed for the actual full HRMS migration and end-to-end payroll tests.

TIOM production remains on `main` with a different Render service and database.
