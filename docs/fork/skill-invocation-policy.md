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
