##### BUILD PYTHON

FROM docker.io/library/ubuntu:26.04@sha256:53958ec7b67c2c9355df922dd08dbf0360611f8c3cdb656875e81873db9ffdba AS build-python

SHELL ["/bin/bash", "-e", "-u", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive

RUN <<EOF
apt-get update --quiet --yes
apt-get install --quiet --yes \
    --no-install-recommends \
    ca-certificates=20260223 \
    python3.14-dev=3.14.4-1
EOF

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 /uv /usr/local/bin/uv

# - Silence uv complaining about not being able to use hard links,
# - tell uv to byte-compile packages for faster application startups,
# - prevent uv from accidentally downloading isolated Python builds,
# - pick the Python interpreter,
# - and finally declare `/app` as the target for `uv sync`.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/bin/python3.14 \
    UV_PROJECT_ENVIRONMENT=/app

# Synchronize DEPENDENCIES without the application itself.
# This layer is cached until uv.lock or pyproject.toml change
RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync \
        --locked \
        --no-dev \
        --no-install-project

##### BUILD NODE

FROM docker.io/library/node:24.16.0@sha256:40ad9f3064e67d6860b4bc3fe1880b2953934fd6320ada990e45fe0efa6badd7 AS build-node

WORKDIR /build

COPY package.json package-lock.json ./
COPY /scss/ ./scss/

RUN <<EOF
npm ci

npm run css
EOF

##### FINAL

FROM docker.io/library/ubuntu:26.04@sha256:53958ec7b67c2c9355df922dd08dbf0360611f8c3cdb656875e81873db9ffdba AS final

LABEL org.opencontainers.image.vendor="Ministry of Justice" \
      org.opencontainers.image.authors="Data Platform Services (justicedataplatform@justice.gov.uk)" \
      org.opencontainers.image.title="Data Platform App" \
      org.opencontainers.image.description="Data Platform App image for Justice data Platform" \
      org.opencontainers.image.url="https://github.com/ministryofjustice/data-platform-app"

SHELL ["/bin/bash", "-e", "-u", "-o", "pipefail", "-c"]

ENV CONTAINER_USER="dataplatform" \
    CONTAINER_UID="10001" \
    CONTAINER_GROUP="dataplatform" \
    CONTAINER_GID="10001" \
    DEBIAN_FRONTEND="noninteractive" \
    APP_ROOT="/app" \
    PATH="/app/bin:${PATH}"

RUN <<EOF
groupadd \
    --gid ${CONTAINER_GID} \
    ${CONTAINER_GROUP}

useradd \
    --uid ${CONTAINER_UID} \
    --gid ${CONTAINER_GROUP} \
    --create-home \
    --shell /bin/bash \
    ${CONTAINER_USER}
EOF

RUN <<EOF
apt-get update --quiet --yes

apt-get install --quiet --yes \
    --no-install-recommends \
    ca-certificates=20260223 \
    python3.14=3.14.4-1


apt-get clean --yes

rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
EOF

COPY docker-entrypoint.sh /

# Copy the pre-built `/app` directory to the runtime container
# and change the ownership to user app and group app in one step.
COPY --from=build-python --chown=${CONTAINER_USER}:${CONTAINER_GROUP} ${APP_ROOT} ${APP_ROOT}

# Copy compiled assets
COPY --from=build-node --chown=${CONTAINER_USER}:${CONTAINER_GROUP} /build/static/assets/css/app.css ${APP_ROOT}/static/assets/css/app.css
COPY --from=build-node --chown=${CONTAINER_USER}:${CONTAINER_GROUP} /build/node_modules/govuk-frontend/dist/govuk/assets/fonts/. ${APP_ROOT}/static/assets/fonts
COPY --from=build-node --chown=${CONTAINER_USER}:${CONTAINER_GROUP} /build/node_modules/govuk-frontend/dist/govuk/assets/images/. ${APP_ROOT}/static/assets/images
COPY --from=build-node --chown=${CONTAINER_USER}:${CONTAINER_GROUP} /build/node_modules/govuk-frontend/dist/govuk/govuk-frontend.min.js ${APP_ROOT}/static/assets/js/govuk-frontend.min.js
COPY --from=build-node --chown=${CONTAINER_USER}:${CONTAINER_GROUP} /build/node_modules/@x-govuk/govuk-prototype-components/dist/govuk-prototype-components.min.js ${APP_ROOT}/static/assets/js/govuk-prototype-components.min.js
COPY --from=build-node --chown=${CONTAINER_USER}:${CONTAINER_GROUP} /build/node_modules/@x-govuk/govuk-prototype-components/dist/govuk-prototype-components.min.js.map ${APP_ROOT}/static/assets/js/govuk-prototype-components.min.js.map
COPY --from=build-node --chown=${CONTAINER_USER}:${CONTAINER_GROUP} /build/node_modules/@ministryofjustice/frontend/moj/assets/images/. ${APP_ROOT}/static/assets/images

COPY --chown=${CONTAINER_USER}:${CONTAINER_GROUP} assets/images/. ${APP_ROOT}/static/assets/images
COPY --chown=${CONTAINER_USER}:${CONTAINER_GROUP} manage.py ${APP_ROOT}/manage.py
COPY --chown=${CONTAINER_USER}:${CONTAINER_GROUP} data_platform_app ${APP_ROOT}/data_platform_app
COPY --chown=${CONTAINER_USER}:${CONTAINER_GROUP} templates ${APP_ROOT}/templates
COPY --chown=${CONTAINER_USER}:${CONTAINER_GROUP} tests ${APP_ROOT}/tests
COPY --chown=${CONTAINER_USER}:${CONTAINER_GROUP} users ${APP_ROOT}/users
COPY --chown=${CONTAINER_USER}:${CONTAINER_GROUP} pyproject.toml ${APP_ROOT}/pyproject.toml

RUN mkdir -p /app/staticfiles && chown ${CONTAINER_USER}:${CONTAINER_GROUP} /app/staticfiles

USER ${CONTAINER_USER}
WORKDIR ${APP_ROOT}

RUN python manage.py collectstatic --noinput --settings=data_platform_app.settings.production

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]
