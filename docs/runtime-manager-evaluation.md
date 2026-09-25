# Runtime manager evaluation (2026-09-25)

Scope: the MVP's remote `Run → Codex → logs/status/cancel → gates/diff/review` path on `corp172-dev`. No runtime manager was wired into the MVP during this evaluation.

## Herdr

- The local Herdr client has an enabled `corp172-dev` machine profile. The remote server reports version `0.9.1` and a compatible API. Remote `agent list` and `pane list` work.
- Herdr can create a pane, start Codex in it, prompt it, wait for `idle`/`done`/`blocked`, read terminal output, send keys, and manage worktrees. See the [CLI reference](https://herdr.dev/docs/cli-reference/).
- Isolated spike: created a temporary Herdr workspace on `corp172-dev` with cwd `/workspace/agent-task-mvp-fixture`, started Codex in its pane, submitted `Reply READY only`, observed `done`, and read `READY` from terminal output. The temporary Herdr workspace was then closed.
- The first prompt stalled because Codex displayed a first-run hook review modal while Herdr classified the pane as `idle`. After dismissing the modal, the same prompt completed. An unattended adapter must check startup output and handle unexpected interactive prompts; `idle` alone is not sufficient evidence that a turn was accepted.
- This is useful for a human to observe or take over an interactive coding session. Its agent state is inferred from an interactive terminal; our deterministic Gate step would still need its own completion contract and result extraction.

## Paseo

- `corp172-dev` already has a running Paseo daemon (`0.8.0`). `paseo provider diagnostic codex --json` reports Codex ready.
- The installed CLI supports `run --background --json`, `--cwd`, `--workspace`, worktree creation, `wait --json`, `inspect --json`, `logs`, `stop`, and archive. Paseo also has a [TypeScript SDK](https://paseo.sh/docs/sdk) with agent handles and [worktree workspaces](https://paseo.sh/docs/sdk/workspaces).
- Isolated spike: in a disposable named worktree, `paseo run --provider codex --mode full-access --workspace <id> --background --json` returned agent ID `47c8a463-51f8-4c96-a697-ed3fa4ac068e`; `wait --json` returned `idle` and the requested `READY`; `inspect --json` and `logs` returned the session and response. The agent and Paseo workspace were archived, then the disposable Git worktree and branch were removed.
- Version-specific detail: `--mode bypass` failed on this daemon; its Codex modes are `auto`, `auto-review`, and `full-access`. That failed invocation had already created a Paseo workspace. An adapter must handle partial creation and use discovered mode IDs.

## Decision for the MVP

Keep the current Codex CLI driver for the structured execution stages. It provides a direct process exit code, JSON log stream, and summary file, and the Runner already owns Git worktree, gates, diff, and review artifacts.

2026-09-25 follow-up after multi-turn became a requirement: a disposable Paseo `codex` agent on `corp172-dev` ran in `full-access`, returned `idle` from `wait`, accepted `send` for a second turn, and was archived with its disposable workspace. `run --background --json` and `send --json` expose agent ID/status, but not the complete structured final answer. `logs` returns a human-readable transcript; in installed CLI 0.8.0, `--output-schema` is rejected with `--background`. The current plan/review/acceptance pipeline requires a machine-readable final answer for each stage, so replacing the direct driver with log scraping would reduce reliability. A later Paseo adapter should use its SDK/API for final message and activity events, then pass the same end-to-end acceptance cases before becoming default.

Paseo is the better candidate to manage the **Agent session only** once its SDK/API integration is verified. The Runner should still own the Task's source clone, worktree, gates, diff, and approve/reject semantics. A `PaseoDriver` would persist Paseo's agent/workspace IDs, map `idle/permission/error` into Run states, forward activity, call `stop` for cancellation, and archive only resources created for that Run. It should not introduce a second Project or Review source of truth.

Herdr remains useful as an optional interactive operator surface, but it is a weaker fit for the unattended, deterministic Gate transition in this MVP.

References: [Paseo CLI](https://github.com/getpaseo/paseo/blob/main/public-docs/cli.md), [Paseo agent SDK](https://paseo.sh/docs/sdk/agents), [Paseo workspaces](https://paseo.sh/docs/sdk/workspaces), [Herdr CLI](https://herdr.dev/docs/cli-reference/).
