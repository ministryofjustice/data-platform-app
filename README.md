# Ministry of Justice Data Platform Application

[![Ministry of Justice Repository Compliance Badge](https://github-community.service.justice.gov.uk/repository-standards/api/data-platform-app/badge)](https://github-community.service.justice.gov.uk/repository-standards/data-platform-app)

[![Open in Dev Container](https://raw.githubusercontent.com/ministryofjustice/.devcontainer/refs/heads/main/contrib/badge.svg)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/ministryofjustice/data-platform-app)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/ministryofjustice/data-platform-app)

## Developer quickstart

1. Clone this repository.
2. Open the project in Visual Studio Code.
3. Reopen in the devcontainer when prompted.
	- You can also run: `Dev Containers: Reopen in Container` from the command palette.
4. Wait for the devcontainer setup to complete.
   - Dependencies are installed automatically by `.devcontainer/post-create.sh`.
   - If setup was interrupted, run:

	```bash
	make install
	```

5. Start the app:

	```bash
	make run
	```

6. Open the local URL shown in the terminal (usually `http://127.0.0.1:8000`).

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
