# Quickstart

```bash
cd services/proxy-gateway && go test ./internal/capacity/ -count=1 -timeout 120s
CAPACITY_FULL=1 go test ./internal/capacity/ -run TestFullProfiles -count=1 -timeout 3h
```
