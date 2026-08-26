.PHONY: run install npm-install build-css build-js build-static lint format lint-templates format-templates test start-ai-gateway stop-ai-gateway mcp

run:
	uv run python manage.py makemigrations --check
	uv run python manage.py migrate
	uv run python manage.py runserver

install:
	uv sync --locked
	$(MAKE) npm-install
	@if [ -d .git ]; then \
		uv run pre-commit install --hook-type pre-commit --hook-type pre-push; \
	else \
		echo "Skipping pre-commit hook installation: not inside a git checkout."; \
	fi
	$(MAKE) build-static

npm-install:
	npm ci

build-css:
	rm -rf static/assets/fonts
	rm -rf static/assets/images
	rm -rf static/assets/css
	mkdir -p static/assets/fonts
	mkdir -p static/assets/images
	mkdir -p static/assets/css
	cp -R node_modules/govuk-frontend/dist/govuk/assets/fonts/. static/assets/fonts
	cp -R node_modules/govuk-frontend/dist/govuk/assets/images/. static/assets/images
	cp -R node_modules/@ministryofjustice/frontend/moj/assets/images/. static/assets/images
	cp -R assets/images/. static/assets/images
	npm run css

build-js:
	rm -rf static/assets/js
	mkdir -p static/assets/js
	npm run build:js
	cp node_modules/govuk-frontend/dist/govuk/govuk-frontend.min.js static/assets/js/govuk-frontend.min.js
	cp node_modules/govuk-frontend/dist/govuk/govuk-frontend.min.js.map static/assets/js/govuk-frontend.min.js.map
	cp node_modules/@ministryofjustice/frontend/moj/moj-frontend.min.js static/assets/js/moj-frontend.min.js
	cp node_modules/@ministryofjustice/frontend/moj/moj-frontend.min.js.map static/assets/js/moj-frontend.min.js.map
	cp node_modules/@x-govuk/govuk-prototype-components/dist/govuk-prototype-components.min.js static/assets/js/govuk-prototype-components.min.js
	cp node_modules/@x-govuk/govuk-prototype-components/dist/govuk-prototype-components.min.js.map static/assets/js/govuk-prototype-components.min.js.map

build-static:
	rm -rf static/
	$(MAKE) build-css
	$(MAKE) build-js
	uv run python manage.py collectstatic --noinput

lint:
	ruff format --check
	ruff check
	$(MAKE) lint-templates
	npx prettier . --check

format:
	ruff format
	ruff check --fix
	$(MAKE) format-templates
	npx prettier . --write

lint-templates:
	uv run djlint templates --lint --profile=django

format-templates:
	uv run djlint templates --reformat --profile=django

test:
	DB_USER=data_platform_app \
	DB_PASSWORD=data_platform_app \
	DB_NAME=data_platform_app \
	uv run pytest --failed-first --maxfail=5 $(ARGS)

start-ai-gateway:
	bash contrib/ai-gateway/start.sh

stop-ai-gateway:
	docker compose --file contrib/docker-compose-ai-gateway.yml down --remove-orphans

mcp:
	@if [ -z "$$MCP_USER_EMAIL" ]; then \
		echo "Error: MCP_USER_EMAIL is not set."; \
		echo "Usage: MCP_USER_EMAIL=you@example.com make mcp"; \
		exit 1; \
	fi
	uv run python -m data_platform_mcp.cli
