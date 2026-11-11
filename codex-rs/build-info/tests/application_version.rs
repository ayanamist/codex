use codex_build_info::BuildInfo;
use codex_build_info::application_version;
use codex_build_info::is_newer_release;

#[test]
fn executable_identity_drives_runtime_versions_and_update_comparisons() {
    const COMMIT: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const VERSION: &str = "0.167.1-fork.aaaaaaaa";
    assert_ne!(env!("CARGO_PKG_VERSION"), "0.167.1-fork.aaaaaaaa");
    BuildInfo::initialize_release(COMMIT, Some(VERSION));
    assert_eq!(application_version(), VERSION);
    assert_eq!(BuildInfo::get().version().to_string(), VERSION);
    assert_eq!(BuildInfo::get().build_commit(), COMMIT);
    assert_eq!(
        is_newer_release(VERSION, application_version()),
        Some(false)
    );
    assert_eq!(
        is_newer_release("0.167.1-fork.bbbbbbbb", application_version()),
        Some(true)
    );

    // Later library initialization cannot replace the executable's identity.
    BuildInfo::initialize("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    assert_eq!(application_version(), VERSION);
    assert_eq!(BuildInfo::get().build_commit(), COMMIT);
}
