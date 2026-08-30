# Evidence 045

Gateway: `go test -race ./internal/domain/passthrough/` ok, coverage 89.1%. Dedicated unhealthy never hits shared; atomic replace mixes credentials 0; draining SelectConnection keeps old secret.

API: `pytest tests/unit/test_binding_lifecycle.py tests/unit/test_binding_http.py` 18 passed. `app.domain.bindings` + HTTP 87% line coverage. Exclusive connection PUBLISH_CONFLICT; unconfirmed replace 409; confirmed replace drains old and audits actor/reason/before/after.

Frontend: ProjectDetail dedicated panel lists non-migrating resources; vitest 2 passed.
