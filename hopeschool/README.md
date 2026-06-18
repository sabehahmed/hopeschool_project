# HopeSchool — Tunisian Hope & Future Early Warning Platform

**SESAME University — Django Exam Project 2025–2026**
**Course:** Python Web Programming (Django) — Chaouki Bayoudhi

---

## Project Overview

HopeSchool is a Django-based early warning platform that detects school disengagement risk in Tunisian students through absence tracking, rule-based risk scoring, intervention planning, and audit-logged workflows.

**Scenario:** School Absenteeism Early-Warning Dashboard

---

## Quick Start

### 1. Install dependencies

```bash
pip install django djangorestframework pytest pytest-django pytest-cov pandas
```

### 2. Run migrations and seed demo data

```bash
python manage.py migrate
python manage.py seed_data
```

### 3. Start the server

```bash
python manage.py runserver
```

Visit: **http://127.0.0.1:8000/login/**

---

## Demo Accounts

| Username   | Password      | Role       | Permissions                          |
|------------|---------------|------------|--------------------------------------|
| operator   | operator123   | Operator   | Create/view students, record absences, bulk upload |
| supervisor | supervisor123 | Supervisor | + Compute risk, manage interventions, export CSV |
| admin      | admin123      | Admin      | Full access + delete + audit config  |

---

## Key Features

### Scenario 1 — Education Early Warning (fully implemented)
- Student intake via form or CSV bulk upload
- Unjustified absence tracking with duplicate-prevention
- Rule-based risk scoring (configurable high/medium thresholds)
- Dashboard with 4 KPIs + 14-day absence chart
- Alert creation for high/medium risk students
- Intervention plan creation with state machine (draft → active → follow_up → closed)
- CSV export report with risk scores and explanations
- Full audit trail for every action

### Failure Injection Cases (testable)
- Future-dated absence → rejected with error
- Duplicate absence same day → blocked (DB constraint)
- Malformed CSV upload → rejected, no partial records, audit-logged
- Invalid state transition (draft → closed) → ValidationError
- Operator accessing supervisor panel → 403 + audit-logged
- Future date of birth → rejected

### 3 User Roles
- **Operator**: data entry (students, absences, bulk upload)
- **Supervisor**: risk scoring, thresholds, interventions, exports
- **Admin**: all of the above + delete + audit config

---

## Project Structure

```
hopeschool/
├── config/
│   ├── settings.py
│   └── urls.py
├── earlywarning/
│   ├── models.py          # Student, AbsenceRecord, RiskScore, InterventionPlan, Alert, AuditLog
│   ├── views.py           # All Django views
│   ├── api_views.py       # DRF ViewSets
│   ├── serializers.py     # DRF serializers with validation
│   ├── services.py        # RiskScoringService, AlertService (business logic)
│   ├── forms.py           # Django forms with validation
│   ├── permissions.py     # Role-based access decorators
│   ├── admin.py           # Django admin registration
│   ├── urls.py            # URL routing (web + API)
│   ├── templates/         # HTML templates (Bootstrap 5)
│   └── management/commands/seed_data.py
├── tests/
│   ├── test_models.py     # Model validation tests
│   ├── test_services.py   # Risk scoring / alert logic tests
│   └── test_views.py      # Permission + view + bulk upload tests
├── pytest.ini
└── README.md
```

---

## Running Tests

```bash
# All tests with verbose output
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=earlywarning --cov-report=term-missing

# Run a specific category
pytest tests/test_models.py -v
pytest tests/test_services.py -v
pytest tests/test_views.py -v
```

Expected: **33 tests, all passing**.

---

## API Endpoints (DRF)

Base URL: `/api/`

| Endpoint                              | Methods         | Role Required       |
|---------------------------------------|-----------------|---------------------|
| `/api/students/`                      | GET, POST       | Operator+           |
| `/api/students/{id}/`                 | GET, PUT, PATCH | Operator+           |
| `/api/students/{id}/`                 | DELETE          | Admin only          |
| `/api/students/{id}/compute_risk/`    | POST            | Supervisor+         |
| `/api/students/{id}/timeline/`        | GET             | Operator+           |
| `/api/students/{id}/recommend/`       | GET             | Supervisor+         |
| `/api/students/alerts_summary/`       | GET             | Supervisor+         |
| `/api/absences/`                      | GET, POST       | Operator+           |
| `/api/risk-scores/`                   | GET             | Supervisor+         |
| `/api/interventions/`                 | GET, POST, PATCH| Supervisor+         |
| `/api/alerts/`                        | GET             | Supervisor+         |
| `/api/alerts/dashboard_alerts/`       | GET             | Supervisor+         |
| `/api/audit-logs/`                    | GET             | Supervisor+         |

---

## Advanced Track A — Architecture & Performance

- **Service layer**: `services.py` separates business logic from views
- **ORM optimisation**: `select_related` and `prefetch_related` on all list queries
- **Indexed fields**: `(school, grade)`, `(region)`, `(student, date)` on AbsenceRecord
- **Modular design**: models / services / views / api_views / serializers / permissions

---

## Ethics & Data Governance

- All data is **synthetic** — no real personal records used
- Role-based visibility: operators cannot see audit logs or risk thresholds
- Every sensitive action is audit-logged with user, timestamp, result, and IP
- Risk explanations are always human-readable — no black-box decisions
- Alerts contain the evidence text that triggered them
- Unauthorized access attempts are blocked **and** logged

---

## Risk Register (docs/)

| Risk | Category | Mitigation |
|------|----------|------------|
| False high-risk alerts | Decision | Configurable thresholds; human must create intervention manually |
| Unauthorized data access | Security | Role-based decorators on all views + API |
| Silent workflow failures | Operational | AuditLog records every action result (success/failure/blocked) |
| Poor data quality (CSV) | Data | Schema validation + row-level error reporting |
| Over-interpretation of scores | Ethical | Explanations always shown; labeled "decision support, not final authority" |
