# Ministry of Justice Data Platform Application

[![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/data-platform-app/badge)](https://github-community.service.justice.gov.uk/repository-standards/data-platform-app)

[![Open in Dev Container](https://raw.githubusercontent.com/ministryofjustice/.devcontainer/refs/heads/main/contrib/badge.svg)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/ministryofjustice/data-platform-app)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ministryofjustice/data-platform-app)

## Developer quickstart

1. Clone this repository.
2. Open the project in Visual Studio Code.
3. Add .env file from [1pass](https://ministryofjustice.1password.eu/app#/WEXD5VMFTVBH7LG7FFDWUV7MC4/Vault/WEXD5VMFTVBH7LG7FFDWUV7MC4:skgdudwgk3ojqiwigoxrmpngle:2cjgikrcktdhwpoeleoo4jomr4?itemListId=WEXD5VMFTVBH7LG7FFDWUV7MC4%3Askgdudwgk3ojqiwigoxrmpngle)
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
