# 运行手册：Endpoint Catalog 加载与变更

## 症状

- 进程启动立即退出，日志含 `CATALOG_LOAD_FAILED` 或 `CATALOG_VERSION_MISMATCH`。
- Gateway `/health/ready` 返回非 ready，而 `/health/live` 仍 alive。

## 判定

1. 确认 `shared/contracts/endpoint-catalog/v1/catalog.json` 存在且 JSON 合法。
2. 确认消费者 `TOKENMARKET_CATALOG_MAJOR`（缺省 `1`）等于文件中 `catalog_major`。
3. 确认完整性：每条记录含 stability、stateful、transport、metering_source、test_fixture_version。
4. 确认 `CATALOG.md` 可由同一 JSON 重新生成且无 diff。

## 处置

- 文件损坏：回滚到上一已发布 commit 的目录，不要手工补记录。
- 主版本不匹配：升级消费者或回滚目录，禁止改校验器放行。
- 需要新增端点：走评审 → schema 测试 → 生成清单 → 升 `catalog_minor`（语义不变）或 `catalog_major`（语义变）。

## 禁止

- 为了启动成功而跳过校验、缓存旧目录或把未知 path 当允许。
- 在日志中写入凭据或完整请求正文。
- 把 new-api 或 Volcano 路径并入本目录。
