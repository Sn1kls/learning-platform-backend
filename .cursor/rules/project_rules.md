---
description: Comprehensive rules for working on the learning-platform-backend project.
globs: "**/*.py", "**/*.html", "Makefile", "docker-compose*.yaml"
---
# Project Rules: learning-platform-backend

## Tech Stack
- **Language**: Python 3.13+
- **Framework**: Django 4.x+, Django Ninja (API), Django Extensions
- **Task Queue**: Celery with Redis
- **Database**: PostgreSQL (psycopg2-binary)
- **Containerization**: Docker, Docker Compose
- **Testing**: Pytest, pytest-django, pytest-cov
- **Linting/Formatting**: Ruff
- **Commits**: Commitizen (Conventional Commits)

## Coding Standards

### Python
- **Style**: Follow PEP 8 guidelines. Ruff is used for linting and formatting.
- **Type Hinting**: Use type hints for function arguments and return values.
- **Imports**: Sorted by Ruff (isort compatible).
- **Docstrings**: Required for all public modules, classes, and functions. Use Google style.

### APIs (Django Ninja)
- Use `Router` for grouping related endpoints.
- Use `Schema` (Pydantic) for request/response validation.
- Return structured errors.

### Security
- No hardcoded secrets. Use environment variables.
- Standard Django security practices (CSRF, XSS protection).

### Internationalization
- All user-facing strings MUST be marked for translation using `gettext_lazy` (imported as `_`).
- Example: `raise ValueError(_("Invalid email format"))`

### API Responses
- ALWAYS use Pydantic Schemas for response data.
- POSITIVELY NO ad-hoc dictionaries `{"message": "..."}` in responses. Create a schema (e.g., `MessageResponseSchema`).
- Use `ninja_extra` or standard `ninja` features to ensure correct documentation.

## Processes

### Commits
- Follow Conventional Commits format: `type(scope): description`.
- **Types**: `fix`, `feat`, `docs`, `style`, `refactor`, `test`, `build`.
- **Scope**: Usually the Jira ticket ID (e.g., `SWUA-123`) or component name.
- Example: `feat(SWUA-101): add user profile endpoint`

### Testing
- Write tests for all new features and bug fixes.
- Run tests using `make tests`.
- Ensure coverage does not drop below 80%.

### Database Migrations
- Create migrations: `make migrations`
- Apply migrations: `make migrate`
- Do not modify existing migration files unless absolutely necessary (and safe).

## Common Commands (Makefile)
- `make build`: Build docker containers.
- `make upd`: Start containers in detached mode.
- `make migrate`: Apply migrations.
- `make migrations`: Create new migrations.
- `make superuser`: Create a superuser.
- `make tests`: Run tests.
- `make collectstatic`: Collect static files.
