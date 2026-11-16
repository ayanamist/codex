# Skill invocation policy compatibility

Date: 2026-11-10. Scope: this fork, based on `87c8104661`, workspace version
`0.167.0`. Community status below was checked using the GitHub API on that date.

## Contract

Skills can declare `disable-model-invocation` as an optional YAML boolean in
`SKILL.md` frontmatter. The resolved policy follows field-level precedence:

| `agents/openai.yaml` `policy.allow_implicit_invocation` | `SKILL.md` `disable-model-invocation` | Implicit invocation |
| --- | --- | --- |
| `true` | Any value or absent | Allowed |
| `false` | Any value or absent | Disabled |
| Absent | `true` | Disabled |
| Absent | `false` | Allowed |
| Absent | Absent | Allowed (existing default) |

Fallback applies when `agents/openai.yaml` is missing, has no `policy`, or has a
policy without `allow_implicit_invocation`. Existing `products`, dependencies,
and interface metadata are preserved. Explicit invocation uses the existing
selection path. This change resolves policy during loading; it adds no new
prompt instructions or user interface.

The shared frontmatter parser rejects non-boolean values. As with other optional
boolean metadata, YAML `null` is treated as unset. Invalid or unreadable optional
`agents/openai.yaml` retains the existing ignore-and-warn behavior; the resulting
missing policy also permits the frontmatter fallback.

## Implementation evidence

- `codex-rs/skills/src/parser.rs`: parses the optional field and resolves policy
  without replacing an explicitly configured invocation value or other fields.
- `codex-rs/ext/skills/src/loader/host.rs`: resolves host skill policy.
- `codex-rs/ext/skills/src/loader/environment.rs`: resolves both direct
  environment loading and V1 capability discovery bundles.
- `codex-rs/exec-server/src/discoverV2/capability_discoveries.rs`: resolves V2
  discovery for standalone and plugin skills before returning metadata.

