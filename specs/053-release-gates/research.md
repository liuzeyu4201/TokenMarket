# Phase 0 Research

## Decision 1：两种结论

`implementation_complete` 与 `public_launch` 分开。后者在渗透/真实冒烟/生产证据缺失时恒为 no-go。

## Decision 2：PATCH 不变量

Project 允许重命名 PATCH，但请求 schema 不得含 mode；这与「模式创建后不可变」一致，禁止用「无 PATCH 动词」误杀 SF13。

## Decision 3：CI 三次

同一候选 commit 连续三次 `make ci`；结果写入 evidence，不得只保留最后一次绿色。
