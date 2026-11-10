# Linux sandbox empty mount targets

Scope: Linux bubblewrap filesystem sandboxing in the `ayanamist/codex` fork.
Investigated on 2026-11-10 against `e3c1d7dacb1da3ccb6ec869a5c749cb3b714fa1c`
(workspace version `0.167.0`) plus the accompanying changes.
Keywords: empty directory, `.agents`, `.aws`, `.codex`, `.git`, bubblewrap,
bwrap, SIGKILL, synthetic mount target, inode, cleanup.

## Known issue and source evidence

Upstream [issue #31599](https://github.com/openai/codex/issues/31599) was open
when checked through the GitHub API on 2026-11-10. Its reports describe empty
metadata directories surviving helper termination. The
[2026-10-30 report](https://github.com/openai/codex/issues/31599#issuecomment-6522862718)
explicitly includes `.agents`, `.codex`, and `.aws` in project roots on version
`0.165.0`. The older [issue #18043](https://github.com/openai/codex/issues/18043)
describes an empty `.codex` file and is closed as a duplicate; that closure
does not establish that the directory leak was fixed.

The local source confirms the mechanism:

- [`permissions.rs`](../../codex-rs/protocol/src/permissions.rs) protects `.git`,
  `.agents`, `.codex`, and `.aws` under workspace-write project roots. Other
  writable roots can inherit metadata protection too.
- [`bwrap.rs`](../../codex-rs/linux-sandbox/src/bwrap.rs) uses an empty read-only
  tmpfs to protect a missing metadata directory. Bubblewrap needs a mount point;
  when its parent is a writable host bind mount, that empty directory exists on
  the host too. Missing ordinary read-only subpaths can similarly create empty
  file mount targets.
- [`linux_run_main.rs`](../../codex-rs/linux-sandbox/src/linux_run_main.rs)
  registers these targets and runs bubblewrap under a supervising helper. Normal
  completion removes empty synthetic targets after the last active owner exits.
  SIGKILL, OOM, or a crash can prevent that cleanup.
- Before this change, later registration recognized another active synthetic
  owner but discarded dead PID markers. It then preserved the leaked object as
  pre-existing, so another normal command did not reclaim it.

These findings explain a reproducible class of leaks. They do not establish
which termination event created any particular pre-existing directory on the
user's machine. No historical session logs or unrelated directories were scanned.

## Recovery contract

The helper now attempts to create missing mount targets before launching
bubblewrap, using exclusive creation for files. When creation succeeds it saves
the device number, inode, and nanosecond change time in `identity.json` next to
the per-process markers. The identity is written through a temporary file and
rename, so killing the writer cannot expose a partial JSON record.

When no active owner remains, a subsequent run can reclaim a recorded object
even if that run originally observed it as pre-existing. Its current identity
must match the saved identity. Real pre-existing paths, replaced paths, and
modified paths are preserved. File removal also requires an empty regular file,
even when timestamps are too coarse to distinguish a write. Directory removal
remains non-recursive; non-empty directories are never recursively deleted. Existing PID markers and legacy
normal-cleanup behavior remain supported when no identity record exists.

A stale PID marker alone is not sufficient proof of ownership: the old helper
might have died before creating anything, or a user might have replaced the
original object. This is also explained in the
[2026-09-24 upstream comment](https://github.com/openai/codex/issues/31599#issuecomment-5806176380).

## Limits

- This repairs recovery after interruption, not host mount-point creation.
  Empty placeholders can still be visible while a sandboxed command runs.
- Recovery requires another sandbox run covering the same protected path. There
  is no background sweep of arbitrary directories.
- Old leaks without identity records are preserved. A kill between creation and
  recording can also leave an unrecorded target. Automatically removing these
  would risk deleting a real user directory.
- PID reuse can delay cleanup because the existing liveness check uses PID
  existence. It does not weaken the identity requirement for recorded targets.
- No installed CLI, daemon, or published release is replaced by these source
  changes. The normal CLI creates its Linux sandbox alias through
  [`arg0`](../../codex-rs/arg0/src/lib.rs), which dispatches back into the CLI's
  compiled `codex-linux-sandbox` implementation. A separately configured sandbox
  executable must also contain this change to benefit from it.

## Verification

The original regression drives the real workspace-write argument builder and
registration/cleanup functions. It leaves markers owned by a killed process,
then constructs a second sandbox over the same workspace. Before the fix, the
test failed with all four directories remaining:

```text
leaked mount points: [".git", ".agents", ".codex", ".aws"]
```

Commands from `codex-rs`:

```sh
cargo test --offline -p codex-linux-sandbox --lib cleanup_synthetic_mount_targets -- --nocapture
cargo test --offline -p codex-linux-sandbox --lib
cargo test --offline -p codex-linux-sandbox --test all sandbox_reclaims_metadata_mount_targets_after_helper_is_killed -- --nocapture
cargo test --offline -p codex-linux-sandbox --test all metadata -- --nocapture
```

Results: all 171 unit tests passed, including 13 cleanup cases. The real helper
SIGKILL/recovery integration test passed: it first verifies normal cleanup, kills
a running helper, confirms all four empty directories remain, then verifies that
a fresh helper removes them while preserving an ordinary file from the command.

The broader `metadata` integration filter passed 11 of 12 tests, without skips.
`root_metadata_symlinks_cannot_reopen_approved_denials` failed with `bubblewrap is
unavailable` from the unchanged launcher. Its fixture copies only the sandbox
helper into a new root and supplies no adjacent bundled bwrap. The approved
policy and nested root environment leave no eligible system bwrap candidate;
the test therefore fails before its intended denial assertions. This is a
validation limitation; this change does not modify its fixture or launcher
selection. The passing cases include metadata write denials, nested and
symlinked writable roots, resolved gitdirs, parent repository discovery, and the
new interrupted-helper recovery test.

`rustfmt --check` on the three changed Rust files and `git diff --check` also
passed. Stable rustfmt printed the repository's existing warning that the
`imports_granularity` option requires nightly.

Run these outside an enclosing filesystem sandbox that remaps ownership of the
real app-server socket directory: that remapping triggers its unrelated
owner/mode validation before the argument-builder regression can reach cleanup.
The first local run also required unpacking cached `test-case 3.3.1` dependencies;
the user approved completing the development dependencies before that continued.
