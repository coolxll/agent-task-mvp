# Manager 本地主 Agent 验收（2026-09-25）

## 使用方式

Manager 使用 Python 3.10–3.14 的环境安装 `requirements.txt`。Mac 已在 Pi 中配置 `workbuddy-dffl` 提供方及 `deepseek-v4.1-flash` 模型；启动 Manager 时设置 `MANAGER_PLANNER_MODEL=pi:workbuddy-dffl/deepseek-v4.1-flash`，再于创建任务时将“规划位置”设为“在 Manager 本地规划”。Manager 从 `~/.pi/agent/models.json` 和 `auth.json` 读取接口和密钥，密钥不写入项目配置。默认仍是在所选远端机器规划。

本地主 Agent 使用 PydanticAI 的 `Agent(output_type=Plan)`。导入的本地 Project 可通过只读工具列出 Git 已跟踪文件、读取 HEAD 中的文件；远端手工 Project 目前仅提供项目元数据。生成的计划会校验步骤 ID、依赖无环、Gate 非空，写入任务包，再交给 Runner 执行。Runner 的实现、Agent 代码评审、Gate、验收和交付决策仍按原有确定性流程运行。

## 验收证据

| 情况 | 已验证结果 |
| --- | --- |
| PydanticAI 类型化输出 | FunctionModel 产生的合法 `Plan` 被解析；Agent 注册了仓库只读工具 |
| 业务校验 | TestModel 给出的循环依赖被拒绝 |
| 缺少模型配置 | `/api/submit` 返回 `FAILED` Run；错误和 Task 状态保存在 SQLite，可在运行列表查看 |
| 计划交接 | 模拟 PydanticAI 输出经 Manager 任务包送达 Runner；Runner 跳过远端规划并完成 Review，规划阶段标记 `source=manager` |
| 原有路径 | 未选择本地规划时继续使用远端 Planner；全部回归测试通过 |
| 真实模型 | Pi 配置的 DeepSeek Flash 返回合法结构化计划；本地隔离 Git fixture 可用 |
| 远端完整闭环 | 隔离 Mac Manager 调用本地 Planner 生成 5 步计划，`corp172-dev` ACP Runner 完成实现、Agent 评审、Gate、diff 与 bundle 回传，Run 进入 `REVIEW`；测试 Run 的 Reject 清理成功 |

真实闭环在本地隔离仓库执行，成果为 `calc.py` 与 `test_calc.py` 的 diff；远端测试目录是 `/workspace/agent-task-mvp/acp-test-data-3/`。该验证没有对真实 GitHub 仓库创建或合并 PR。本地主规划仍需用户显式选择；默认路径是否切换需要结合实际任务的计划质量和耗时继续观察。
