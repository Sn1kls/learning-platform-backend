# Learning Platform (backend)

The backend of an online mental health course: people join a cohort, go through modules and lessons that unlock on a schedule, earn points, and take a mental health self-assessment before and after the course.

This is my diploma project (TNTU, 2026). It is based on the backend of Soulvia, a real e-learning platform with about 500 users that I worked on at Maze Logic. It's published here with the agreement of Maze Logic, with the branding removed. Some parts of the original were written by teammates, see [My part](#my-part).

## What it does

- **Accounts:** email registration with a profile, email activation, JWT login with refresh rotation, password reset, soft delete.
- **Cohorts:** registration windows and start dates, automatic enrollment into the active cohort, and a consent step that gates all content.
- **Course:** modules unlock on the cohort's schedule, and lessons (text, video, audio, quiz, homework) must be completed in order.
- **Points and progress:** fixed points per lesson type, quiz scoring with partial credit and best attempt, progress tracking.
- **Quizzes and homework:** text, single- and multiple-choice questions; homework as text or files, approved automatically or by a reviewer.
- **Mental health test:** the same survey before and after the course.
- **Chat invitations** by age group and a general chat, by email and through the API.
- **Admin panel** on django-unfold: rich text, drag-and-drop ordering, CSV export, manual emails.

## Stack

Python 3.13, Django 5.2, Django Ninja (JWT), PostgreSQL 17, Redis 7 (django-redis), S3-compatible storage (DigitalOcean Spaces), SendGrid / SMTP, loguru + Sentry, pytest with an 80% coverage gate, ruff, Docker Compose with gunicorn and nginx, GitHub Actions for CI and deploys over SSH. UI texts in Ukrainian and English.

## My part

- REST API endpoints on Django Ninja, covered by pytest behind the 80% coverage gate in CI, plus ruff and bandit.
- Soft deletion of users.
- Per-endpoint API rate limiting backed by Redis.
- Chat invitation logic that takes a user's groups into account.
- Wiring in the custom admin application and its routing.

## Running locally

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen --no-cache
```

Translations:

```bash
python manage.py makemessages -l en
python manage.py compilemessages
```

Formatting and linting:

```bash
ruff format .
ruff check . --fix
```

The full product and data model description is in [CONCEPT.md](CONCEPT.md).
