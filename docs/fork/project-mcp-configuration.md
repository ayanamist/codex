# Project MCP configuration

Reviewed and implemented: 2026-11-11. Scope: working-tree changes to this fork
based on `f7ed43000b`, workspace version `0.167.1`. Upstream documentation and
reference implementation observations below were checked on the same date.

## Contract

This fork automatically loads `.mcp.json` as runtime MCP configuration in
trusted projects. It searches from the existing project root through cwd,
with nearer directories taking precedence. No `.codex` directory or import
step is required. Without a project marker, discovery is limited to cwd.
The unchanged upstream baseline used only `.codex/config.toml` for ordinary
project MCP configuration; the JSON compatibility described here is a fork
addition. User configuration defaults to `~/.codex/config.toml` (under
`CODEX_HOME` when overridden).

For example, a project can declare `.mcp.json`:

```json
{
  "mcpServers": {
    "example": {
      "command": "node",
      "args": ["./tools/mcp-server.js"]
    },
    "api": {
      "type": "http",
      "url": "${MCP_BASE_URL:-https://example.com}/mcp",
      "headers": { "Authorization": "Bearer ${MCP_TOKEN}" }
    }
  }
}
```

The referenced executable/script must already be available, and the HTTP
example requires `MCP_TOKEN` in the executing host's environment. JSONC
comments, trailing commas, BOM and a bare server map are also accepted.
Relative stdio cwd defaults to the JSON file's directory, so the same root
declaration works when Codex is started in a subdirectory.

Same-directory native `.codex/config.toml` overrides JSON. Complete JSON
registrations replace lower-priority entries by server name; native
control-only settings can disable them or restrict tools. Invalid entries,
missing variables and legacy SSE entries produce warnings and do not start;
they mask lower same-name registrations rather than reactivating them.
Other valid entries remain available. Values expanded from the environment
are not included in these diagnostics. There is no automatic file watcher;
new sessions and existing full configuration reloads reread the file.

There are two additional, independent uses of `.mcp.json` in the source:

- Installed/selected plugins can bundle `.mcp.json` at their plugin root.
  The plugin loader resolves this file from the plugin manifest or its
  conventional fallback. This is scoped to plugin loading, not arbitrary
  project roots.
- External-agent migration can read project `.mcp.json`, translate its
  `mcpServers` entries into Codex TOML, and write missing entries into the
  project's `.codex/config.toml`. Importing configuration does not establish
  a runtime link to the original JSON file.

`codex mcp add` currently edits the user/global configuration, including when
invoked from a project directory. Its implementation prints
`Added global MCP server` after writing the configuration.

## Evidence

- [Official MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli):
  user and trusted-project TOML configuration.
