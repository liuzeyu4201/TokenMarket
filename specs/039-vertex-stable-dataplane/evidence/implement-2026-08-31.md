# Implementation evidence: 039-vertex-stable-dataplane

**Date**: 2026-08-31

`TestVertexStableCatalogContractTable` covers all embedded vertex stable records (29/29).

generateContent preserves buyer project/location in the upstream path and extra JSON fields. predictLongRunning `name` registers operation affinity. Shared batch jobs return `DEDICATED_PROJECT_REQUIRED`. IAM control-plane is blocked with a platform envelope, not `google.rpc.Status`. v1beta1 generate requires opt-in.
