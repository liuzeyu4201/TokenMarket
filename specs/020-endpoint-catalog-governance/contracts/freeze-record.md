# 目录冻结记录

- **Freeze date**: 2026-08-31
- **catalog_major**: 1
- **catalog_minor**: 0
- **Providers**: openai, anthropic, vertex
- **范围**: 厂商公开稳定模型数据面；控制面显式登记为 `control_plane`；preview/beta 显式登记且默认拒绝。
- **来源**:
  - OpenAI API Reference（Responses、Chat Completions、Files、Realtime 等）
  - Anthropic API Overview（Messages、Batches、Models、count_tokens）
  - Vertex AI Publisher Models REST（generateContent 及同资源预测/缓存/批/调优）
- **评审**: V0.2_0831 SF01；含糊接口不进入 `stable`。
- **兼容影响**: 新主版本事实源；V0.1 volcano 契约不受影响。
- **测试夹具版本**: `fx-v0.2.0`
- **负责 SF**: 目录治理 SF01；厂商全量协议差分 SF19/SF20/SF21。
