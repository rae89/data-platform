# CLAUDE.md

Project guidance is shared with other agents in AGENTS.md:

@AGENTS.md

## Claude Code notes

- Prefer `make` targets and `uv run dg ...` over calling `dagster` directly.
- Before finishing a change, run `make check` and the tests listed in AGENTS.md, and
  report any failures.
- When work from `TODO.md` is done, check off its items there.
