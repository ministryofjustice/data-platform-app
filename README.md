# Ministry of Justice Data Platform Application

[![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/data-platform-app/badge)](https://github-community.service.justice.gov.uk/repository-standards/data-platform-app)

[![Open in Dev Container](https://raw.githubusercontent.com/ministryofjustice/.devcontainer/refs/heads/main/contrib/badge.svg)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/ministryofjustice/data-platform-app)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ministryofjustice/data-platform-app)

## Developer quickstart

1. Clone this repository.
2. Open the project in Visual Studio Code.
3. Add .env file from [1pass](https://ministryofjustice.1password.eu/app#/WEXD5VMFTVBH7LG7FFDWUV7MC4/Vault/WEXD5VMFTVBH7LG7FFDWUV7MC4:tahmy4wjhm2zr2ld5qbqxl4ufi:civa53euwau6iiayay3pyphcwm?itemListId=WEXD5VMFTVBH7LG7FFDWUV7MC4%3Atahmy4wjhm2zr2ld5qbqxl4ufi)
4. Reopen in the devcontainer when prompted.
   - You can also run: `Dev Containers: Reopen in Container` from the command palette.
5. Wait for the devcontainer setup to complete.
   - Dependencies are installed automatically by `.devcontainer/post-create.sh`.
   - If setup was interrupted, run:

   ```bash
   make install
   ```

6. Start the app:

   ```bash
   make run
   ```

7. Open the local URL shown in the terminal (usually `http://127.0.0.1:8000`).

## Code quality

To check code quality locally:

```bash
make lint
```

To automatically fix formatting issues:

```bash
make format
```

To run tests:

```bash
make test
```

These commands lint and format Python, Django templates, JavaScript, CSS, JSON, and YAML files. See the Makefile for all available development commands.

This repository installs both pre-commit and pre-push hooks. The pre-push hook runs the full lint suite (`make lint`) before a push, to try to avoid annoying super-linter failures in CI.

## Testing

All code changes must include tests. Tests are organized by app/module under `tests/`, mirroring the source structure.

### Run tests

```bash
make test
```

This runs the full test suite with coverage analysis. Tests must maintain **≥90% code coverage** (enforced by CI).

### Coverage

- `make test` generates a `coverage.xml` report and prints a summary.
- Aim for meaningful coverage of business logic, edge cases, and error handling. Avoid low-value tests that only bump numbers.

## Database note

For initial development, we are using SQLite locally.

When we move toward deployment, we will switch local development to PostgreSQL so that development and production environments are aligned.

## Authentication (Microsoft Entra ID)

Users sign in with Microsoft Entra ID (OAuth 2.0 / OpenID Connect), via
[django-azure-auth](https://github.com/Weird-Sheep-Labs/django-azure-auth).

Entra ID is the **sole authentication provider in every environment** — there is
no separate local login, so running the app locally requires real Entra
credentials, set as environment variables (e.g. in your `.env`):

| Variable              | Description                                                |
| --------------------- | ---------------------------------------------------------- |
| `AZURE_CLIENT_ID`     | Application (client) ID from the Entra app registration.   |
| `AZURE_CLIENT_SECRET` | Client secret from the Entra app registration.             |
| `AZURE_AUTHORITY`     | `https://login.microsoftonline.com/<tenant-id>`.           |
| `AZURE_REDIRECT_URI`  | Reply URL registered in Entra, ending in `/sso/callback/`. |

The test suite needs no tenant: tests use `force_login`, and `settings/test.py`
supplies dummy credentials so the app boots without one.

### Enforcement

Login is enforced centrally by Django's `LoginRequiredMiddleware` (deny by
default): every view requires an authenticated user unless it is explicitly
marked `@login_not_required`. The allowlist is the public product pages (home,
roadmap, data factories) and the auth flow itself (`login`, `logout` and the
Entra `callback`, which must stay open because the user is still anonymous while
signing in).

Sessions have an absolute 8-hour lifetime (`SESSION_COOKIE_AGE`), so a user who
loses Entra access is forced back through the provider within a working day.
While their Entra session is still valid this re-login is a silent SSO redirect.

### Admin access

Admin access is granted manually. To do this locally, sign in via Entra once to
create your `User`, then promote it with `make manage shell`. In real
environments you will need to speak to an existing admin.

## Feature flags

This application uses environment-backed feature flags, so features can be turned on or off per
environment without code changes.

Feature flags are read from your `.env` file when Django starts:

| Variable                   | Feature enabled when `true`            |
| -------------------------- | -------------------------------------- |
| `FEATURE_AI_GATEWAY_COSTS` | AI Gateway costs views and related UI. |

Default behaviour:

- If a variable is missing, it defaults to `False` (feature disabled).
- A flag is enabled only when its value is exactly `true` (case-insensitive).

Example `.env` configuration:

```bash
FEATURE_AI_GATEWAY_COSTS=true
```

After updating your `.env`, restart the app (`make run`) so the new flag values are loaded.

## GOV.UK Notify integration

GOV UK Notify is used to send emails. Set these environment variables in your `.env`:

| Variable                                    | Description                                 |
| ------------------------------------------- | ------------------------------------------- |
| `NOTIFY_API_KEY`                            | GOV.UK Notify API key for this service.     |
| `NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID`   | Template ID for the "member added" email.   |
| `NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID` | Template ID for the "member removed" email. |

These secrets can be found in the Data Platform 1Password vault.

If Notify is not configured correctly, project actions still complete, but email delivery failures
are captured in Sentry for monitoring.

## Static assets

Static assets are built as part of `make install` (this runs `make build-static`).

If you change frontend assets during development:

1. Rebuild CSS only:

   ```bash
   make build-css
   ```

2. Rebuild JavaScript assets only:

   ```bash
   make build-js
   ```

3. Rebuild everything under `static/assets`:

   ```bash
   make build-static
   ```

## AI Gateway

To start a local copy of the AI Gateway, run:

```bash
make start-ai-gateway
```

You can then access the AI Gateway at <http://localhost:4000>. The username is `admin` and the password is the value of `LITELLM_MASTER_KEY` in [contrib/docker-compose-ai-gateway.yml](./contrib/docker-compose-ai-gateway.yml).

To have this Django app use your local gateway, add these variables to your `.env`:

```bash
AI_GATEWAY_URL=http://localhost:4000
AI_GATEWAY_MASTER_KEY=sk-123456789 # gitleaks:allow
DEFAULT_ACCESS_GROUP_NAME=generally-available-models
```

`AI_GATEWAY_MASTER_KEY` must match the gateway's `LITELLM_MASTER_KEY` value. If you changed it in Docker compose or your environment, use that value instead. `DEFAULT_ACCESS_GROUP_NAME` is the name of the access group that defines which models are available by default; the app looks up its ID on the gateway at runtime.

The app stores each generated key's secret encrypted at rest (Fernet), so you must
also set a `FIELD_ENCRYPTION_KEY`. Generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then add it to your `.env`:

```bash
FIELD_ENCRYPTION_KEY=your-generated-fernet-key
```

To rotate the encryption key later, set `FIELD_ENCRYPTION_KEY` to a comma-separated
list with the new key first (e.g. `new-key,old-key`); all keys are tried when
decrypting, while only the first is used to encrypt.

After updating `.env`, restart the Django app (`make run`) so the new settings are loaded.

You can also connect to it programmatically using cURL, for example

```bash
curl \
  --header "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
  --request GET \
  http://localhost:4000/settings
```

OpenAPI specification is available at <http://localhost:4000/openapi.json>.
