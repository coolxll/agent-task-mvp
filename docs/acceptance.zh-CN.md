# MVP 验收记录（2026-09-25）

## 2026-09-26 当前补充

- Runner 已统一接入多个 Provider，并按节点上可执行的 CLI 报告 readiness；这个 readiness 只证明命令可发现和可启动，不保证认证、账号 entitlement 或服务端配额可用。Paseo 因结构化输出和会话生命周期尚未完成真实闭环，默认隐藏，仅可通过 `ENABLE_EXPERIMENTAL_PASEO=1` 在隔离环境启用。
- 代码评审、Gate 或 Agent 验收失败会触发最多两轮自动修复，每轮重新执行独立评审、全部 Gate 和验收；验证轮次保存在 Artifact 中。
- Runner watchdog 可恢复已经建立 worktree 且具有持久流水线状态的意外退出 Worker，最多自动恢复两次；无法证明安全的 provisioning 阶段退出会明确失败。集成测试包含真实 `SIGKILL` Worker 后续跑。
- 当前完整回归为 **48 项测试通过**，并通过 Python 编译检查、`node --check ui.js` 与 `git diff --check`。
- 隔离 Manager/Runner 使用真实 Codex 在 `coolxll/agent-task-mvp` 完成 [PR #17](https://github.com/coolxll/agent-task-mvp/pull/17) 的创建与系统内批准合并：审核 head `a4a5de1150ca05f6d2b8afb5a4c2114173341fcd`，目标 `main`，merge commit `506690980900df4723c45c76d688cdcf134dea16`；Run #2 最终为 `SUCCEEDED`、`delivery_status=merged`，worktree 已清理。branch protection 主动阻挡场景仍未实测，远端任务分支由验收后手工删除。详见 [GitHub 交付安全边界](github-delivery-security.zh-CN.md)。
- Antigravity CLI `1.2.10` 的真实结构化 plan 探针在消耗 token 前被服务端拒绝，原因为当前账号不具备 Antigravity 资格。该结果是外部账号 entitlement 阻塞，不是本项目代码失败，也说明 CLI readiness 不能代表端到端可用。

以下内容保留 2026-09-25 当时的验收过程和 Run 证据；其中“尚未实现”类表述应结合本节当前补充阅读。

## 本轮改动：全托管执行与交付验收

用户反馈的“审核”现已明确为两个不同动作：远端工作流内的 **Agent 代码评审** 检查实现质量；末端的 **用户交付验收** 决定是否接受成果。GitHub 交付时，用户验收通过才合并 PR；本地分支交付时，成果分支已回 Mac，验收通过后保留它。拒绝会关闭已有 PR 并清理远端工作区。网页导航及按钮使用“交付验收”措辞。

Runner 设为 `--agent-access full` 时，当前 Codex 驱动使用 Full access 并跳过工具权限提示。若 Agent 在最终消息中输出 `NEEDS_INPUT: <问题>`，Runner 保存问题、阶段和会话 ID，Run 进入 `NEEDS_INPUT`；用户在“执行流程”回答后，由驱动继续同一阶段，并跳过已完成阶段。等待状态下可取消。该机制处理 Agent 主动提出的任务问题；Codex 内部无法转成最终消息的交互弹窗仍不能由 Web 接管。

**Agent 边界验收：**`AgentDriver` 和注册表放在 `agent_drivers.py`。Manager 接受并校验 Task 的 `agent_kind`，Run 与任务包保存选择；Runner 在 `/health` 声明支持的 Agent 类型并按类型选择驱动；`pipeline.py` 不导入或调用 Codex CLI。Codex 的进程命令、会话 ID 提取、取消和结果读取只在 `CodexDriver`。UI 显示真实 Run 的 Agent 类型。部署后现场检查：Manager `/api/agents` 返回 `["codex"]`；`corp172-dev` Runner `/health` 返回 `agent_kinds: ["codex"]`；旧 Run #11 仍为 `REVIEW` 且结果交付 `ready`。目前注册表仅有 `codex`，未声称已支持第二种 Agent。

**开源组件复用：**计划、代码评审、验收输出改为 Pydantic 模型生成 JSON Schema 并进行严格校验，替换了自写的递归 JSON 校验器；`requirements.txt` 固定版本。Git、SQLite、Codex CLI 继续承担仓库、存储、编码 Agent 的现成功能。Herdr / Paseo 的实际运行能力和取舍见[运行管理评估](runtime-manager-evaluation.md)；Paseo CLI 当前的后台任务只稳定返回状态，结果正文仍需从面向人的日志中提取，因此未把验收所需的结构化结果改接到它。平台本体 Planner 的 PydanticAI / Google ADK 选择见[专项决策](native-agent-framework.zh-CN.md)。

Mac 和 `corp172-dev` 已切到项目 `.venv` 启动，远端检查 `pydantic.__version__ == 2.13.5`、`pipeline.Plan` 可生成 Schema、Runner `/health` 正常；现有 Run #11 的持久结果仍可读取。新的 Pydantic 校验路径通过 12 项本地集成测试。尚未用真实远端 Codex 新建 Run 验证模型对 Pydantic 生成 Schema 的输出遵循情况。

**本地集成验收：**`test_02a_agent_question_answer_resumes_same_run` 通过 Manager API 提交任务、等待提问、回答、续跑、交付和拒绝清理；同时验证已回答的问题不会被后续实现阶段重复提问。`test_02b_waiting_question_can_be_cancelled` 验证等待回答时能取消并清理 worktree。`test_03a_only_registered_agent_kinds_are_accepted` 验证仅接受已注册类型。总计 **12 项测试通过**；`py_compile` 和 `node --check` 通过。

**真实远端验收：**Task #10 / Run #11 在 `corp172-dev` 的隔离 worktree 运行真实 Codex。规划阶段提出“docstring 应该使用中文还是英文？”，Runner 保存 `NEEDS_INPUT`、问题和会话 ID；通过 Manager API 回答“英文”后，原规划会话续跑，进入实现阶段。这个 Run 在补充跨阶段回答上下文的修复过程中启动，所以实现阶段又重复问了一次；回答后继续完成实现、代码评审、Gate 和验收检查，结果 bundle 回传 Mac，`delivery_status=ready`。修复后的集成测试已验证后续阶段不再重复提问；真实远端对该修复的完整新 Run 尚未重新验证。

Run #11 **不能批准**：仓库原始提交没有 `tests` 目录，配置的 unittest Gate 退出码为 1；Codex 添加的 docstring 还把实际执行减法的函数误写为“返回和”。独立代码评审与验收报告均为 `passed=false`，`ready_to_merge=false`，UI 禁止验收通过。该 Run 留在交付验收页保留失败证据，尚未作拒绝清理。在这次验收时，工作流还不会把评审或 Gate 失败自动送回 Agent 返工；该能力现已按本页 2026-09-26 补充实现。

本记录对照[实施计划](implementation-plan.zh-CN.md)和[目标 MVP](target-mvp.zh-CN.md)，区分真实远端执行、本地集成验证与尚待真实 GitHub 仓库验收的环节。运行数据保存在 Mac 的 `manager.sqlite3` / `manager.sqlite3.data/` 和 `corp172-dev` 的 `/workspace/agent-task-mvp/data/`。Web 地址：<http://127.0.0.1:18765/zh>。

## 已交付能力与验收点

| 验收点 | 操作 / 检查 | 实际结果 |
| --- | --- | --- |
| 选本机目录 | 任务页“选择文件夹…”定位干净的 Git 仓库 | Chrome UI 实测能浏览文件夹、导入 Project；输入区只有项目、节点和一段需求 |
| 固化输入 | 创建 Task，读取 `/api/runs/<id>/package` | 版本化 JSON 任务包含需求、源提交、bundle 摘要、节点、阶段、Gate 和交付方式；Mac/Runner 各保存一份 |
| 不丢本机改动 | 在目录添加未提交文件后提交任务 | 明确报错，文件保持原样；集成测试通过 |
| 远端准备 | Runner 接收 bundle、核对 SHA-256、建立托管克隆和独立 worktree | Run #10 从 Mac 试验仓库传输成功；远端 worktree 建立成功 |
| Agent 拆解 | Planner 读仓库并返回结构化步骤 | Run #10 生成两个有依赖的步骤：修复加法、补测试；系统校验步骤引用和依赖无环 |
| 实现与独立评审 | 查看 Run #10 的阶段和结果 | 两个实现步骤完成；独立 Code Review 报告 `passed=true`、无阻断问题 |
| 测试与验收 | 查看 Run #10 的 Gate 和验收报告 | `python3 -m unittest discover -s tests -v`：3 项通过、退出码 0；验收报告逐项给出证据，`ready_to_merge=true` |
| 成果回 Mac | 查看 Run #10 的 `delivery_status` 和 `delivery_repo` | `ready`；Mac 导入结果 bundle 并验证结果提交 SHA 与远端一致，原本机工作目录 HEAD 未改变 |
| Gate 拦截 | 用失败的 Gate 跑集成场景 | 结果仍可 Review，Approve 被拒绝；Reject 清理受管 worktree |
| 取消和清理 | Agent 运行时调用 Cancel 后 Cleanup | Agent 进程被终止，worker 停止后只移除系统创建的 worktree/分支；集成测试通过 |
| PR 推送、创建与合并控制 | 本地 Git bare remote 配合模拟 `gh` 响应 | 实际 Git 推送了同一结果提交；创建 PR 命令执行，合并携带已审查的 SHA；PR head 改变时拒绝合并 |

真实远端样例：Project #5（`acceptance-source`）、Task #9、Run #10。Run #10 的 base commit 为 `d05b92c`，结果 commit 为 `a4292b4c9d8a925d12f7c053000792d7d6d0e7d0`，变更 `calculator.py` 与 `tests/test_calculator.py`。Run 保持 **REVIEW**，可直接在网页“审核”中查看计划、评审、测试和 diff。该 Project 配置为“取回 Mac 并保留分支”，因此此样例不会产生 GitHub PR。

Run #9 曾因远端 Codex 供应端没有按 `--output-schema` 返回 JSON 而在 PLANNING 阶段失败。已补充显式 JSON 输出约束与本地结构校验；Run #10 使用同一源项目和需求完成全流程。失败记录仍可在数据库中追溯。

## 验收操作

1. 打开 <http://127.0.0.1:18765/zh>，在“交付验收”点击 Run #10“查看结果”。应看到两个步骤、评审通过、3 项 unittest 通过、验收证据，以及 Mac 上的结果仓库路径。
2. 要自行提交新任务，在“任务”点击“选择文件夹…”，选择一个已提交的 Git 仓库，选择 `corp172-dev`，输入一段需求。也可选择已有 Project。
3. 在“执行流程”观察阶段。`NEEDS_INPUT` 时打开 Run 回答问题继续；`FAILED` 应包含具体错误；`REVIEW` 应可查看完整结果。Code Review、Gate 或验收任何一项失败时，系统最多自动修复两轮并完整复验；仍失败时 Approve 不可用，结果可 Reject 或检查后新建 Run。
4. 若要验收 GitHub PR：选择你有写权限的 GitHub 项目，检查“配置”中的交付方式为 GitHub、目标分支正确；任务通过检查后确认出现 PR 链接；网页 Approve 后 PR 状态应为 `MERGED`，远端临时 worktree 应被清理。真实主路径已由 PR #17 验证；branch protection 主动拒绝路径仍需在配置了相应规则的仓库单独验收。

## 验证命令和结果

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m py_compile app.py agent_drivers.py control.py pipeline.py git_io.py native_planner.py acp_bridge.py herdr_bridge.py
node --check ui.js
```

集成测试：**12 项通过**，涵盖 Agent 类型校验、任务包与 bundle、完整流程、提问后续跑、等待提问时取消、Gate 阻断、清理、PR 推送与模拟创建、合并时校验提交。另有 corp172-dev 真实 Codex Run #10，通过全部远端阶段并把成果导回 Mac；Run #11 验证真实远端提问与续跑，并由自动检查发现错误。中文网页的目录选择器已在 Chrome 中操作检查。

## 已知边界

- 一个任务选择一台执行机器；Planner 可在该机器拆成最多 8 个步骤。跨机器依赖执行和交接尚未实现。
- GitHub PR 的推送、创建、head/base 复核、合并和 Runner 清理主路径已由 PR #17 真实验证；branch protection / required checks 主动阻挡路径仍需对具体项目验收。
- 当前本机目录必须是干净 Git 仓库；Git bundle 限 48 MiB。非 Git 文件夹和未提交改动的快照传递未实现。
- Runner worker 已支持有界自动恢复，但 provisioning 阶段无法证明安全的退出会失败，恢复也不替代操作系统级隔离。`corp172-dev` 的 Codex 以 `danger-full-access` 运行，Git worktree 只提供代码目录隔离。
