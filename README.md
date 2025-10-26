# stage-2

Minimal infra repo for an nginx front with blue/green backend containers.

Quick start

1. Copy `.env.example` to `.env` and edit values.
2. Run:

```bash
docker-compose up -d
```

Notes
- This repository contains deployment artifacts (docker-compose, nginx templates, CI workflow). It does not contain application source code — the `BLUE_IMAGE` and `GREEN_IMAGE` environment variables should point to built container images.
- The nginx template expects to be rendered by the container command configured in `docker-compose.yml`.

Ports & grader expectations
- Nginx public entrypoint (host): http://localhost:8080
- Blue service direct (host): http://localhost:8081
- Green service direct (host): http://localhost:8082

Manual toggle / Active pool
- The `ACTIVE_POOL` env var controls which backend is primary. By default `ACTIVE_POOL=blue`.
- To change active pool manually:

```bash
# edit .env and change ACTIVE_POOL to 'green' then reload nginx in the container
docker-compose up -d nginx
docker-compose exec nginx nginx -s reload
```

Chaos endpoints (supplied by the app images)
- POST /chaos/start?mode=error to induce failures on the target app
- POST /chaos/stop to stop chaos
- GET /healthz and GET /version to validate responses and headers (X-App-Pool, X-Release-Id)

Files of interest
- `docker-compose.yml` — docker compose for nginx + blue/green apps
- `nginx/` — nginx template and configuration
- `workflows/ci-cd.yml` — GitHub Actions deploy workflow

Improvements
- Add a registry-based CI (build & push images) and have the server pull images instead of building on the server.
- Add health-check endpoints on app containers and validate before switching `ACTIVE_POOL`.
