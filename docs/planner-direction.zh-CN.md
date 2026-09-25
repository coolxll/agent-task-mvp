# Planner 当前实现与后续方向

当前 Planner 是在所选远端 Node 上运行的独立 Codex `exec` 会话。它先读取仓库，再输出结构化计划；每个计划有 1–8 个步骤、步骤 ID、标题、实现说明和依赖，还有验收条件与建议 Gate。Runner 校验 ID 唯一、依赖存在且无环，然后按顺序启动每一步的实现会话。项目预配置的 Gate 优先于 Agent 建议。计划与各阶段结果随 Run 持久化并显示在审核界面。真实样例见[验收记录](acceptance.zh-CN.md)。

本轮每个 Task 只选择一台 Node，所有步骤在同一个 Git worktree 中顺序执行。进一步做跨机器复杂任务时，需要 Manager 查询节点能力并让 Planner 提出各步骤 Node；前一步成果必须先形成可被下一台机器获取的提交或分支，才能解锁依赖。届时每一步可以对应独立 Run，并在 UI 中编辑或批准整份计划。这个能力目前尚未实现。

平台本体 Planner 的下一步框架选择与依据见[专项决策](native-agent-framework.zh-CN.md)：优先 PydanticAI 来实现类型化计划与少量只读工具；当前继续复用已登录的远端 Codex 规划路径。Google ADK 保留为需要多本体 Agent 工作流时的备选。框架切换前要有可用模型连接，并用同一隔离任务验收计划质量和失败处理。

官方资料：[SDK 概览](https://www.antigravity.google/docs/sdk/overview)、[工具与权限](https://www.antigravity.google/docs/sdk/tools/)、[结构化输出](https://www.antigravity.google/docs/sdk/structured-output/)。
