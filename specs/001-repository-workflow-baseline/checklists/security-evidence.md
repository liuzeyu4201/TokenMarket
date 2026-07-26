# 安全证据

**功能**：`specs/001-repository-workflow-baseline/`
**日期**：2026-07-14

## 密钥扫描

```bash
gitleaks detect -s .
```

- 结果：**PASSED**（退出码 0）
- 扫描了 4 次提交，约 1.90 MB。
- 未发现泄漏。
- 合成正向夹具在专用 US2 测试
  （`tests/workflow/test_secret_scan.py`）中被检测到，其值在输出中已脱敏。

## 依赖扫描

### Go

```bash
govulncheck -C services/proxy-gateway ./...
```

- 结果：**PASSED**（退出码 0）
- 在被调用代码中未发现漏洞。

### Python

```bash
uv export --project services/api-service --no-hashes > /tmp/api-reqs.txt
uv run --project tools/workflow pip-audit -r /tmp/api-reqs.txt --disable-pip --no-deps
```

- 结果：**FAILED**（退出码 1）
- `starlette 0.45.3` 中的已知漏洞：
  - PYSEC-2026-161 → fix 1.0.1
  - PYSEC-2026-249 → fix 1.3.1
  - PYSEC-2026-248 → fix 1.3.0
  - PYSEC-2026-1942 → fix 0.49.1
  - PYSEC-2026-1941 → fix 0.47.2
  - PYSEC-2026-2281 → fix 1.1.0
  - PYSEC-2026-2280 → fix 1.1.0
- 该发现会阻塞 `make security-check` 以及因此阻塞 `make ci`，直到
  经评审的依赖更新或已批准的、带过期时间的例外被记录。

### npm

```bash
npm audit --audit-level=moderate
```

- 结果：**PASSED**（退出码 0）
- 发现 0 个漏洞。

## 镜像扫描

```bash
make image-scan
```

- 结果：**FAILED**（退出码 2）
- 原因：本地工作站未安装 Trivy 0.61.0。
- CLI 返回 `TOOL_MISSING` 并 fail-closed，而非跳过扫描。

## 摘要

| 扫描器 | 结果 | 说明 |
|---------|--------|-------|
| gitleaks | PASSED | 无泄漏 |
| govulncheck | PASSED | 无被调用漏洞 |
| pip-audit | FAILED | starlette 0.45.3 已知发现 |
| npm audit | PASSED | 无发现 |
| trivy image | FAILED | 本地未安装工具 |

由于镜像扫描未能运行，不存在未批准的 HIGH/CRITICAL 镜像发现。
唯一已认可的阻塞是已文档化的 `starlette` 依赖发现，
在合并前必须修复或获得正式例外。
