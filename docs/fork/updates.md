# CLI update sources

Scope: the `ayanamist/codex` fork, standalone CLI updates, startup update checks,
and managed daemon installer downloads. Reviewed on 2026-11-10 against
`14e06796d3420312ca48164a7e4573330f6f4d20` (workspace version `0.167.0`)
plus the accompanying fork changes.
Keywords: `codex update`, fork, GitHub Releases, standalone installer, version cache.

## Behavior and source evidence

`codex update` does not read a configurable update feed. In
[`run_update_command`](../../codex-rs/cli/src/main.rs), it detects the current
installation method through `codex-install-context` and executes the action from
[`update_action.rs`](../../codex-rs/tui/src/update_action.rs). Debug builds reject the
command, and unrecognized installation layouts require a manual update.

The standalone Unix and Windows actions download these bootstrap installers:

- `https://github.com/ayanamist/codex/releases/latest/download/install.sh`
- `https://github.com/ayanamist/codex/releases/latest/download/install.ps1`

The managed daemon uses the same installer locations in
[`update_loop.rs`](../../codex-rs/app-server-daemon/src/update_loop.rs). Both
installers reset `CODEX_INSTALLER_USE_RELEASES_OPENAI_COM` to `false`
at startup, so an inherited mirror setting cannot select the official
distribution. Callers do not need to set this variable.

The [Unix installer](../../scripts/install/install.sh) and
[Windows installer](../../scripts/install/install.ps1) default to the fork's GitHub
Releases. They resolve `latest` through
`https://api.github.com/repos/ayanamist/codex/releases/latest`, or a requested
version through `/releases/tags/rust-v<VERSION>`. Downloads use release asset
metadata and SHA-256 verification. Constructed GitHub download URLs also point
to `ayanamist/codex`. A failed default GitHub request stops the installation;
it does not fall back to the official distribution. The upstream mirror code
remains in the scripts to keep the fork delta small,
but its environment switch is forcibly disabled.

Startup version checks in [`updates.rs`](../../codex-rs/tui/src/updates.rs) and the
CLI's [`doctor` check](../../codex-rs/cli/src/doctor/updates.rs) query the fork for
all installation methods. The startup check caches metadata in
`$CODEX_HOME/version.json` and refreshes it in the background after 20 hours.
An existing cache can therefore display an old source's version until refreshed.
The command `codex update` itself does not use that cache. Startup update checks
are disabled for debug builds and version `0.0.0` source builds.

Automatic updates through Homebrew, npm, Bun, pnpm, and Vite+ are disabled
because their official packages would replace this fork with the upstream
distribution. `codex update` rejects those installation methods and points to
the fork's standalone installer. Version checks and release notes use the fork
for every installation method. Use the standalone installer to track this fork.
There is no `config.toml` setting for a GitHub repository or installer URL.

## Release contract and limits

The fork release pipeline now publishes numbered versions such as
`rust-v0.167.0-ayanamist.1` as stable GitHub releases. Its installers and update
checks recognize the fork revision. Pushing `fork-release` now allocates the
tag and publishes automatically. See [release management](release-management.md)
for rebuilding only the fork entrypoint while reusing pinned upstream helpers.

The default channel requires a published stable release with a `rust-v<VERSION>`
tag and the assets produced by
[the release workflow](../../.github/workflows/rust-release.yml): `install.sh`,
`install.ps1`, platform package archives, and `codex-package_SHA256SUMS`.
The installers also retain support for legacy platform npm archive assets.
Prereleases can be installed explicitly with `--release`; they do not become
the default `latest` stable channel.

On 2026-11-10, `gh api repos/ayanamist/codex/releases/latest` returned HTTP 404,
and the release list returned `[]`. This is a point-in-time observation. Until
an appropriate release exists, the configured bootstrap URLs cannot complete
an online update. This change does not publish a release or replace an already
installed binary; it takes effect after installing a build containing it.

## Verification

The installer tests use local fixtures, a fake download command, and temporary
installation directories. They cover the default fork channel, digest checks,
explicit versions, download failures, and ignored inherited mirror settings.

```sh
python3 scripts/install/test_install_sh.py
sh -n scripts/install/install.sh
git diff --check -- . ':(exclude)**/*.snap'
cd codex-rs
cargo test --offline -p codex-tui --lib update_action::tests --no-default-features
cargo test --offline -p codex-tui --lib update_prompt::tests --no-default-features
cargo test --offline -p codex-tui --lib update_available_history_cell_snapshot --no-default-features
cargo test --offline -p codex-cli --bin codex daemon_update_tests
cargo test --offline -p codex-cli --bin codex doctor::updates::tests::update_action_labels_install_contexts
```

Results on 2026-11-10: 17 installer tests, 13 focused TUI tests, and 3 CLI tests
passed (33 total). CLI coverage checks that updates run outside the project,
daemon handoff uses the launching executable and propagates failure, and doctor
labels package-manager installs as requiring manual migration. Shell syntax and
source whitespace checks passed. Generated terminal snapshots preserve display
padding. The existing unrelated unused-variable warning in
`tui/src/chatwidget/rate_limits.rs` remains.

Read-only release inspection:

```sh
gh api repos/ayanamist/codex/releases/latest --jq '{tag_name, prerelease, assets: [.assets[].name]}'
gh api 'repos/ayanamist/codex/releases?per_page=3' --jq '[.[] | {tag_name, prerelease, draft}]'
```

Live installation and Windows execution require separate verification; local
fixture tests do not establish release availability or Windows runtime behavior.
