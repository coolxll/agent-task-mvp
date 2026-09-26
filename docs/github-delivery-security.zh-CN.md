# GitHub 交付安全边界

本文说明当前 `control.py` 与 `app.py` 实现的 GitHub PR 交付检查，以及这些检查已有哪一层证据。这里的“已实现”表示源码中的确定性检查；“本地集成通过”表示测试使用本地 Git 仓库和模拟的 `gh` 响应覆盖了该路径；两者都不等同于真实 GitHub 仓库已经验收。

## 发布前固定并核对成果

Runner 完成代码评审、Gate 和验收后，将 worktree 当前 `HEAD` 写入 `artifacts.commit_sha`，并从该成果分支生成 `result.bundle`。Manager 只为仍处于 `REVIEW`、交付状态为 `pending` 或 `publishing` 的 Run 导入成果。

导入和发布依次执行以下检查：

1. Runner 仅在 Run 为 `REVIEW` 或 `SUCCEEDED` 时提供结果 bundle。Manager 解码时校验 base64、48 MiB 大小上限和随响应传回的 SHA-256；随后由 Git 将 bundle 中的成果分支 fetch 到 Manager 的 bare 仓库。
2. Manager 解析导入分支的提交，并要求它精确等于已审核的 `artifacts.commit_sha`；同时要求 `artifacts.base_sha` 是该提交的祖先。任一检查失败都会把交付标为 `failed`，不会继续 GitHub push。
3. 完成上述导入与提交校验后，Manager 把交付标为 `ready`；这个状态表示成果已成功导入，并不单独证明 GitHub PR 已创建。仅当交付类型是 GitHub 且 `ready_to_merge=true` 时，Manager 才要求存在变更文件，从已验证的本地分支 ref 推送同名远端分支，再查找或创建以任务包 `source.base_branch` 为 base 的 PR；该分支中的任何步骤失败都会改记为 `failed`。若 `ready_to_merge=false`，发布阶段跳过 GitHub push 和 PR 操作，仍会把已导入的交付记为 `ready`，而批准阶段会因成果未通过评审、测试或验收而拒绝合并。

因此，正常发布路径推送的是 Manager 已从 bundle 导入并与审核记录比对过的提交，而不是重新从可变工作目录临时生成的内容。SHA-256 在此用于发现传输内容与响应摘要不一致；它本身不是 GitHub 身份或签名证明。

## 批准时的再次核对与合并固定

批准请求只接受处于 `REVIEW` 的 Run。对于带当前流水线版本的成果，Manager 还要求 `ready_to_merge=true`，并要求交付已经是 `ready`（或此前已记录为 `merged`）。首次执行尚未记录为 `merged` 的 GitHub 合并时，顺序如下：

1. Manager 再次读取 Runner 状态，要求其中记录的 `commit_sha` 与 `artifacts.commit_sha` 相同。
2. Manager 读取目标 PR 的 `state`、`headRefOid` 和 `baseRefName`，要求 PR head 精确等于已审核提交，base 精确等于任务包中固定的 base 分支。head 或 base 变化会中止批准，要求重新审核。
3. PR 必须已经是 `MERGED`，或仍为 `OPEN`。对于开放 PR，Manager 使用 squash 方式调用 `gh pr merge`，并传入 `--match-head-commit <artifacts.commit_sha>`，使 GitHub 在合并操作处再次约束 head。
4. 合并命令返回后，Manager 再查询 PR 状态；只有状态确认为 `MERGED` 才把本地 `delivery_status` 记为 `merged`。分支保护或 required checks 尚未允许合并时，不会把交付误记为成功。
5. 随后 Manager 才调用 Runner 的批准接口。Runner 要求 worktree `HEAD` 仍等于 `artifacts.commit_sha`，且当前流水线成果的 worktree 保持干净；检查通过后移除 worktree，并把 Run 置为 `SUCCEEDED`。

第 1 项核对的是 Runner 持久状态中记录的提交；对 Runner worktree 实际 `HEAD` 和洁净度的核对发生在第 5 项。若 GitHub 已合并并记录为 `merged`，但后续 Runner 调用失败，可以重试批准以完成 Runner 侧检查和清理；重试时不会再次发起 GitHub 合并。代码没有宣称整个 GitHub API、Manager 数据库和 Runner 清理构成一个原子事务。

