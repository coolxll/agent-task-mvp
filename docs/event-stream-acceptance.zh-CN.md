# 执行事件流与 UI 验收（2026-09-25）

## 行为

- Manager 从 Runner 的已有状态和日志轮询结果生成 `run_events` 表：阶段状态、普通日志行及 ACP 工具事件分别记录。事件 ID 单调递增，可在 Manager 重启后继续读取。
- `GET /api/runs/{id}/events` 返回最近 1000 条事件；传 `after` 可按 ID 顺序分页。`GET /api/runs/{id}/stream?after=<id>` 通过 SSE 推送后续事件，并支持 `Last-Event-ID` 断线续读。Runner 与 Manager 之间仍使用原有简单 HTTP 轮询。
- 中文和英文 UI 的运行详情增加执行事件列表，并把后续日志实时追加。状态到达 `NEEDS_INPUT`、`REVIEW` 或终态时刷新详情，使回答和交付验收操作可见。原始日志和最终 Artifact 仍可查看。
- Review 交付处于 `pending/publishing` 时保留 5 秒刷新，直到 PR 或本地成果状态就绪。

## 验证

- 本地完整工作流测试检查 `REVIEW` 状态事件、规划日志事件、递增 ID，以及 SSE 从指定 ID 返回下一事件。并发测试确认本地 Planner 等待模型时不会锁住 SQLite 的另一笔写入。
- `node --check ui.js` 通过；本机 `.venv312/bin/python -m unittest discover -s tests -v` 全部通过。

## 限制

事件延迟由 Manager 原有 2 秒轮询决定。页面断线后能从持久化事件补读；超过最近 1000 条的历史仍可通过分页 API 或原始日志读取。ACP 工具事件取自适配器日志，其他 Agent 目前只有阶段与文本日志事件。尚未做浏览器视觉验收。
