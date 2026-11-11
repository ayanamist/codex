# Configuration

For basic configuration instructions, see [this documentation](https://developers.openai.com/codex/config-basic).

For advanced configuration instructions, see [this documentation](https://developers.openai.com/codex/config-advanced).

For a full configuration reference, see [this documentation](https://developers.openai.com/codex/config-reference).

## Project MCP JSON compatibility in this fork

Trusted projects can use `.mcp.json` directly, with a `mcpServers` object or a
bare server map. Codex discovers files between the project root and current
directory; nearer files win, and same-directory `.codex/config.toml` has
priority. The JSON supports stdio and Streamable HTTP, common `headers`,
`${VAR}` / `${VAR:-default}` references, comments and trailing commas.
Legacy `type: "sse"` produces a warning and is skipped. Invalid server entries
are isolated from valid siblings. See the [compatibility contract and
verification](fork/project-mcp-configuration.md) for paths, merge rules,
unsupported fields and upstream/reference implementation differences.

## Lifecycle hooks

Admins can set top-level `allow_managed_hooks_only = true` in
`requirements.toml` to ignore user, project, and session hook configs while
still allowing managed hooks from requirements and managed config layers. This
setting is only supported in `requirements.toml`; putting it in `config.toml`
does not enable managed-hooks-only mode.
