# 平台本体 Agent 的框架选择

本文中的“本体 Agent”指 Manager 侧负责理解需求、查 Project / Node、拆解并安排 Run 的 Planner / Coordinator；远端 Coding Agent 仍由 `AgentDriver` 调用。把用户说的“pandemic”暂按 **PydanticAI** 理解。

## 结论

**本地主 Planner 已接入 PydanticAI，保持显式选择。** 默认运行路径仍使用远端 Coding Agent 做规划；Mac 尚无可供本地主 Planner 调用的模型 API 凭据，Codex CLI 登录态不能直接视为模型 SDK 凭据。模型真实端到端验收尚待配置模型服务后进行，见[验收记录](manager-planner-acceptance.zh-CN.md)。

环境前提：当前 Mac Manager 的系统 Python 为 3.9；2026-09-25 从 PyPI 包元数据核对，`pydantic-ai` 与 `google-adk` 最新版本均要求 Python ≥3.10。实现本体 Planner 前需要把 Manager 运行环境升级到受支持的 Python，并配置可用的模型 API 或模型服务。

选择 PydanticAI 的理由是下一步需求很窄：输入 Task、Project、可用 Node，调用少量只读工具，输出可验证的 `ExecutionPlan`。它原生支持 Pydantic `output_type`、工具、依赖注入、消息历史和事件流；已有的 Pydantic 输出模型可以复用。Manager 保存 Plan 和 Run 状态，Git worktree、Gate、PR、交付验收仍由确定性代码执行。

| 候选 | 已核对的能力 | 当前取舍 |
| --- | --- | --- |
| PydanticAI | 类型化输出、工具和依赖注入、消息历史、事件流；持久执行可接 Temporal / DBOS / Prefect 等 | 适合先实现一个能查项目与节点、输出计划的本体 Planner。持久执行不是装上框架就自动获得，MVP 仍以现有数据库记录 Run 状态。 |
| Google ADK | Agent、SessionService、MemoryService、顺序/并行/循环与图工作流，提供恢复机制 | 更适合多个本体 Agent 共同协调、动态分支与共享会话成为真实需求时。现在引入会和现有 Manager 状态机、Run 持久化职责重叠。 |
| 远端 Codex CLI（现状） | 已登录、能读仓库并输出计划，Run #10/#11 已实测 | 继续作为可用的规划路径，直到本体 Planner 有模型连接并通过同一验收案例。 |

## 本体 Planner 的接入边界

建议接口是 `plan(task, project, available_nodes) -> ExecutionPlan`。工具只暴露必要的只读信息，例如查询 Project、Node 能力和历史 Run。输出计划须经模型校验及普通代码的依赖无环、Node 存在、Gate 有效校验，再由 Manager 持久化；Runner 只执行分配给它的 Run。不要让框架直接拥有 Project/Run 数据库、Git 工作区清理或 PR 合并权限。

当实际任务要求 Planner 反复调查、跨机器交接或协调多个本体 Agent 时，先基于任务样例验证 PydanticAI 的工具循环是否足够；若出现明确的多 Agent 工作流管理需求，再评估 ADK。不要为了可能出现的复杂性提前把整条确定性执行链搬进 Agent 框架。

## 验收条件

1. 在同一组 Task / Project / Node 输入下，Planner 输出合法、可执行的结构化计划。
2. 非法 Node、循环依赖、空 Gate 被拒绝，且错误可见。
3. Manager 能保存计划和模型错误；Runner 无需知道 Planner 使用哪个框架。
4. 真实模型连接可用后，与当前 Codex Planner 跑同一个隔离样例，比较计划质量、耗时和失败信息，再切换默认路径。

## 核对来源

2026-09-25 直接 fetch 官方页面全文后核对（`read_url` 的摘要未作为完整依据）：

- [PydanticAI Agents](https://pydantic.dev/docs/ai/core-concepts/agent/) 与 [Output](https://pydantic.dev/docs/ai/core-concepts/output/)
- [PydanticAI Durable Execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/)：明确区分持久执行和会话存储
- [Google ADK Agents](https://adk.dev/agents/)、[Workflows](https://adk.dev/workflows/)、[Sessions](https://adk.dev/sessions/) 与 [Resume](https://adk.dev/runtime/resume/)
