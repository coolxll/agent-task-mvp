# 目标 MVP：从一段需求到合并 PR

本文记录产品目标；[中文 README](../README.zh-CN.md) 描述当前代码已实现的操作。两者不能混为一谈。

## 用户入口

首次使用可预先配置 Project、Node、Workspace、Agent 和 Gate。平时创建任务只需要：

1. 选择本机工作目录（一个 Git 项目文件夹；系统识别 Project、remote 和当前 ref）。
2. 在一个大文本框里写需求，包括约束和期望结果。
3. 选择一台启动任务的机器，然后提交。

Project、Task、Node、Run、Workspace、Artifact 等实体继续保留。项目和节点配置属于可复用的环境信息，不要求用户每次重新填写。若工作目录没有可供远端获取的 Git remote，或含未提交改动，提交前必须明确显示如何传递代码；不能假装远端已有同一份工作树。

## 执行流程

```text
本机 Git 目录 + 一段需求 + 启动 Node
  → Manager 固化任务包并持久化
  → Runner 准备远端仓库和隔离 worktree
  → Planner Agent 调查仓库，生成步骤、依赖和验收条件
  → Implement Agent 执行一个或多个步骤
  → Code Review（独立检查产出）
  → 测试 / Gate
  → 创建 PR
  → 验收（展示计划、日志、Review、测试、diff 和 PR，允许退回）
  → 验收通过后合并 PR
  → 清理系统创建的临时 Workspace
```

任务包可以用 JSON 或 YAML 表示，但格式本身不是功能目标。它至少要固定：任务 ID、原始需求、仓库地址及基准提交、启动 Node、可用 Gate 和交付方式。密钥只通过安全配置传递，不写进任务包。计划、步骤、Run、日志和产出都要持久化。

Planner 调查仓库并拆解步骤。Runner 校验计划依赖后依序执行；跨节点版本需要 Manager 查询更多节点并派发。远端运行规划与编码，并负责把结果回传；最终 PR 合并由 Manager 在验收通过后触发，避免某个 Runner 自行决定是否合并。

第一轮可以让 Planner 在复杂任务上生成多个步骤，但跨机器步骤必须有明确的代码交接：前一步推送的分支、提交或 PR 能被下一台机器取得。没有交接机制时，有代码依赖的步骤不能分到不同机器。

## 实现状态

| 环节 | 当前状态 |
| --- | --- |
| 简化输入 | 已实现：本机 Git 目录、机器、大需求框；预配置 Project/Node/Workspace 继续保留 |
| 任务包 | 已实现：版本化 JSON、提交 SHA、Git bundle 摘要，Manager/Runner 持久化 |
| 规划与开发 | 已实现：远端 Codex Planner 生成 1–8 个步骤，在选定节点按依赖执行 |
| 独立评审、测试与验收 | 已实现：独立 Codex 会话与普通代码 Gate；报告和 diff 回传 Web |
| 成果回 Mac | 已实现：验证提交并导入 Mac 的结果仓库 |
| GitHub PR | 已实现代码和本地集成验证；仍需一个有写权限的真实 GitHub 项目做外部验收 |
| 跨机器步骤 | 尚未实现；当前每个 Task 在选定的一台机器上执行全部步骤 |

实际操作和证据见[中文 README](../README.zh-CN.md)与[验收记录](acceptance.zh-CN.md)。

## 已确定的产品语义

- 本机目录包含未提交改动时，先明确报错，用户提交后再运行；系统不修改用户主工作区。
- PR 第一版只支持 github.com；其余仓库可将结果分支取回 Mac。
- 用户在 Web 审核通过后，Manager 才合并 PR。远端 Agent 无合并权限。
