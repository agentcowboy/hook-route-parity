# hook-route-parity

Compare declared hook routes — event, matcher, command, args and if — in two Claude Code settings or plugin hooks JSON files. Exit 0 means the normalized route sets match; 1 means drift; 2 means an input or usage error.

`hook-route-parity` v0.1 compares only direct handlers with `type: "command"`
under `hooks → event → matcher groups → hooks array`. It never runs configured commands.

Commands lose only outer ASCII whitespace. Matchers omitted, `""`, or `"*"` normalize
to `""`, except for `FileChanged`: there `"*"` also adds a literal file named `*` to the watch list,
so it stays distinct from an omitted matcher. Matcher-ignoring events also normalize to `""`, following the
[hooks documentation](https://code.claude.com/docs/en/hooks) fetched 2026-10-03.
Matcher-ignoring events: `UserPromptSubmit`, `PostToolBatch`, `Stop`, `TeammateIdle`, `TaskCreated`, `TaskCompleted`, `WorktreeCreate`, `WorktreeRemove`, `MessageDisplay`, `CwdChanged`.
Unknown events compare literally. No paths, variables, or regexes are expanded.
`args` keeps its exact string list and order: absent differs from `[]` (shell
form versus exec form). `if` keeps its exact string; absent means `""`.

Ordering, matcher group boundaries, and duplicate counts are ignored: identical
routes collapse into one set entry. Other handler types, including `http`,
`mcp_tool`, `prompt`, and `agent`, are ignored, as are `timeout`, `async`,
`asyncRewake`, `statusMessage`, `once`, and `shell`.
Ignored fields such as `shell` can still change how a hook runs.
Missing top-level `hooks`, `hooks: {}`, and an event with `[]` yield no routes.
Malformed containers or route fields are input errors, including missing types
and command strings, and event names that are not printable or contain whitespace.
Errors name the side and problem, with JSON line/column when available.
Output never includes filenames, commands, matchers, arguments,
conditions, input snippets, or hashes; drift output names events and counts.

Matching sets do not prove hooks fire. Settings layers (user, project, local,
managed) and managed policy are not merged; `disableAllHooks` is not considered.
Script availability is not checked. Skill and subagent YAML hooks are not covered.

Requirements: Python 3.11 or newer (tested on 3.11 and 3.13), and Bash for acceptance.
No packages or installation needed.
From the checkout:

```bash
python3 hook_route_parity.py LEFT.json RIGHT.json
python3 hook_route_parity.py examples/left.json examples/right.json
```

The second command exits 1 and prints:

```text
DRIFT PostToolUse left-only=0 right-only=1
DRIFT PreToolUse left-only=1 right-only=1
DRIFT command-routes events=2
```

Run `bash ACCEPTANCE` from the checkout, or `bash /path/to/checkout/ACCEPTANCE`
from any directory. It uses temporary synthetic JSON and checks the real CLI,
including disclosure canaries in both output streams. Failures or skipped tests
prevent the final PASS line. Success exits 0 and prints exactly:

```text
HOOK_ROUTE_PARITY TESTS run=64 failures=0 errors=0 skips=0
HOOK_ROUTE_PARITY ACCEPTANCE PASS
```

Nearby alternatives: [oh-my-harness](https://github.com/kyu1204/oh-my-harness)
generates configuration and checks generated-file drift;
[claude-hooker](https://github.com/mattsta/claude-hooker) checks its own hook
definitions and diagnoses installs. This tool compares
two existing files without adopting a generator or hook framework.

MIT licensed, copyright 2026 agentcowboy.

Built with AI coding agents.

v0.1.1: `FileChanged` keeps `"*"` distinct from an omitted or empty matcher.
