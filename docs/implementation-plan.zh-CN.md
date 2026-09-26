# MVP 差距与实施计划

目标：选择本机 Git 目录、选择机器、输入一段需求，系统在远端完成规划、实现、独立评审、测试及验收报告；Manager 取回成果、创建 PR，用户验收后合并。

| 顺序 | 差距 | 实施内容 | 状态 / 验证 |
| --- | --- | --- | --- |
| 1 | 提交表单字段多，缺少本机目录入口 | 目录浏览与导入，自动识别项目；目录、机器、大需求框 | 已实现；中文界面目录选择器实测 |
| 2 | Run 参数没有完整可追溯输入 | 版本化 JSON 任务包、精确 Git 提交、Git bundle 传输与摘要校验 | 已实现；Run #10 和集成测试通过 |
| 3 | 单次 Codex 直接写代码 | Planner Agent 输出有依赖的步骤，依序实现，独立 Agent 评审和验收，普通代码执行 Gate | 已实现；corp172-dev Run #10 通过 |
| 4 | 只有最终日志与 diff | 展示任务包、当前阶段、计划、评审、测试与验收报告 | 已实现；Chrome 查看 Run #10 结果 |
| 5 | 成果停留在远端 | 成果 bundle 自动回 Mac；GitHub PR 创建；Web 验收后合并；拒绝关闭 PR | Git bundle 实测；真实 GitHub PR #17 已通过系统创建、校验、批准合并和清理，branch protection 阻挡路径待验收 |
| 6 | 文档与产品目标不一致 | 更新中英使用说明、配置要求、限制与验证记录 | 已更新中英文 README 和逐项验收记录 |

## 本轮取舍

- 一个选定 Node 执行完整流水线；Planner 会拆解有依赖的多个步骤，跨机器依赖调度后续加入。
- Planner、Implement、Code Review、Acceptance 只依赖 AgentProvider / AgentDriver；当前统一适配 Antigravity、Pi、Codex、Claude、Herdr、ACP 和实验性 Paseo。Runner readiness 只表示对应 CLI 命令可用，不保证登录态、账号 entitlement 或服务端配额；Paseo 默认隐藏。Run 和任务包持久保存 agent_kind，Runner 按类型创建驱动。每个阶段独立会话；同一阶段遇到 Agent 主动提问时保存会话 ID，回答后续跑，并把回答传给后续阶段。
- 保留 Project、Task、Node、Run、Workspace、Artifact；流水线阶段与步骤保存在 Run 的持久化结果中。
- 本机目录提交固定到已提交 HEAD；有未提交改动时明确拒绝，避免静默遗漏或改动用户主工作区。
- GitHub 写操作在 Manager 上通过 gh 和 Git 完成，遵守 Mac Gatekeeper 的仓库规则。远端不持有推送凭据。
- 只有 Gate、独立评审、Agent 验收均通过才允许最终 Approve。用户通过后合并 PR；失败保留产出供检查。
- 检查失败时最多自动修复两轮并完整复验；Worker 意外退出时仅对已安全准备且有持久状态的 Run 最多恢复两次。
- 无 GitHub remote 的试验项目可使用“保留分支”交付方式，不伪装成已合并 PR。
