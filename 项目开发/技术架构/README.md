# 技术架构宣讲材料

本目录是**工程架构宣讲原文**，不搬进 `docs/`。枢纽入口：[docs/architecture/README.md](../../docs/architecture/README.md)。

数字以仓库现码为准。目标能力（Kafka、扣费、Escrow、加权路由、三端业务页）单独标注，不画进现状部署图。

| 文件 | 用途 |
|------|------|
| [TokenMarket_技术架构.pdf](TokenMarket_技术架构.pdf) | 详细说明（全模块、时序、HTTP 全表、Alembic、张力） |
| [TokenMarket_技术架构.pptx](TokenMarket_技术架构.pptx) | 约 2 小时分享（44 页；流程图讲关键机制） |
| [TokenMarket_技术架构.html](TokenMarket_技术架构.html) | 同内容交互稿（← → 翻页，全屏演示） |
| [scripts/build_pdf.py](scripts/build_pdf.py) | PDF 再生脚本 |

## 分享时间盒

| 时段 | 内容 |
|------|------|
| 00–15 | 全景、所有权、SF 地图 |
| 15–30 | 契约、Make、ADR、健康探针 |
| 30–55 | 身份：注册、OTP、Cookie、授权 |
| 55–80 | 卖家 Key 与买家代理 Key |
| 80–110 | 网关主链路工作原理 |
| 110–120 | 观测、交付、张力、Q&A |

配套现状图：[docs/architecture/overview.md](../../docs/architecture/overview.md)。目标图：[1-项目架构与目录结构.md](../1-项目架构与目录结构.md)。
