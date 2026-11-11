# CLI installation and update sources

## Installation documentation review: 2026-11-11

Scope: installation entry points for `ayanamist/codex` on `fork-release`,
reviewed against `74593b7469`, workspace version `0.167.1`.
Keywords: first install, README, migration, platform support, PATH, release assets.

The installers already selected the fork, but the root README still linked to
the official bootstrap scripts, npm package, Homebrew cask, and upstream release
assets. `docs/install.md` also cloned the upstream repository and described
upstream platforms and DotSlash assets. The README and
[installation guide](../install.md) now document fork bootstrap URLs, supported
release targets, explicit release selection, install paths, migration, and updates.

A read-only GitHub API check on 2026-11-11 found the latest stable release
[`rust-v0.167.0-fork.aeae161d`](https://github.com/ayanamist/codex/releases/tag/rust-v0.167.0-fork.aeae161d),
published on 2026-11-10. Its assets include both installers, the package checksum
manifest, and exactly three platform packages: Linux x86_64 GNU, macOS ARM64,
and Windows x64. This matches the current release workflow matrix. The Linux
glibc 2.38 floor follows the build contract in [release management](release-management.md).
The published version differs from the local workspace's upstream base; `latest`
selects a published release, not the local checkout.

Verification uses current installer source, the release workflow, GitHub release
metadata, and `git diff --check`. This documentation change does not run an
installer, replace a local binary, or establish runtime compatibility on those
platforms. Recheck release availability with:

```sh
gh api repos/ayanamist/codex/releases/latest --jq '{tag_name, html_url, published_at, assets: [.assets[].name]}'
git diff --check
```

## Implementation review: 2026-11-10

Scope: the `ayanamist/codex` fork, standalone CLI updates, startup update checks,
and managed daemon installer downloads. Reviewed on 2026-11-10 against
`14e06796d3420312ca48164a7e4573330f6f4d20` (workspace version `0.167.0`)
plus the accompanying fork changes.
Keywords: `codex update`, fork, GitHub Releases, standalone installer, version cache.
Commit-based version acceptance was updated on 2026-11-10 against
`5d0840ed69be4451d0a3dba14a26e1a833629b5f` plus local changes; keywords:
commit hash, SemVer suffix, latest, legacy numbered versions.

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

The fork release pipeline generates versions such as
`rust-v0.167.0-fork.5d0840ed`, using the source commit's first eight characters.
Its installers accept arbitrary legal SemVer suffixes without fixing names or
lengths. Update checks use the numeric upstream base and the identity from
GitHub `latest`; hashes have no lexical precedence. Historical numbered releases
remain installable. GitHub Release metadata determines stable/prerelease status.
Code pushes to `fork-release` derive the tag and publish automatically, while
documentation-only pushes are ignored. See [release management](release-management.md)
for rebuilding the fork CLI and standalone executor while reusing pinned upstream helpers.
Linux standalone installs select the fork's `*-unknown-linux-gnu` packages,
which support glibc 2.38 and newer; the release workflow validates imported
GLIBC symbol versions across the entire package before publication.

The default channel requires a published stable release with a `rust-v<VERSION>`
tag and the assets produced by
[the release workflow](../../.github/workflows/rust-release.yml): `install.sh`,
`install.ps1`, platform package archives, and `codex-package_SHA256SUMS`.
The installers also retain support for legacy platform npm archive assets.
Prereleases can be installed explicitly with `--release`; they do not become
the default `latest` stable channel.

During the initial 2026-11-10 inspection, `gh api repos/ayanamist/codex/releases/latest` returned HTTP 404,
and the release list returned `[]`. This is a point-in-time observation. Until
an appropriate release exists, the configured bootstrap URLs cannot complete
an online update. Later, [run 42777286813](https://github.com/ayanamist/codex/actions/runs/42777286813)
completed all six builds and release publication successfully; that run predates
the local hash-version changes. This change does not publish a release or replace an already
installed binary; it takes effect after installing a build containing it.
The subsequent read-only check found `rust-v0.167.0-ayanamist.2` as the fork's
non-prerelease `latest`; hash-based versions remain local changes.

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