## 拒绝与清理的边界

- 尚未合并时拒绝：若已有 PR，Manager 调用 `gh pr close`；之后 Runner 的拒绝接口移除该 Run 的 worktree，并在状态记录的 `source_path` 仓库中删除名称以 `agent/task-` 开头的本地成果分支，Run 变为 `REJECTED`。
- 已记录为 `merged` 后拒绝：Manager 明确拒绝该操作，要求重试批准来完成清理，避免把已合并成果伪装成已拒绝。
- 批准成功：Runner 移除 worktree，但以 `delete_branch=false` 清理，因此不删除 Runner 本地成果分支。
- 失败或取消 Run 的独立 cleanup 接口只接受 `FAILED` 或 `CANCELLED`，并在 worker 已停止后移除 Runner worktree，以及状态记录的 `source_path` 仓库中名称以 `agent/task-` 开头的本地分支。

清理前，Runner 要求 worktree 的路径精确匹配 `<runner-root>/worktrees/<run-id>` 且不是符号链接；对本地分支的所有权检查则只要求分支名以 `agent/task-` 开头。分支删除在状态记录的 `source_path` 仓库中执行，实现没有要求该源仓库位于 Runner 根目录下，因此不能把 Runner 根目录约束扩大解释为对本地分支或源仓库路径的约束。当前拒绝路径关闭 PR，但不删除 GitHub 远端成果分支；无论批准或拒绝，也不删除 Manager 已导入的 `result.git`、运行记录或审核证据。若关闭 PR、调用 Runner 或更新状态之间发生外部故障，可能需要重试，不能把“拒绝”理解为跨 GitHub、Manager 与 Runner 的原子回滚。

## 证据分层

### 源码支持的实现保证

上述 bundle 解码、Git 提交与祖先校验、发布条件、Runner 提交复核、PR head/base 复核、`--match-head-commit` 固定、合并后 `MERGED` 状态确认，以及受限的 Runner 清理边界，分别由 `control.py` 的 `publish()` / `review_delivery()` 和 `app.py` 的 Runner bundle、review、cleanup 接口执行。这些是当前代码路径提供的检查，不代表外部服务永不失败，也不把 squash 后目标分支的新提交 SHA 等同于被审核的 PR head SHA。

### 本地、模拟 `gh` 的集成证据

`tests/test_workflow.py` 覆盖了以下行为：

- `test_07a_publish_pushes_exact_commit_and_creates_pr` 从真实测试 Runner 获取结果 bundle，导入本地 bare 仓库，并把成果分支实际推送到本地 bare remote；`gh pr list/create/view` 由 fixture 模拟。测试确认远端分支指向 `artifacts.commit_sha`。
- `test_07_pr_merge_is_pinned_and_requires_merged_state` 模拟 Runner 与 GitHub 响应，确认合并命令包含 `--match-head-commit`，并覆盖合并后复查到 `MERGED` 才记录成功的路径。
- `test_08_pr_head_change_blocks_merge` 模拟 PR head 被改变，确认批准在发起合并前失败。
- `test_05_source_bundle_validation` 验证错误的 bundle SHA-256 被拒绝；完整工作流测试还验证审核、Gate、验收、成果导入和 Runner 清理的相关状态转换。

这里的 Git push 和 bundle 导入使用真实 Git 命令，但 GitHub PR API 是模拟的。因此这些测试是本地集成证据，不是 GitHub 对 branch protection、required checks、认证权限、PR 创建、squash 合并或网络故障行为的现场证明。

### 真实 GitHub 验收状态

本文件不声称已经完成真实 GitHub 验收。本次 Run 被用户批准之前，尚不能以它证明真实仓库中的分支推送、PR 创建、head/base 复核、`--match-head-commit`、保护规则阻挡、合并后状态确认或最终 Runner 清理均已现场通过。真实验收应在隔离的 GitHub 仓库或明确授权的测试 PR 上执行，并单独记录仓库、PR、审核提交、观察到的保护规则结果和清理结果。
