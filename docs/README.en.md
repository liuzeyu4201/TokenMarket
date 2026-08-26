[中文](README.md) | **English**

# Documentation hub

This directory is the **catalog** for repository documentation, not the store of every source document. Product research, PRDs, specs, contracts, and runbooks stay on their canonical paths. The hub classifies them, adds bilingual entry points, and fills gaps.

Language rules: [Language](#language).

## Classification

| Kind | Canonical path | Hub | Language |
|------|----------------|-----|----------|
| Repository landing | [`README.md`](../README.md) | — | Chinese + [`README.en.md`](../README.en.md) |
| Local quick start | [`QUICKSTART.md`](../QUICKSTART.md) | — | Chinese + [`QUICKSTART.en.md`](../QUICKSTART.en.md) |
| Contributing / branches | [`CONTRIBUTING.md`](../CONTRIBUTING.md) | — | Chinese + [`CONTRIBUTING.en.md`](../CONTRIBUTING.en.md) |
| Security disclosure | [`SECURITY.md`](../SECURITY.md) | — | Bilingual single file (GitHub-reserved name) |
| License | [`LICENSE`](../LICENSE) | — | Bilingual single file |
| Architecture | [`项目开发/1-项目架构与目录结构.md`](../项目开发/1-项目架构与目录结构.md) | [`architecture/`](architecture/README.en.md) | Hub bilingual; source Chinese |
| HTTP / event contracts | [`shared/contracts/`](../shared/contracts/README.md) | [`api/`](api/README.en.md) | English identifiers; bilingual guides |
| Product and research | [`产品调研/`](../产品调研/README.md), [`项目开发/`](../项目开发/README.md) | [`product/`](product/README.en.md) | Sources Chinese; hub bilingual |
| Architecture decisions | [`docs/decisions/`](decisions/README.en.md) | this tree | Index bilingual; historical ADRs keep original language |
| Feature specs | [`specs/`](../specs/), [`项目开发/V0.1/V0.1_0712/specs/`](../项目开发/V0.1/V0.1_0712/specs/README.md) | [`product/`](product/README.en.md) | Chinese |
| Runbooks | [`ops/runbooks/`](../ops/runbooks/README.md) | — | Chinese |
| Constitution | [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) | — | English (historical authority; not bulk-translated here) |

## By reader

| You want to… | Open |
|--------------|------|
| Run the local environment | [`QUICKSTART.en.md`](../QUICKSTART.en.md) |
| Understand service boundaries | [`architecture/README.en.md`](architecture/README.en.md) |
| Look up an HTTP API | [`api/README.en.md`](api/README.en.md) → `shared/contracts/` |
| Read PRD / roadmap / research | [`product/README.en.md`](product/README.en.md) |
| See why a design exists | [`decisions/README.en.md`](decisions/README.en.md) |
| Recover, migrate, or deploy | [`ops/runbooks/README.md`](../ops/runbooks/README.md) |
| Implement a V0.1 feature | the matching `NNN-…` directory under [`specs/`](../specs/) |

## Language

| Document type | Rule |
|---------------|------|
| Landing, quick start, contributing, this hub | Simplified Chinese is the default filename; English sibling is `*.en.md` |
| Newly written or substantially revised engineering prose | Simplified Chinese (constitution Principle VIII) |
| Identifiers, API fields, commands, paths, environment variables | Keep original form; do not translate |
| OpenAPI / JSON Schema / workflow contracts | English identifiers; explanatory text may be Chinese |
| Existing English ADRs, constitution, component READMEs | Keep as-is; do not bulk-translate. New passages use Chinese, or add a `*.en.md` index |

Do not relocate `产品调研/`, `项目开发/`, `specs/`, or `shared/contracts/` into `docs/`. Those moves would break canonical paths in specs, tests, and the constitution.

## Tree

```text
docs/
├── README.md / README.en.md     # this hub
├── architecture/                # architecture index and V0.1 current diagram
├── api/                         # public API navigation → shared/contracts
├── product/                     # product / research / spec navigation
└── decisions/                   # ADRs (path fixed by tests)
```
