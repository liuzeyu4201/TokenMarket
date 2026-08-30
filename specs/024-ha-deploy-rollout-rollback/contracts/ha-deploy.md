# HA deploy contract

- `compose.app.yml` services use `image:` only.
- healthcheck + stop_grace_period required.
- `make deploy-down` retains named volumes.
- mode=test|prod explicit.
