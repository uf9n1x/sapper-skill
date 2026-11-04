# kb/ — 离线知识库（KB）

带元数据的本地 Markdown 知识库（ADR-0010）。与 techniques（"如何思考某领域"）
分工：**KB 负责"某产品/版本/问题的可复用解法"**，两者不重复维护同一内容。

## 条目格式

文件名必须以 `kb-` 开头（如 `kb-example-httpd-admin-20260101.md`），
frontmatter 必填字段：

```yaml
---
title: 条目标题
source: 来源说明（官方公告 / 论坛帖子 / 演练 finding 等）
trust: official | community | unverified
applies_to: 适用产品/版本（如 example-httpd 2.4）
last_verified: YYYY-MM-DD（最后验证日期）
---
```

## 纪律（机器校验 + 流程约束）

- **信任级别**：`official`（官方来源）/ `community`（社区共识）/
  `unverified`（未验证线索）。不存在的 trust 值会被 `kb-list` 拒绝。
- **过期警告**：`last_verified` 距今超过 180 天，`kb-list`/`kb-read`
  强制显示 `EXPIRED`——使用前必须复核。
- **晋升门禁**（`prism.py kb-promote`）：
  - 只有 latest verdict = **confirmed** 的假设才能晋升；
  - 晋升文本经过**去目标化硬校验**——含案件内任何原始目标串
    （IP/域名/主机名）直接拒绝；
  - 新条目固定 `trust: unverified`，信任由后续验证提升，不虚标；
  - 原始目标输出不得自动污染 KB。

## 维护

- 条目更新结论后必须更新 `last_verified`。
- 冲突条目：保留双方并互相引用，由使用者按 trust 与验证时间判断。
