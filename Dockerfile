##### BUILD PYTHON

FROM public.ecr.aws/ubuntu/ubuntu:26.04@sha256:215ce47dc5c697ba3bcda7367ac1f6448d039306017d3c6a539dcefd2911efdb AS build-python

SHELL ["/bin/bash", "-e", "-u", "-o", "pipefail", "-c", "-x"]

ENV DEBIAN_FRONTEND=noninteractive

RUN <<EOF
apt-get update --quiet --yes
apt-get install --quiet --yes \
    --no-install-recommends \
    python3.14-dev \
    ca-certificates
EOF

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv

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

FROM public.ecr.aws/docker/library/node:24.11.1 AS build-node

WORKDIR /build

COPY package.json package-lock.json ./
COPY /scss/ ./scss/

RUN <<EOF
npm install

npm run css
EOF

##### FINAL

FROM public.ecr.aws/ubuntu/ubuntu:26.04@sha256:215ce47dc5c697ba3bcda7367ac1f6448d039306017d3c6a539dcefd2911efdb AS runtime

LABEL org.opencontainers.image.vendor="Ministry of Justice" \
      org.opencontainers.image.authors="Data Platform Services (justicedataplatform@justice.gov.uk)" \
      org.opencontainers.image.title="Data Platform App" \
      org.opencontainers.image.description="Data Platform App image for Justice data Platform" \
      org.opencontainers.image.url="https://github.com/ministryofjustice/data-platform-app"

SHELL ["sh", "-exc"]

# Add the application virtualenv to search path.
ENV PATH=/app/bin:$PATH

# Don't run your app as root.

ENV CONTAINER_USER="dataplatform" \
    CONTAINER_UID="10001" \
    CONTAINER_GROUP="dataplatform" \
    CONTAINER_GID="10001" \
    DEBIAN_FRONTEND="noninteractive" \
    APP_ROOT="/app"


RUN <<EOF
#!/usr/bin/env bash
userdel --remove --force ubuntu

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


# See <https://hynek.me/articles/docker-signals/>.
STOPSIGNAL SIGINT

RUN <<EOF
#!/usr/bin/env bash
apt-get update --quiet --yes
apt-get install --quiet --yes \
    --no-install-recommends \
    python3.14 \
    ca-certificates
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

# collect static using production settings, but ONLY for this command
RUN python manage.py collectstatic --noinput --settings=data_platform_app.settings.production

EXPOSE 8000
ENTRYPOINT ["/docker-entrypoint.sh"]