- [Official plugin packaging documentation](https://developers.openai.com/plugins/build/plugins):
  the Codex compatibility plugin layout includes `.codex-plugin/plugin.json`
  and optional `.mcp.json`. Portable Agent Plugins use root `plugin.json`
  and `mcp.json` instead.
- `codex-rs/config/src/loader/mod.rs`, `discover_project_layers`: discovers
  `.mcp.json` and `.codex/config.toml` between the project root and working
  directory with the same trust gating.
- `codex-rs/config/src/project_mcp.rs`: JSONC compatibility parsing, variables,
  transport/header aliases, isolated warnings and atomic JSON registrations.
- `codex-rs/config/src/state.rs`: effective MCP merge and removal of displaced
  field origins, preserving native TOML-only behavior.
- `codex-rs/config/src/loader/local.rs`: equivalent replacement semantics for
  plain TOML projections consumed through executor-local configuration RPCs.
- `codex-rs/cli/src/mcp_cmd.rs`: list/get print configuration warnings to stderr
  while keeping JSON stdout parseable.
- `codex-rs/core-plugins/src/loader.rs`, `default_mcp_config_paths`, and
  `codex-rs/ext/mcp/src/plugin/provider.rs`, `load_from_file_system`: plugin
  `.mcp.json` lookup.
- `codex-rs/external-agent-migration/src/mcp.rs`,
  `read_external_mcp_servers`: external JSON input and TOML translation.
- `codex-rs/external-agent-migration/src/service.rs`,
  `import_mcp_server_config`: repository imports write `.codex/config.toml`.
- `codex-rs/external-agent-migration/src/service_tests/general/config_import.rs`:
  existing tests specify detection of missing project servers and preservation
  of existing same-named TOML entries.
- `codex-rs/cli/src/mcp_cmd.rs`: MCP add writes through
  `ConfigEditsBuilder::new(codex_home)`.

## Verification and limitations

The initial investigation used source and official-documentation inspection.
The cross-agent comparison below checks documentation and source, not the
versions installed on this machine. Implementation verification is recorded
separately below; no existing user installation was replaced.

Recheck after upgrades with these read-only commands:

```sh
git rev-parse HEAD
rg -n '\.mcp\.json' codex-rs
rg -n 'discover_project_layers|CONFIG_TOML_FILE' codex-rs/config/src/loader/mod.rs
rg -n 'import_mcp_server_config|target_config' codex-rs/external-agent-migration/src/service.rs
rg -n 'Added global MCP server|ConfigEditsBuilder::new' codex-rs/cli/src/mcp_cmd.rs
```

## Cross-agent comparison

Checked: 2026-11-11. Scope: the public documentation/current source linked
below, with local CLI/IDE use distinguished from plugins and cloud agents.
The sample establishes adoption, not market share or exhaustive compatibility.

Project-scoped MCP configuration is a common design. A root `.mcp.json`
with a top-level `mcpServers` object is an established cross-tool convention:
Claude Code and GitHub Copilot CLI document it directly, current VS Code
Copilot documentation includes it, and the Pi MCP adapter extension reads it.
It is not a configuration location shared by every agent. Several tools
document their own project paths; even similar JSON formats differ in
transport names, environment-variable syntax, and other fields.

| Agent / integration | Documented project configuration | Root `.mcp.json` finding |
| --- | --- | --- |
| Claude Code | `.mcp.json`, top-level `mcpServers` | Native project scope; project server approval applies. [Official MCP scopes](https://code.claude.com/docs/en/mcp#project-scope) |
| GitHub Copilot CLI | `.mcp.json` and `.github/mcp.json` | Native discovery from cwd upward to the Git root; workspace trust required. [Official setup](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers#adding-per-repository-mcp-servers) |
| VS Code / Copilot harness | Root `.mcp.json` (`mcpServers`); also `.vscode/mcp.json` (`servers`) | Current documentation says Copilot harness sessions read the portable root format directly. The experimental setting controls whether Add Server offers this destination; existing files remain available with it off. [Official reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) |
| Pi, built-in MCP | `.pi/mcp.json`, top-level `mcpServers` | Official documentation names the Pi-specific path, with project trust. User path is `~/.pi/agent/mcp.json`. [Official source documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md) |
| Pi with `pi-mcp-adapter` extension | Root `.mcp.json`, plus adapter/Pi-specific files | The extension explicitly reads root `.mcp.json` as shared project configuration; distinguish this from the built-in loader. [Extension maintainer's configuration documentation](https://github.com/nicobailon/pi-mcp-adapter/blob/main/docs/configuration.md#file-layout) |
| Cursor | `.cursor/mcp.json`, top-level `mcpServers` | Official documentation lists a different project path. [Official MCP setup](https://prod.cursor.com/help/customization/mcp) |
| Gemini CLI | `.gemini/settings.json`, `mcpServers` setting | Official documentation lists a different project path. [Official tutorial](https://geminicli.com/docs/cli/tutorials/mcp-setup/) |
| OpenCode | Project `opencode.json` / `opencode.jsonc`, MCP settings | Official documentation lists a different project path. [Official configuration](https://opencode.ai/docs/config), [MCP configuration](https://opencode.ai/docs/mcp-servers) |
| Roo Code | `.roo/mcp.json`, top-level `mcpServers` | Official documentation explicitly says this project file is automatically detected. [Official documentation](https://roocodeinc.github.io/Roo-Code/features/mcp/using-mcp-in-roo/) |
| Cline | CLI user file `~/.cline/data/settings/cline_mcp_settings.json`; IDE-managed MCP settings JSON | The inspected official page documents these settings, not automatic project-root `.mcp.json` discovery. This is not an exhaustive source-level negative finding. [Official MCP documentation](https://docs.cline.bot/mcp/mcp-overview) |
| Codex upstream baseline / this fork | Upstream: `.codex/config.toml`; fork addition: `.mcp.json` | This working tree adds trusted-project JSON runtime loading as described in the contract above. Plugin loading and one-time migration remain independent. |

Pi is version-sensitive: current Pi documentation includes built-in MCP, while
older Pi material described a core without MCP and third-party extensions
provided it. The adapter's current documentation explicitly distinguishes
Pi 0.99-and-later native files from its shared `.mcp.json` inputs. A statement
that "Pi supports `.mcp.json`" therefore needs to identify the integration.

Do not treat an explicit file argument as automatic discovery. For example,
Copilot CLI also accepts `--additional-mcp-config` JSON or `@file` for one
session; its root-file support is independently documented in its workspace
loading rules. [Official command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)

For agents whose documentation lists another path, the table establishes
their documented configuration contract; it does not prove that every
version, extension, import feature, or compatibility loader rejects root
`.mcp.json`. No agent was installed or executed for this comparison.
Windsurf's old official MCP URL redirected to an inaccessible successor page
during this check, so its current behavior is not included as a verified row.

Recheck by opening the linked configuration sections and, when necessary,
the owning loader source. Keep project discovery separate from user settings,
plugin packages, explicit imports, and remote/cloud configuration.

## Upstream implementation search

Checked: 2026-11-11, using the GitHub API for `openai/codex`. No open PR
implementing ordinary project-root `.mcp.json` automatic loading was found in
the searches below. This is a scoped search result, not proof that no branch
or differently described patch exists.

The closest implementation is
[PR #12718, Add support for local cwd mcp.json MCP server config](https://github.com/openai/codex/pull/12718).
It was opened and closed on 2026-02-24 without merging. Its actual constant
is `LOCAL_MCP_JSON_FILE = "mcp.json"`: it reads the **non-dot** filename in
the current working directory only, rather than discovering project-root
`.mcp.json` when launched from a subdirectory. It accepts `mcpServers` or a
direct server map, translates directly through `McpServerConfig`, applies
project trust, and gives local JSON precedence over same-named TOML entries.
It includes loader tests, but the author reported that they could not run
the tests because their Cargo toolchain was too old. The old patch targets
`core/src/config_loader`; the current loader is in `config/src/loader`.
These differences make it a reference rather than a drop-in patch.

The maintainer closed that PR citing the policy against unsolicited code
contributions and separately pointed to layered TOML project configuration.
This does not establish rejection of JSON compatibility on technical grounds.
[Closure comment](https://github.com/openai/codex/pull/12718#issuecomment-3955303240),
[configuration comment](https://github.com/openai/codex/pull/12718#issuecomment-3955307687).

The author's follow-up
[issue #13056](https://github.com/openai/codex/issues/13056) was closed as
completed on 2026-08-05. The
[maintainer's closing comment](https://github.com/openai/codex/issues/13056#issuecomment-5187109295)
specifically says trusted-project `.codex/config.toml` supports MCP servers;
it does not claim `.mcp.json` runtime loading was implemented.

Two merged PRs provide related code but solve different problems:

- [#19949, external configuration detection/import](https://github.com/openai/codex/pull/19949),
  merged 2026-04-29: converts external configuration to Codex-native files.
- [#27863, shared plugin MCP parsing](https://github.com/openai/codex/pull/27863),
  merged 2026-06-12: extracts JSON parsing and normalization into `codex-mcp`.
  It preserves plugin-specific semantics and does not add arbitrary project
  config discovery. Any parser reuse needs to account for that scope.

Verification commands (read-only; query encoding is handled by `gh`):

```sh
gh api -X GET search/issues -f q='repo:openai/codex is:pr "mcp.json"' -f per_page=100
gh api -X GET search/issues -f q='repo:openai/codex is:pr is:open "mcp.json"' -f per_page=100
gh api -X GET search/issues -f q='repo:openai/codex is:pr is:open "mcpServers"' -f per_page=100
gh api repos/openai/codex/pulls/12718
gh api repos/openai/codex/pulls/12718/files --paginate
gh api repos/openai/codex/issues/12718/comments --paginate
gh api repos/openai/codex/issues/13056
gh api repos/openai/codex/issues/13056/comments --paginate
```

## Reference implementation evidence

Checked: 2026-11-11, by reading upstream source without installing or running
the referenced applications. These are observed contracts of specific
implementations, not a proposed Codex contract.

- `nicobailon/pi-mcp-adapter`: package version `7.0.1`, commit
  `5397dabc0f8eba1c7804baaf092e4c2cf0cc0130` (2026-11-11).
- `microsoft/vscode`: commit
  `b171a702a976feda601dbe6ae3e80935644898be` (2026-11-11).
- Copilot CLI and Claude Code runtime internals were not source-audited.
  Their documentation does not prove that their complete parsing/runtime
  semantics match either open-source implementation below.

### Pi MCP adapter: shared project `.mcp.json`

This is the adapter's **shared-file** path. Its separate translation of
Pi-native `.pi/mcp.json` has stricter validation and different merge handling.

| Concern | Observed implementation |
| --- | --- |
| Discovery and boundary | Default shared project path is exactly `resolve(cwd, ".mcp.json")`. Ancestor discovery requires a user-global `settings.ancestorConfigRoots` opt-in. Valid roots must be existing directories under HOME; the nearest configured root containing cwd bounds a root-to-parent traversal. Git markers are not used by this discovery. Pi-native `.pi/mcp.json` remains cwd-only. [Paths and discovery][pi-discovery] |
| JSON and top-level shape | Removes UTF-8 BOM, comments and trailing commas before `JSON.parse`. Shared-file validation reads `mcpServers` or the alias `mcp-servers`; it does **not** interpret a bare server map as servers. Non-object top-level/server maps become empty maps. [JSON helper][pi-json], [shared validation][pi-validation] |
| Server validation and errors | Parse/read exceptions warn and skip the file. Non-object server entries are skipped, while object entries receive shallow validation; provider-auth validation can skip one entry and an invalid description is removed without dropping that server. Transport validation occurs later at connection time. [File errors][pi-file-errors], [shared validation][pi-validation] |
| Transport and `type` | The shared runtime selects exactly one nonempty `command`, `url`, or adapter-specific `socket`; `type` is not the discriminator on this path. `command` selects stdio. URL connections start with Streamable HTTP by default, with SSE fallback only on selected endpoint-incompatibility failures. `httpTransport` can force a transport without fallback. This differs from Pi-native translation, which explicitly validates `type`. [Connection selection][pi-connect], [HTTP fallback][pi-http] |
| Headers and environment | HTTP `headers` and stdio `env` pass through the adapter's secret/environment resolvers at connection time. Stdio inherits `process.env` unless `inheritEnv: false`, then applies configured overrides. Besides variable interpolation, this adapter supports its own command-backed secrets; those are adapter behavior, not generic MCP-file semantics. [Headers][pi-headers], [stdio environment][pi-env], [secret resolution][pi-secrets] |
| Variables, unset and empty | `${VAR}` and `${VAR:-default}` are supported; the default applies only when unset, and an explicitly empty variable stays empty. Generic interpolation replaces an unset variable without a default with `""`; URL resolution instead checks for missing variables and fails before validating the final URL. The helper also recognizes `$env:VAR` and `{env:VAR}`. [Interpolation][pi-interpolation], [URL/path helpers][pi-paths] |
| `cwd` and relative paths | Stdio expands variables/home markers in command, args and cwd. Missing cwd defaults to the session cwd, via `new McpServerManager(cwd)`. The shared-file path does not rebase command/args/cwd to the directory containing an ancestor config. The inspected call passes relative strings onward to the stdio SDK/Node; exact OS command-resolution behavior was not followed into that dependency. [Initialization][pi-init], [stdio launch][pi-connect], [path helpers][pi-paths] |
| Same-name merge | Shared sources merge server fields shallowly, later fields winning; `env`/`headers` are whole fields, not recursively merged maps. Changing transport removes incompatible inherited fields; changing URL strips inherited URL-bound authentication fields. Pi-native project/global files have special handling to preserve Pi's whole-entry replacement instead. [Shared merge][pi-merge], [shallow spread][pi-shallow], [Pi-native handling][pi-native-merge] |
| Enable/disable and unknown fields | Shared entries disable only when `disabled === true`; `enabled: false` is not translated on this path. Shared object entries retain unrecognized properties, but that does not make them operational: only fields consumed by runtime code have an effect. Pi-native translation separately converts `enabled: false`. [Disabled predicate][pi-disabled], [shared validation][pi-validation] |
| Trust and reload | Initialization resolves project trust before creating the runtime manager. Project servers require a trusted project and approval of the effective definition, or an explicit permitted approval policy. Changed definitions are hashed separately. Enable/disable writes explicitly tell the user to run `/reload`; automatic file watching was not established by this inspection. [Initialization][pi-init], [trust gate][pi-trust], [reload instruction][pi-reload] |

### VS Code workspace-root reader

| Concern | Observed implementation |
| --- | --- |
| Discovery, trust and updates | `WorkspaceDotMcpDiscovery` inspects `.mcp.json` at each VS Code workspace folder root, without Git-root traversal. A non-Git workspace folder uses the same path. The collection inherits workspace trust. A nonrecursive file watcher schedules re-reading after 500 ms; missing/malformed files produce no definitions. This establishes config rediscovery, not every running-process restart detail. [Workspace discovery][vsc-discovery] |
| JSON and shape | `parseWorkspaceRootMcpConfiguration` uses the VS Code JSON parser with trailing commas enabled. It accepts wrapped `mcpServers` or a bare server map; malformed top-level JSON throws, while invalid server entries are omitted individually. Comments are supported by the underlying JSON parser; BOM behavior was not independently traced. [Root parser][vsc-root-parser] |
| Normalization | Copilot's legacy `type: "local"` is mapped to stdio. The shared normalizer recognizes stdio, HTTP, `streamable-http`, SSE and missing type inferred from command or URL; filters invalid args/env/header values; constructs a new object containing supported properties. Unknown properties, including root-entry `enabled`/`disabled`, are not preserved by this normalizer. [Copilot adapter][vsc-copilot], [normalizer][vsc-normalizer] |
| Runtime handoff and limitations | Root discovery then calls `claudeConfigToServerDefinition`, which uses `command` for stdio and `url` for an HTTP launch, forwards args/env/headers, and supplies workspace folder as default cwd. That handoff does not forward all normalized properties, including explicit cwd or SSE transport. Therefore recognizing an SSE field during normalization does not establish end-to-end SSE behavior for this root-file route. Variable expansion is marked on the resulting definitions, but the final resolver and unset/empty-variable behavior were not traced. [Workspace handoff][vsc-discovery], [definition conversion][vsc-conversion] |
| Read versus create/install | The root-file install validator is stricter than the reader: it rejects properties such as cwd/envFile, non-HTTP transport and interpolation, directing users to `.vscode/mcp.json`. These create/install restrictions must not be confused with all behavior of manually supplied files. Cross-source same-name precedence was not audited beyond distinct per-folder collection/server IDs. [Install validator][vsc-install] |

For comparison, the closed-source Copilot CLI's
[official workspace-loading documentation](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers#adding-per-repository-mcp-servers)
specifies cwd-to-Git-root discovery, same-directory `.mcp.json` precedence over
`.github/mcp.json`, and closer-directory precedence for conflicting server
names. That documentation alone does not settle field-level merging, JSONC,
non-Git discovery, or every proprietary field/error rule. Do not substitute
the VS Code workspace reader for evidence about the CLI's implementation.

Reproduce the source inspection with `gh api repos/OWNER/REPO/contents/PATH
-f ref=COMMIT -X GET`, decoding its `content` field, and inspect the pinned
functions linked below. No referenced project's tests were run.

[pi-discovery]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/config.ts#L835-L1042
[pi-json]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/utils.ts#L19-L25
[pi-validation]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/config.ts#L1494-L1584
[pi-file-errors]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/config.ts#L1321-L1332
[pi-connect]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/server-manager.ts#L1201-L1265
[pi-http]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/server-manager.ts#L1875-L1930
[pi-headers]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/server-manager.ts#L1691-L1709
[pi-env]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/server-manager.ts#L2255-L2274
[pi-secrets]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/utils.ts#L230-L277
[pi-interpolation]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/utils.ts#L146-L164
[pi-paths]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/utils.ts#L280-L317
[pi-merge]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/config.ts#L1084-L1141
[pi-shallow]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/agent-plugin-provenance.ts#L27-L35
[pi-native-merge]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/config.ts#L631-L641
[pi-disabled]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/types.ts#L529-L536
[pi-init]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/init.ts#L162-L174
[pi-trust]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/project-server-trust.ts#L265-L305
[pi-reload]: https://github.com/nicobailon/pi-mcp-adapter/blob/5397dabc0f8eba1c7804baaf092e4c2cf0cc0130/index.ts#L2256-L2259
[vsc-discovery]: https://github.com/microsoft/vscode/blob/b171a702a976feda601dbe6ae3e80935644898be/src/vs/workbench/contrib/mcp/common/discovery/workspaceDotMcpDiscovery.ts#L23-L141
[vsc-root-parser]: https://github.com/microsoft/vscode/blob/b171a702a976feda601dbe6ae3e80935644898be/src/vs/platform/mcp/common/mcpWorkspaceConfiguration.ts#L85-L107
[vsc-copilot]: https://github.com/microsoft/vscode/blob/b171a702a976feda601dbe6ae3e80935644898be/src/vs/platform/mcp/common/mcpCopilotConfiguration.ts#L50-L56
[vsc-normalizer]: https://github.com/microsoft/vscode/blob/b171a702a976feda601dbe6ae3e80935644898be/src/vs/platform/agentPlugins/common/pluginParsers.ts#L549-L598
[vsc-conversion]: https://github.com/microsoft/vscode/blob/b171a702a976feda601dbe6ae3e80935644898be/src/vs/workbench/contrib/mcp/common/discovery/nativeMcpDiscoveryAdapters.ts#L25-L75
[vsc-install]: https://github.com/microsoft/vscode/blob/b171a702a976feda601dbe6ae3e80935644898be/src/vs/platform/mcp/common/mcpWorkspaceConfiguration.ts#L21-L69

### Additional reference and current Codex constraints

- [Claude Code's documented scope precedence](https://code.claude.com/docs/en/mcp#scope-hierarchy-and-precedence)
  selects a complete same-name server definition rather than merging fields.
  Its [variable contract](https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson)
  supports `${VAR}` and `${VAR:-default}` in command, args, env, URL and
  headers. Empty counts as set. Missing variables can remain literal with a
  warning; this differs from the adapter. These are documented behaviors,
  not a runtime source audit.
- Roo Code commit `b867ec9145750d0ae1ff7f02d35406e9bf2a0b16` supplies another
  implementation reference: its [server schema and validation](https://github.com/RooCodeInc/Roo-Code/blob/b867ec9145750d0ae1ff7f02d35406e9bf2a0b16/src/services/mcp/McpHub.ts#L60-L139)
  and [transport checks](https://github.com/RooCodeInc/Roo-Code/blob/b867ec9145750d0ae1ff7f02d35406e9bf2a0b16/src/services/mcp/McpHub.ts#L201-L237)
  distinguish stdio, SSE and Streamable HTTP. Its generic `timeout` is in
  seconds, while [Claude's MCP timeout documentation](https://code.claude.com/docs/en/mcp#time-limits-on-mcp-tool-calls)
  documents a per-server `timeout` in milliseconds. That field cannot be
  mapped uniformly just because its spelling matches.
- In this Codex checkout, `config/src/mcp_types.rs` defines only stdio and
  Streamable HTTP config transports. `codex-mcp/src/agent_plugin_config.rs`
  explicitly rejects Agent Plugins legacy SSE. Native plugin parsing in
  `codex-mcp/src/plugin_config.rs` does not implement the common `headers`
  spelling or generic `${VAR}` expansion. Directly using it would therefore
  not meet the compatibility goal.
- `config/src/merge.rs` recursively merges TOML tables today. Changing every
  MCP entry to atomic replacement would change native configuration behavior,
  including control-only overrides. JSON compatibility needs an explicit
  boundary rather than an incidental change to all existing TOML merges.

## Confirmed compatibility target

Date: 2026-11-11. Status: **confirmed by the user and implemented in the working tree**.
This section records the agreed observable contract. The implementation and
verification scope are described above and below.

Intent: an existing project `.mcp.json` used with common coding agents should
be usable by Codex directly, with its common launch, environment and
authentication settings taking effect, without importing or rewriting it
into TOML. The target is a documented interoperable subset, not duplication
of every vendor's runtime or private settings.

| Area | Confirmed contract |
| --- | --- |
| Discovery | Read `.mcp.json` from cwd through the existing Codex project-root boundary, inclusive. No `.codex` directory is required. Nested definitions nearer cwd take precedence. Existing project-root markers and worktree handling apply; without a detected marker, scope defaults to cwd. |
| Document | Accept `mcpServers` and Copilot's bare server map. Tolerate BOM, comments and trailing commas. Wrapped documents can carry metadata such as `$schema`; a malformed wrapper must not be reinterpreted as a server named `mcpServers`. |
| Stdio | Support `command`, string-array `args`, string-map `env` and optional `cwd`. Recognize absent type, `stdio`, and Copilot's `local`. Reject conflicting command/URL declarations. |
| HTTP | Support `url`, `headers`, `type: "http"`, `streamable-http` and `streamable_http`; a URL-only entry can infer HTTP. Keep Codex's existing OAuth/login flow available. Common headers must actually reach requests. |
| Variables | Expand `${VAR}` and `${VAR:-default}` in command, args, env values, cwd, URL and headers. Use the environment of the host executing or connecting to that server. Empty counts as set; only unset uses the default. Intentional divergence from Claude: an unset reference without a default disables that server with a diagnostic instead of sending a literal placeholder or an empty credential. |
| Paths | Default stdio cwd to the declaring JSON file's directory. Resolve an explicit relative cwd against that directory. Relative command paths and script arguments retain normal child-process working-directory semantics; bare executables use PATH. This deliberately gives an ancestor declaration stable behavior when Codex starts in a nested directory. |
| Duplicate JSON servers | Merge by name; a higher-priority complete JSON definition replaces the lower-priority definition as a whole, avoiding mixed transports or inherited credentials from another endpoint. A disabled-only entry can suppress an inherited server. |
| Native configuration | Same-directory `.codex/config.toml` is above `.mcp.json`, and project JSON is above user defaults; nearer directories win, with session overrides and enforced requirements retaining their authority. Keep existing TOML-only merge behavior. A native complete transport declaration replaces a JSON declaration, while native control-only overrides such as `enabled = false` and tool policies can still apply to it. |
| Disabled entries | Honor `disabled: true` and `enabled: false`; disabling wins if both flags are present. Do not start a disabled definition or fall back to a same-name enabled definition from a lower source. |
| Errors and unsupported fields | Report source file, server name and field without resolved secret values. Invalid servers do not discard valid siblings. Invalid JSON skips that file with a visible warning. An invalid higher-priority definition must not silently activate a lower-priority same-name definition. Metadata may be ignored; unsupported execution/authentication settings need diagnostics. Vendor permission fields such as `autoApprove`/`alwaysAllow` do not grant Codex permissions. |
| Ambiguous vendor settings | Do not guess units for generic `timeout`, or assume all clients' OAuth/helper settings are interchangeable. Document supported mappings; diagnose unsupported behavior-affecting fields. Existing Codex settings with explicit names/units remain the unambiguous override route. |
| User-visible behavior | CLI/TUI and app-server consumers of project configuration use the same effective server definitions. `codex mcp list/get` agree with the runtime. Refresh paths reread JSON; restart/new-session behavior is required. Automatic file watching is a separate scope choice. |
| Trust | Apply Codex's project trust, configuration restrictions and managed MCP requirements to JSON-origin servers as well. Reading/interpolating a config is not authority to run helper commands before trust. |

### Transport scope

The user explicitly excluded legacy SSE from this implementation. An entry
with `type: "sse"` must produce a warning and be skipped; other servers
continue loading. Do not infer HTTP for that entry, attempt an SSE connection,
fail the whole file, or fall back to a same-name lower-priority definition.
The target also does not promise WebSocket, in-process SDK, or Unix-socket
servers; each requires a separate runtime capability.

Other clients' global files and private project paths are reference material,
not additional auto-discovery targets in this proposal. Project JSON remains
the shared input; write-back commands and vendor settings migration are
separate features.

### Acceptance examples

Use synthetic fixtures, not user credentials. Observable requirements include:

1. A root `mcpServers` stdio entry is discovered from a subdirectory without
   any `.codex/config.toml`; relative scripts run from its declared base.
2. A remote HTTP entry receives a static header and an interpolated bearer
   header, including a default-valued URL. Diagnostics do not reveal values.
3. Omitted stdio type, `local`, and HTTP aliases normalize consistently;
   command plus URL and unsupported transports are diagnosed. An SSE entry
   produces a warning, is not connected, and does not discard valid siblings.
4. Nested JSON, user defaults, native complete definitions, native
   control-only overrides and session overrides follow the documented order.
5. Switching a same-name endpoint or transport does not inherit another
   declaration's args, headers or credentials.
6. Disabled entries, malformed server entries, malformed files and missing
   environment variables have isolated, visible outcomes without fallback
   to an unintended lower-priority server.
7. Unknown/untrusted projects do not launch JSON-origin processes; existing
   managed requirements still restrict them.
8. Listing and runtime agree, and a new session or supported config refresh
   observes JSON edits without a migration step.

The target-definition step changed documentation only. The implementation
adds `jsonc-parser 0.34.0` with its `serde` feature, explicitly approved by the
user; the Cargo lock diff preserves existing package versions and unrelated
dependencies. Compiling checks follow `AGENTS.override.md` and the remote-dev
instructions.

## Implementation verification

Verified: 2026-11-11 on `tyanyang-any9.devcloud.woa.com`, in
`/data/workspace/codex`, using the personal remote-dev synchronization wrapper.
All changes were authored locally. No local compilation/test execution,
installation of a replacement Codex CLI, commit or push was performed.

| Check | Result |
| --- | --- |
| `python3 .cache/remote-dev/remote-dev.py test -p codex-config --lib` | 421 passed, including 19 new parser/loader/merge tests. Nextest run `398c57ce-eb7d-41d6-ae15-0c7462c39b59`. |
| `python3 .cache/remote-dev/remote-dev.py test -p codex-cli --test mcp_list` | 8 passed, including the new subprocess test for project discovery, list/get agreement, variables, SSE warnings and valid JSON stdout. Nextest run `c71ec98f-e46f-4241-b8cd-26e91c28e9d1`. |
| `python3 .cache/remote-dev/remote-dev.py exec -- cargo clippy --manifest-path codex-rs/Cargo.toml -p codex-config --all-targets -- -D warnings` | Passed. |
| `python3 .cache/remote-dev/remote-dev.py exec -- cargo fmt --manifest-path codex-rs/Cargo.toml --check -p codex-config -p codex-cli` | Passed. Stable rustfmt reports the repository's documented `imports_granularity` nightly-only option warning. |
| `git diff --check` | Passed locally. |
| Cargo lock scope audit against `HEAD` | Only `jsonc-parser` was added; only `codex-config`'s dependency list changed among existing package entries. Existing versions, checksums and unrelated dependencies are preserved. |

The CLI was built and exercised on the remote Linux host. Its first cold test
build took about 9 minutes; the subsequent complete `mcp_list` run rebuilt in
2.48 seconds and ran in 0.343 seconds. The existing unrelated
`tui/src/chatwidget/rate_limits.rs:328` unused-variable warning remains.

Tests use isolated temporary projects and synthetic values. The config tests
cover JSONC/BOM/bare maps, aliases, headers and OAuth-field normalization,
variable defaults and empty values, missing variables, source-relative cwd,
native controls/complete replacements, credential/transport isolation,
executor-local projections, invalid entries/files, untrusted projects,
project boundaries, no-marker cwd scope and reload by rebuilding config.
The subprocess test exercises the built CLI; it does not connect to real
third-party MCP servers. Windows/macOS runtime behavior, live OAuth against a
third-party service, and Bazel builds were not verified in this change.