Release coverage was corrected on 2026-11-10 after auditing `17a0203a0b`: the
workflow now builds and packages the fork's standalone `codex-exec-server` along
with `codex`. The earlier CLI-only overlay left the standalone helper on the
upstream implementation, so DiscoveryV2 callers missed the executor-side
fallback. Packaging tests verify the replaced executor, and CI checks its fork
version; runtime policy verification of the complete release remains separate.
See the [executor packaging fix](release-management.md#standalone-executor-build-and-packaging-fix).

## Local enablement by name

Checked: 2026-11-14, checkout `b544f00e62`, workspace version `0.169.0`.
Scope: local skill enablement configuration, separate from the invocation-policy
compatibility change above.

Codex supports an external enablement override in the user config
(`$CODEX_HOME/config.toml`, normally `~/.codex/config.toml`):

```toml
[[skills.config]]
name = "research"
enabled = false
```

No skill-file change is required. Set `enabled = true`, or remove the disabling
entry when no other matching rule disables it, to restore enablement. Restart
Codex after editing the configuration.

- `name` matches the exact resolved skill name, including case. It applies to
  every discovered skill with that name. Plugin names can include a namespace,
  for example `sample:sample-search`; use the name in Codex's skill catalog.
- Alternatively, `path` selects one absolute `SKILL.md` path. Each entry must
  have exactly one of `name` or `path`; entries with both or neither are ignored.
- Rules apply in order, with the last matching rule winning. A later path rule
  can re-enable one copy disabled by name, and a later name rule can override
  a path rule.
- At this revision, individual skill rules are read only from `User` and
  `SessionFlags` configuration layers. Project `.codex/config.toml` entries
  under `skills.config` are ignored. The separate `skills.bundled.enabled`
  setting uses the effective configuration and has different scope behavior.
- `enabled` controls skill availability. The local per-skill schema has no
  `allow_implicit_invocation` override: keeping a skill available while disabling
  automatic invocation still uses the skill's invocation policy described above.
  Setting `enabled = true` does not change that policy.

Evidence: `codex-rs/config/src/skills_config.rs` defines the selectors, ordered
matching, and configuration-layer filter; `skills_config_tests.rs` covers name
selectors and mixed-selector precedence. The host service resolves these rules
against discovered names and paths in
`codex-rs/ext/skills/src/host_service.rs`; its test
`skills_for_config_disables_plugin_skills_by_name` covers a namespaced plugin.
`codex-rs/core/src/config/edit_tests.rs` also covers persisting a name selector.
The [official skills guide](https://learn.chatgpt.com/docs/build-skills#enable-or-disable-local-codex-skills)
documents user-config overrides, name matching, last-match precedence, and restart.

Verification was source/schema/test inspection plus the current official guide;
these tests were not executed and no local user configuration was changed.
To locate the contracts again from the repository root:

```bash
rg -n 'pub struct SkillConfig|resolve_disabled_paths|ConfigLayerSource::User|skill_config_rule_selector' codex-rs/config/src/skills_config.rs
rg -n 'preserves_name_selectors|later_name_rule|later_path_rule' codex-rs/config/src/skills_config_tests.rs
rg -n 'skills_for_config_disables_plugin_skills_by_name' codex-rs/ext/skills/src/host_service_tests.rs
rg -n 'set_skill_config_writes_name_selector_entry' codex-rs/core/src/config/edit_tests.rs
```

## Global and per-workspace policy overrides

Implemented: 2026-11-16, workspace version `0.169.0`, on checkout `0c8093a5a7`.
Scope: local skill rules in the global user configuration, with workspace rules
under the existing `projects` entries. This extends the 2026-11-14 enablement-only
contract above; no skill-file edits are required.

```toml
# Global defaults for a skill, selected by its resolved catalog name.
[[skills.config]]
name = "research"
policy = { allow_implicit_invocation = false, products = ["codex"] }

# Add rules to an existing workspace entry; keep its current trust setting.
[projects."/absolute/path/to/project"]
trust_level = "trusted"
skills.config = [
  { name = "research", policy = { allow_implicit_invocation = true } },
  { name = "code-review", enabled = false },
]
```

The workspace example re-enables automatic invocation of `research`, retaining
its global `products = ["codex"]` restriction. `enabled` remains separate from
`policy`: disabling automatic invocation keeps the skill enabled for explicit
selection, while `enabled = false` disables its availability.

Rules merge **per field**, in this order:

1. The skill's resolved declaration, including the frontmatter fallback above.
2. Global `skills.config` rules from user configuration layers.
3. Rules from the selected workspace's `skills.config`.
4. Session `skills.config` overrides.

Later matching rules win only for fields they explicitly set. Omitting
`enabled`, `policy`, or an individual policy field preserves the earlier value.
An empty `policy = {}` changes nothing. `products` replaces the whole earlier
list; `products = []` removes the skill's product restriction, following the
existing skill policy semantics. Supported product values are `codex`,
`chatgpt`, and `atlas`. Invocation and product restrictions are independent:
`enabled = true` does not implicitly change either of them.

Selectors retain their existing contract: exactly one of `name` and absolute
`path`, exact case-sensitive resolved names (including plugin namespaces), and
ordered name/path matching. Repeated selectors remain in order so a policy-only
entry cannot erase an earlier enablement or product decision. Workspace rules
for the same project key also retain field inheritance across user/profile and
session layers.

Workspace selection reuses the current cwd/canonical-path/repository-root
lookup. A matching cwd entry takes precedence over the repository entry as a
whole, including when that cwd entry contains no skill rules. There is no
arbitrary parent-directory or nested-project inheritance. Git subdirectories
can use the repository's existing project entry. These overrides are read from
user and session configuration; project-local `.codex/config.toml` skill rules
remain ignored. Trust selection itself is unchanged. Restart Codex after
changing the configuration.

Implementation evidence:

- `config/src/skills_config.rs` (under `codex-rs/`) parses optional fields,
  resolves ordered scopes, selects the existing project key, and applies
  field-level policy overrides. `ProjectConfig` adds only optional skill rules.
- `ext/skills/src/loader/host_merge.rs` and `loader/environment.rs` apply policy
  after namespacing and before product filtering. The executor provider covers
  direct filesystem scans, V1 manifest bundles, and V2 metadata inventories.
  No override is written back to executor discovery or source files.
- `core-plugins/src/loader.rs` retains raw inventories until effective policy is
  available, then applies product filtering and native/migrated-command
  precedence. Shared parsed snapshots retain the source's original policy.
- Host, executor (all three discovery routes), and plugin cache identities
  include the effective rules. The host snapshot carries the current workspace's
  rules into executor catalog preparation.
- `core/src/config/edit.rs` retains policy when toggling skills, including
  inline arrays and repeated selectors. Role files keep their existing
  disable-only authority: they cannot replace inherited parent skill policy.
  `core/config.schema.json` is generated from the updated configuration types.

Coverage is for local configuration applied to host/executor-owned skills,
including namespaced plugin skills. A local skill policy override does not
change plugin-level marketplace installation/product restrictions, the frozen
Cloud skill provider, or an executor's own configuration. Foreign-path workspace
support remains limited by the existing native-cwd loader contract.

Verification commands follow the repository's remote build convention, from the
repository root:

```bash
python3 .cache/remote-dev/remote-dev.py test -p codex-config -p codex-skills-extension -p codex-core-plugins -p codex-skills --lib --offline -E 'package(codex-config) & (test(skills_config) | test(project_trust) | test(deserialize_skill)) | package(codex-skills-extension) & (test(loader::) | test(host_service) | test(provider::) | test(policy_cache)) | package(codex-core-plugins) & (test(loader) | test(plugin_cache_identity)) | package(codex-skills)'
python3 .cache/remote-dev/remote-dev.py test -p codex-skills-extension --test executor_file_system_authority --test skills_extension --offline -E 'test(executor_discovery_routes_produce_equivalent_catalog_metadata) | test(v2_)'
python3 .cache/remote-dev/remote-dev.py test -p codex-skills-extension --lib --test executor_file_system_authority --test skills_extension --offline -E 'test(loader::environment) | test(policy_cache) | test(executor_discovery_routes_produce_equivalent_catalog_metadata) | test(v2_)'
python3 .cache/remote-dev/remote-dev.py test -p codex-core --lib --offline -E 'test(config::edit::tests::) | test(apply_role_skills_config_disables_skill_for_spawned_agent)'
python3 .cache/remote-dev/remote-dev.py check -p codex-cli -p codex-app-server -p codex-exec-server-cli --all-targets --offline
python3 .cache/remote-dev/remote-dev.py exec -- cargo clippy --no-deps --offline --manifest-path codex-rs/Cargo.toml -p codex-config -p codex-skills-extension -p codex-core-plugins -p codex-core --lib
python3 .cache/remote-dev/remote-dev.py exec -- cargo run --offline --manifest-path codex-rs/Cargo.toml -p codex-config-schema --bin codex-write-config-schema -- --out /tmp/codex-skill-policy.schema.json
```

Verification results on 2026-11-16 (remote Linux, Rust 1.95.0):

- 170 selected configuration, skill, host loader, plugin, and cache unit tests
  passed; 13 executor integration tests passed; 52 core configuration-edit and
  role-authority tests passed. A final 21-test environment-loader/executor/cache
  recheck also passed. These are focused runs, not the full workspace suite.
- CLI, app-server, and standalone executor `--all-targets` checks passed. The
  unchanged TUI source emits an unused-variable warning for
  `should_warn_about_rate_limit_usage` at `tui/src/chatwidget/rate_limits.rs:350`.
- Affected-library Clippy passed with `--no-deps`; the final config/skill/plugin
  library run emitted no warnings. Clippy without `--no-deps` is blocked by the
  unchanged `expect()` at `linux-sandbox/src/linux_run_main.rs:829`, under the
  workspace's `clippy::expect_used` deny rule. The unchanged build-info library
  also emits a `type_complexity` warning. Neither file was modified for this task.
- The generated schema was copied back from the remote generator; the TOML
  examples parse successfully. Remote Rust 1.95.0 formatting checks and local
  `git diff --check` passed.
- Missing locked Cargo dependencies were downloaded with user approval. A
  comparison of all 1,311 external lock entries confirmed no external package
  version, source, or checksum changes; only two internal workspace dependency
  edges were added locally.

No full CLI interaction, release build, macOS execution, or Windows execution
was performed.

## Community evidence

- [openai/codex#29989 — Support disable-model-invocation in SKILL.md](https://github.com/openai/codex/issues/29989)
  is open. It requests this exact compatibility behavior, including precedence
  for `agents/openai.yaml`, because portable skills otherwise require an extra
  Codex-specific file.
- [openai/codex#10585 — Skills with implicit invocation disabled while only allowing explicit invocation](https://github.com/openai/codex/issues/10585)
  is closed as completed. It covers the underlying explicit-only capability,
  rather than the frontmatter fallback.
- [openai/codex#11244 — add SkillPolicy and allow_implicit_invocation](https://github.com/openai/codex/pull/11244)
  merged on 2026-02-10. It added the existing `agents/openai.yaml` policy.
- [openai/codex#36976 — Honor explicit-only orchestrator skills](https://github.com/openai/codex/pull/36976)
  merged on 2026-08-04. It concerns hiding explicit-only orchestrator skills from
  model-visible catalogs while preserving direct invocation, not parsing this
  frontmatter field.
- [kkkiio/agconf#3 — Generate agents/openai.yaml for disable-model-invocation skills](https://github.com/kkkiio/agconf/pull/3)
  merged on 2026-10-28. This community workaround generates the Codex policy
  during installation and preserves a source-provided metadata file verbatim.

Searches of `openai/codex` PRs for the exact `disable-model-invocation` field
returned no matches. A broader search for skill model invocation and the linked
issue's cross-reference timeline found related work, but no upstream PR
implementing this fallback. Search results cannot rule out an unlinked or
differently worded PR.

## Verification

Run from `codex-rs/` with the repository's Rust 1.95.0 toolchain:

```bash
cargo test --offline -p codex-skills --lib
cargo test --offline -p codex-skills-extension --lib loader::
cargo test --offline -p codex-exec-server --lib discovery_invocation_policy_falls_back_to_frontmatter
```

Parser tests cover both frontmatter values, missing flags, explicit metadata
overrides in both directions, product preservation, and invalid field types.
Loader tests cover absent metadata files, absent policy or invocation fields,
explicit overrides, and parity between direct and bundled environment loading.
The V2 test checks standalone and plugin discovery.

Results on 2026-11-10: 56 `codex-skills` unit tests, 43 skill loader tests, and
the V2 discovery test passed (100 tests total). Formatting checks for all changed
Rust files and `git diff --check` passed. The toolchain emits the repository's
documented warning about nightly-only `imports_granularity`; formatting still
passes. All Cargo commands used locally cached dependencies in offline mode.
Cargo's incidental lockfile changes to workspace package versions were removed.
No full CLI build or interactive session was run.

To refresh the primary community lookup:

```bash
gh api repos/openai/codex/issues/29989
gh api 'search/issues?q=repo%3Aopenai%2Fcodex%20is%3Apr%20%22disable-model-invocation%22'
gh api repos/openai/codex/issues/29989/timeline --paginate
gh api repos/kkkiio/agconf/pulls/3
```
