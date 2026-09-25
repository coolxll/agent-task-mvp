# Manager 本地主 Agent 验收（2026-09-25）

## 使用方式

Manager 使用 Python 3.10–3.14 的环境安装 `requirements.txt`。配置可用的模型服务与凭据，并设置 `MANAGER_PLANNER_MODEL`（例如 `openai:<模型名>`，具体名称取决于模型服务）。创建任务时将“规划位置”设为“在 Manager 本地规划”。默认仍是在所选远端机器规划；无需模型 API 凭据。

本地主 Agent 使用 PydanticAI 的 `Agent(output_type=Plan)`。导入的本地 Project 可通过只读工具列出 Git 已跟踪文件、读取 HEAD 中的文件；远端手工 Project 目前仅提供项目元数据。生成的计划会校验步骤 ID、依赖无环、Gate 非空，写入任务包，再交给 Runner 执行。Runner 的实现、Agent 代码评审、Gate、验收和交付决策仍按原有确定性流程运行。

## 验收证据

| 情况 | 已验证结果 |
| --- | --- |
| PydanticAI 类型化输出 | FunctionModel 产生的合法 `Plan` 被解析；Agent 注册了仓库只读工具 |
| 业务校验 | TestModel 给出的循环依赖被拒绝 |
| 缺少模型配置 | `/api/submit` 返回 `FAILED` Run；错误和 Task 状态保存在 SQLite，可在运行列表查看 |
| 原有路径 | 未选择本地规划时继续使用远端 Planner；全部回归测试通过 |

本机 `.venv312/bin/python -m unittest discover -s tests -v`：24 项通过。当前 Mac 没有配置模型 API 凭据，因此**尚未进行真实模型服务的本地主 Agent 端到端验收**；本地主规划保持用户显式选择，不切为默认。真实模型验收应在同一隔离任务上比较计划、耗时和失败信息，再决定是否切换默认。
