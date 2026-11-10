#[cfg(test)]
use super::*;
#[cfg(test)]
use crate::linux_run_main::install_bwrap_signal_forwarders;
#[cfg(test)]
use crate::linux_run_main::wait_for_bwrap_child;
#[cfg(test)]
use codex_network_proxy::ManagedNetworkSandboxContext;
#[cfg(test)]
use codex_protocol::models::PermissionProfile;
#[cfg(test)]
use codex_protocol::protocol::FileSystemSandboxPolicy;
#[cfg(test)]
use codex_protocol::protocol::NetworkSandboxPolicy;
#[cfg(test)]
use codex_utils_absolute_path::AbsolutePathBuf;
#[cfg(test)]
use pretty_assertions::assert_eq;

fn read_only_permission_profile() -> PermissionProfile {
    PermissionProfile::read_only()
}

fn read_only_file_system_policy() -> FileSystemSandboxPolicy {
    read_only_permission_profile().file_system_sandbox_policy()
}

#[test]
fn detects_proc_mount_invalid_argument_failure() {
    let stderr = "bwrap: Can't mount proc on /newroot/proc: Invalid argument";
    assert!(is_proc_mount_failure(stderr));
}

#[test]
fn detects_proc_mount_operation_not_permitted_failure() {
    let stderr = "bwrap: Can't mount proc on /newroot/proc: Operation not permitted";
    assert!(is_proc_mount_failure(stderr));
}

#[test]
fn detects_proc_mount_permission_denied_failure() {
    let stderr = "bwrap: Can't mount proc on /newroot/proc: Permission denied";
    assert!(is_proc_mount_failure(stderr));
}

#[test]
fn ignores_non_proc_mount_errors() {
    let stderr = "bwrap: Can't bind mount /dev/null: Operation not permitted";
    assert!(!is_proc_mount_failure(stderr));
}

#[test]
fn inserts_bwrap_argv0_before_command_separator() {
    let file_system_sandbox_policy = read_only_file_system_policy();
    let mut argv = build_bwrap_argv(
        vec!["/bin/true".to_string()],
        &file_system_sandbox_policy,
        Path::new("/"),
        Path::new("/"),
        BwrapOptions {
            mount_proc: true,
            network_mode: BwrapNetworkMode::FullAccess,
            ..Default::default()
        },
    )
    .expect("build bwrap argv")
    .args;
    apply_inner_command_argv0_for_launcher(
        &mut argv,
        /*supports_argv0*/ true,
        "/tmp/codex-arg0-session/codex-linux-sandbox".to_string(),
    );
    let separator = argv.iter().position(|arg| arg == "--").unwrap();
    assert_eq!(
        &argv[separator - 2..],
        ["--argv0", "codex-linux-sandbox", "--", "/bin/true"]
    );
}

#[test]
fn rewrites_inner_command_path_when_bwrap_lacks_argv0() {
    let file_system_sandbox_policy = read_only_file_system_policy();
    let mut argv = build_bwrap_argv(
        vec!["/bin/true".to_string()],
        &file_system_sandbox_policy,
        Path::new("/"),
        Path::new("/"),
        BwrapOptions {
            mount_proc: true,
            network_mode: BwrapNetworkMode::FullAccess,
            ..Default::default()
        },
    )
    .expect("build bwrap argv")
    .args;
    apply_inner_command_argv0_for_launcher(
        &mut argv,
        /*supports_argv0*/ false,
        "/tmp/codex-arg0-session/codex-linux-sandbox".to_string(),
    );

    assert!(!argv.iter().any(|arg| arg == "--argv0"));
    assert!(
        argv.windows(2)
            .any(|window| { window == ["--", "/tmp/codex-arg0-session/codex-linux-sandbox"] })
    );
}

#[test]
fn rewrites_bwrap_helper_command_not_nested_user_command_when_current_exe_appears_later() {
    let nested_current_exe = std::env::current_exe()
        .expect("current exe")
        .to_string_lossy()
        .into_owned();
    let mut argv = vec![
        "bwrap".to_string(),
        "--".to_string(),
        "/tmp/helper-symlink".to_string(),
        "--sandbox-policy-cwd".to_string(),
        "/tmp/cwd".to_string(),
        "--".to_string(),
        nested_current_exe.clone(),
        "--codex-run-as-apply-patch".to_string(),
        "patch".to_string(),
    ];

    apply_inner_command_argv0_for_launcher(
        &mut argv,
        /*supports_argv0*/ false,
        "/tmp/argv0-fallback-helper".to_string(),
    );

    assert_eq!(
        argv,
        vec![
            "bwrap".to_string(),
            "--".to_string(),
            "/tmp/argv0-fallback-helper".to_string(),
            "--sandbox-policy-cwd".to_string(),
            "/tmp/cwd".to_string(),
            "--".to_string(),
            nested_current_exe,
            "--codex-run-as-apply-patch".to_string(),
            "patch".to_string(),
        ]
    );
}

#[test]
fn inserts_unshare_net_when_network_isolation_requested() {
    let file_system_sandbox_policy = read_only_file_system_policy();
    let argv = build_bwrap_argv(
        vec!["/bin/true".to_string()],
        &file_system_sandbox_policy,
        Path::new("/"),
        Path::new("/"),
        BwrapOptions {
            mount_proc: true,
            network_mode: BwrapNetworkMode::Isolated,
            ..Default::default()
        },
    )
    .expect("build bwrap argv")
    .args;
    assert!(argv.contains(&"--unshare-net".to_string()));
}

#[test]
fn inserts_unshare_net_when_proxy_only_network_mode_requested() {
    let file_system_sandbox_policy = read_only_file_system_policy();
    let argv = build_bwrap_argv(
        vec!["/bin/true".to_string()],
        &file_system_sandbox_policy,
        Path::new("/"),
        Path::new("/"),
        BwrapOptions {
            mount_proc: true,
            network_mode: BwrapNetworkMode::ProxyOnly,
            ..Default::default()
        },
    )
    .expect("build bwrap argv")
    .args;
    assert!(argv.contains(&"--unshare-net".to_string()));
}

#[test]
fn masks_wsl_interop_with_full_network_and_restricted_filesystem() {
    let argv = build_bwrap_argv(
        vec!["/bin/true".to_string()],
        &read_only_file_system_policy(),
        Path::new("/"),
        Path::new("/"),
        BwrapOptions {
            network_mode: BwrapNetworkMode::FullAccess,
            mask_wsl_interop: true,
            ..Default::default()
        },
    )
    .expect("build bwrap argv")
    .args;

    assert!(argv.windows(2).any(|args| args == ["--tmpfs", "/run/WSL"]));
    assert!(!argv.iter().any(|arg| arg == "--unshare-net"));
}

#[test]
fn masks_inherited_procfs_when_wsl_interop_is_masked_without_fresh_proc() {
    let argv = build_bwrap_argv(
        vec!["/bin/true".to_string()],
        &read_only_file_system_policy(),
        Path::new("/"),
        Path::new("/"),
        BwrapOptions {
            mount_proc: false,
            network_mode: BwrapNetworkMode::FullAccess,
            mask_wsl_interop: true,
            ..Default::default()
        },
    )
    .expect("build bwrap argv")
    .args;

    assert!(argv.windows(2).any(|args| args == ["--tmpfs", "/run/WSL"]));
    assert!(argv.windows(2).any(|args| args == ["--tmpfs", "/proc"]));
    assert!(!argv.windows(2).any(|args| args == ["--proc", "/proc"]));
}

#[test]
fn proxy_only_mode_takes_precedence_over_full_network_policy() {
    let mode = bwrap_network_mode(
        NetworkSandboxPolicy::Enabled,
        /*allow_network_for_proxy*/ true,
    );
    assert_eq!(mode, BwrapNetworkMode::ProxyOnly);
}

#[test]
fn split_only_filesystem_policy_requires_direct_runtime_enforcement() {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let docs = temp_dir.path().join("docs");
    std::fs::create_dir_all(&docs).expect("create docs");
    let docs = AbsolutePathBuf::from_absolute_path(&docs).expect("absolute docs");
    let policy = FileSystemSandboxPolicy::restricted(vec![
        codex_protocol::permissions::FileSystemSandboxEntry {
            path: codex_protocol::permissions::FileSystemPath::Special {
                value: codex_protocol::permissions::FileSystemSpecialPath::project_roots(
                    /*subpath*/ None,
                ),
            },
            access: codex_protocol::permissions::FileSystemAccessMode::Write,
            missing_path_behavior: None,
        },
        codex_protocol::permissions::FileSystemSandboxEntry {
            path: docs.into(),
            access: codex_protocol::permissions::FileSystemAccessMode::Read,
            missing_path_behavior: None,
        },
    ]);

    assert!(
        policy.needs_direct_runtime_enforcement(NetworkSandboxPolicy::Restricted, temp_dir.path(),)
    );
}

#[test]
fn root_write_read_only_carveout_requires_direct_runtime_enforcement() {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let docs = temp_dir.path().join("docs");
    std::fs::create_dir_all(&docs).expect("create docs");
    let docs = AbsolutePathBuf::from_absolute_path(&docs).expect("absolute docs");
    let policy = FileSystemSandboxPolicy::restricted(vec![
        codex_protocol::permissions::FileSystemSandboxEntry {
            path: codex_protocol::permissions::FileSystemPath::Special {
                value: codex_protocol::permissions::FileSystemSpecialPath::Root,
            },
            access: codex_protocol::permissions::FileSystemAccessMode::Write,
            missing_path_behavior: None,
        },
        codex_protocol::permissions::FileSystemSandboxEntry {
            path: docs.into(),
            access: codex_protocol::permissions::FileSystemAccessMode::Read,
            missing_path_behavior: None,
        },
    ]);

    assert!(
        policy.needs_direct_runtime_enforcement(NetworkSandboxPolicy::Restricted, temp_dir.path(),)
    );
}

#[test]
fn managed_proxy_preflight_argv_unshares_network() {
    let mode = bwrap_network_mode(
        NetworkSandboxPolicy::Enabled,
        /*allow_network_for_proxy*/ true,
    );
    let argv = build_preflight_bwrap_argv(BwrapOptions {
        network_mode: mode,
        ..Default::default()
    })
    .expect("build preflight argv")
    .args;
    assert!(argv.iter().any(|arg| arg == "--"));
    assert!(argv.iter().any(|arg| arg == "--unshare-net"));
}

#[test]
fn proc_mount_preflight_does_not_bind_the_full_filesystem() {
    let argv = build_preflight_bwrap_argv(BwrapOptions::default())
        .expect("build preflight argv")
        .args;

    assert!(argv.windows(2).any(|window| window == ["--tmpfs", "/"]));
    assert!(argv.windows(2).any(|window| window == ["--proc", "/proc"]));
    assert!(
        !argv
            .windows(3)
            .any(|window| window == ["--ro-bind", "/", "/"])
    );
    assert!(!argv.windows(3).any(|window| window == ["--bind", "/", "/"]));
}

#[test]
fn proc_mount_preflight_preserves_wsl_masks() {
    let argv = build_preflight_bwrap_argv(BwrapOptions {
        mask_wsl_interop: true,
        mask_wslg_distro: true,
        ..Default::default()
    })
    .expect("build WSL preflight argv")
    .args;

    assert!(argv.windows(2).any(|window| window == ["--proc", "/proc"]));
    assert!(
        argv.windows(2)
            .any(|window| window == ["--tmpfs", WSL_INTEROP_DIR])
    );
    assert!(argv.windows(6).any(|window| {
        window
            == [
                "--perms",
                "000",
                "--tmpfs",
                WSLG_DISTRO_ROOT,
                "--remount-ro",
                WSLG_DISTRO_ROOT,
            ]
    }));
}

#[test]
fn cleanup_synthetic_mount_targets_removes_only_empty_mount_targets() {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let empty_file = temp_dir.path().join(".git");
    let empty_dir = temp_dir.path().join(".agents");
    let non_empty_file = temp_dir.path().join("non-empty");
    let missing_file = temp_dir.path().join(".missing");
    std::fs::write(&empty_file, "").expect("write empty file");
    std::fs::create_dir(&empty_dir).expect("create empty dir");
    std::fs::write(&non_empty_file, "keep").expect("write nonempty file");

    let registrations = register_synthetic_mount_targets(&[
        crate::bwrap::SyntheticMountTarget::missing(&empty_file),
        crate::bwrap::SyntheticMountTarget::missing_empty_directory(&empty_dir),
        crate::bwrap::SyntheticMountTarget::missing(&non_empty_file),
        crate::bwrap::SyntheticMountTarget::missing(&missing_file),
    ]);
    cleanup_synthetic_mount_targets(&registrations);

    assert!(!empty_file.exists());
    assert!(!empty_dir.exists());
    assert_eq!(
        std::fs::read_to_string(&non_empty_file).expect("read nonempty file"),
        "keep"
    );
    assert!(!missing_file.exists());
}

#[test]
fn synthetic_mount_registry_root_is_unique_to_effective_user() {
    let effective_uid = unsafe { libc::geteuid() };
    assert_eq!(
        synthetic_mount_registry_root(),
        std::env::temp_dir()
            .canonicalize()
            .expect("resolve temp directory")
            .join(format!(
                "codex-bwrap-synthetic-mount-targets-{effective_uid}"
            ))
    );
}

#[test]
fn cleanup_synthetic_mount_targets_waits_for_other_active_registrations() {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let empty_dir = temp_dir.path().join(".git");
    std::fs::create_dir(&empty_dir).expect("create empty dir");
    let target = crate::bwrap::SyntheticMountTarget::missing_empty_directory(&empty_dir);

    let registrations = register_synthetic_mount_targets(std::slice::from_ref(&target));
    let active_marker = registrations[0].marker_dir.join("1");
    std::fs::write(&active_marker, "").expect("write active marker");

    cleanup_synthetic_mount_targets(&registrations);
    assert!(empty_dir.exists());

    std::fs::remove_file(active_marker).expect("remove active marker");
    let registrations = register_synthetic_mount_targets(std::slice::from_ref(&target));
    cleanup_synthetic_mount_targets(&registrations);

    assert!(!empty_dir.exists());
}

#[test]
fn cleanup_synthetic_mount_targets_removes_transient_file_after_concurrent_owner_exits() {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let empty_file = temp_dir.path().join(".git");
    let first_target = crate::bwrap::SyntheticMountTarget::missing(&empty_file);

    let first_registrations = register_synthetic_mount_targets(&[first_target]);
    assert!(empty_file.exists(), "registration creates the mount target");
    let active_marker = first_registrations[0].marker_dir.join("1");
    std::fs::write(&active_marker, SYNTHETIC_MOUNT_MARKER_SYNTHETIC).expect("write active marker");
    let metadata = std::fs::symlink_metadata(&empty_file).expect("stat empty file");
    let second_target =
        crate::bwrap::SyntheticMountTarget::existing_empty_file(&empty_file, &metadata);
    let second_registrations = register_synthetic_mount_targets(&[second_target]);

    cleanup_synthetic_mount_targets(&first_registrations);
    assert!(empty_file.exists());

    std::fs::remove_file(active_marker).expect("remove active marker");
    cleanup_synthetic_mount_targets(&second_registrations);

    assert!(!empty_file.exists());
}

#[test]
fn cleanup_synthetic_mount_targets_reclaims_directories_after_owner_is_killed() {
    let workspace = tempfile::TempDir::new().expect("workspace");
    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    for name in [".git", ".agents", ".codex", ".aws"] {
        // Simulate bubblewrap materializing its mount points on the host.
        std::fs::create_dir_all(workspace.path().join(name)).expect("create mount point");
    }
    abandon_synthetic_mount_registrations(&registrations);

    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    cleanup_synthetic_mount_targets(&registrations);

    let remaining: Vec<_> = [".git", ".agents", ".codex", ".aws"]
        .into_iter()
        .filter(|name| workspace.path().join(name).exists())
        .collect();
    assert_eq!(remaining, Vec::<&str>::new(), "leaked mount points");
}

fn workspace_synthetic_mount_targets(path: &Path) -> Vec<crate::bwrap::SyntheticMountTarget> {
    let policy = FileSystemSandboxPolicy::workspace_write(&[], true, true);
    build_bwrap_argv(
        vec!["/bin/true".to_string()],
        &policy,
        path,
        path,
        BwrapOptions::default(),
    )
    .expect("build workspace sandbox")
    .synthetic_mount_targets
}

fn abandon_synthetic_mount_registrations(registrations: &[SyntheticMountTargetRegistration]) {
    let mut owner = std::process::Command::new("/bin/sh")
        .args(["-c", "kill -KILL $$"])
        .spawn()
        .expect("spawn owner");
    let owner_pid = owner.id();
    assert!(!owner.wait().expect("wait for killed owner").success());
    // Leave exactly the registry state of a helper killed before cleanup.
    for registration in registrations {
        std::fs::rename(
            &registration.marker_file,
            registration.marker_dir.join(owner_pid.to_string()),
        )
        .expect("abandon owner marker");
    }
}

#[test]
fn cleanup_synthetic_mount_targets_reclaims_file_after_owner_is_killed() {
    let workspace = tempfile::TempDir::new().expect("workspace");
    let path = workspace.path().join("blocked");
    let registrations =
        register_synthetic_mount_targets(&[crate::bwrap::SyntheticMountTarget::missing(&path)]);
    assert!(path.exists());
    abandon_synthetic_mount_registrations(&registrations);

    let metadata = std::fs::symlink_metadata(&path).expect("stat mount target");
    let registrations = register_synthetic_mount_targets(&[
        crate::bwrap::SyntheticMountTarget::existing_empty_file(&path, &metadata),
    ]);
    cleanup_synthetic_mount_targets(&registrations);
    assert!(!path.exists());
}

#[test]
fn cleanup_synthetic_mount_targets_preserves_unrecorded_directory_after_owner_is_killed() {
    let workspace = tempfile::TempDir::new().expect("workspace");
    let path = workspace.path().join(".agents");
    // Simulate an old helper killed before bwrap created its mount target.
    let marker_dir = synthetic_mount_marker_dir(&path);
    std::fs::create_dir_all(&marker_dir).expect("create marker directory");
    std::fs::write(
        marker_dir.join(std::process::id().to_string()),
        SYNTHETIC_MOUNT_MARKER_SYNTHETIC,
    )
    .expect("write legacy marker");
    abandon_synthetic_mount_registrations(&[SyntheticMountTargetRegistration {
        target: crate::bwrap::SyntheticMountTarget::missing_empty_directory(&path),
        marker_file: marker_dir.join(std::process::id().to_string()),
        marker_dir,
    }]);
    std::fs::create_dir(&path).expect("create real directory after owner died");

    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    cleanup_synthetic_mount_targets(&registrations);
    assert!(path.exists());
}

#[test_case::test_case(false; "directory")]
#[test_case::test_case(true; "file")]
fn cleanup_synthetic_mount_targets_preserves_replacement_after_owner_is_killed(file: bool) {
    let workspace = tempfile::TempDir::new().expect("workspace");
    let path = workspace.path().join(".agents");
    let target = if file {
        crate::bwrap::SyntheticMountTarget::missing(&path)
    } else {
        crate::bwrap::SyntheticMountTarget::missing_empty_directory(&path)
    };
    let registrations = register_synthetic_mount_targets(&[target]);
    abandon_synthetic_mount_registrations(&registrations);
    // Keep the old inode allocated so this test does not depend on inode reuse.
    std::fs::rename(&path, workspace.path().join("old-target")).expect("move leaked target");
    if file {
        std::fs::write(&path, "").expect("create real empty file");
    } else {
        std::fs::create_dir(&path).expect("create real empty directory");
    }

    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    cleanup_synthetic_mount_targets(&registrations);
    assert!(path.exists());
}

#[test]
fn cleanup_synthetic_mount_targets_preserves_modified_directory_after_owner_is_killed() {
    use std::os::unix::fs::PermissionsExt;

    let workspace = tempfile::TempDir::new().expect("workspace");
    let path = workspace.path().join(".agents");
    let registrations = register_synthetic_mount_targets(&[
        crate::bwrap::SyntheticMountTarget::missing_empty_directory(&path),
    ]);
    let identity = read_synthetic_mount_identity(&registrations[0].marker_dir)
        .expect("recorded mount identity");
    abandon_synthetic_mount_registrations(&registrations);
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700))
        .expect("change directory permissions");
    let metadata = std::fs::symlink_metadata(&path).expect("stat modified directory");
    assert_ne!(identity, SyntheticMountIdentity::from_metadata(&metadata));

    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    cleanup_synthetic_mount_targets(&registrations);
    assert!(path.exists());
}

#[test]
fn cleanup_synthetic_mount_targets_preserves_real_pre_existing_directories() {
    let workspace = tempfile::TempDir::new().expect("workspace");
    for name in [".git", ".agents", ".codex", ".aws"] {
        std::fs::create_dir(workspace.path().join(name)).expect("create real directory");
    }
    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    abandon_synthetic_mount_registrations(&registrations);
    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    cleanup_synthetic_mount_targets(&registrations);
    for name in [".git", ".agents", ".codex", ".aws"] {
        assert!(workspace.path().join(name).exists(), "preserve {name}");
    }
}

#[test]
fn cleanup_synthetic_mount_targets_waits_for_live_owner_before_reclaiming_leak() {
    let workspace = tempfile::TempDir::new().expect("workspace");
    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    abandon_synthetic_mount_registrations(&registrations);
    let active_marker = registrations[0].marker_dir.join("1");
    std::fs::write(&active_marker, SYNTHETIC_MOUNT_MARKER_SYNTHETIC).expect("write live marker");

    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    cleanup_synthetic_mount_targets(&registrations);
    let live_target = registrations
        .iter()
        .find(|registration| registration.marker_dir.join("1") == active_marker)
        .expect("live target");
    assert!(live_target.target.path().exists());

    std::fs::remove_file(active_marker).expect("remove live marker");
    let targets = workspace_synthetic_mount_targets(workspace.path());
    let registrations = register_synthetic_mount_targets(&targets);
    cleanup_synthetic_mount_targets(&registrations);
    assert!(!live_target.target.path().exists());
}

#[test]
fn cleanup_synthetic_mount_targets_preserves_nonempty_file_even_with_matching_identity() {
    let workspace = tempfile::TempDir::new().expect("workspace");
    let path = workspace.path().join("blocked");
    let registrations =
        register_synthetic_mount_targets(&[crate::bwrap::SyntheticMountTarget::missing(&path)]);
    std::fs::write(&path, "user data").expect("write user data");
    // Model a filesystem whose timestamp precision cannot distinguish the
    // creation from the write: identity equality must never authorize deleting
    // a nonempty file.
    let identity = SyntheticMountIdentity::from_metadata(
        &std::fs::symlink_metadata(&path).expect("stat user file"),
    );
    std::fs::write(
        registrations[0]
            .marker_dir
            .join(SYNTHETIC_MOUNT_IDENTITY_FILE),
        serde_json::to_vec(&identity).expect("serialize identity"),
    )
    .expect("model matching identity");
    cleanup_synthetic_mount_targets(&registrations);
    assert_eq!(
        std::fs::read_to_string(path).expect("read user file"),
        "user data"
    );
}

#[test]
fn cleanup_synthetic_mount_targets_preserves_real_pre_existing_empty_file() {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let empty_file = temp_dir.path().join(".git");
    std::fs::write(&empty_file, "").expect("write pre-existing empty file");
    let metadata = std::fs::symlink_metadata(&empty_file).expect("stat empty file");
    let first_target =
        crate::bwrap::SyntheticMountTarget::existing_empty_file(&empty_file, &metadata);
    let second_target =
        crate::bwrap::SyntheticMountTarget::existing_empty_file(&empty_file, &metadata);

    let first_registrations = register_synthetic_mount_targets(&[first_target]);
    let second_registrations = register_synthetic_mount_targets(&[second_target]);

    cleanup_synthetic_mount_targets(&first_registrations);
    cleanup_synthetic_mount_targets(&second_registrations);

    assert!(empty_file.exists());
}

#[test]
fn bwrap_signal_forwarder_terminates_child_and_keeps_parent_alive() {
    let supervisor_pid = unsafe { libc::fork() };
    assert!(supervisor_pid >= 0, "failed to fork supervisor");

    if supervisor_pid == 0 {
        run_bwrap_signal_forwarder_test_supervisor();
    }

    let status = wait_for_bwrap_child(supervisor_pid);
    assert!(libc::WIFEXITED(status), "supervisor status: {status}");
    assert_eq!(libc::WEXITSTATUS(status), 0);
}

#[cfg(test)]
fn run_bwrap_signal_forwarder_test_supervisor() -> ! {
    let child_pid = unsafe { libc::fork() };
    if child_pid < 0 {
        unsafe {
            libc::_exit(2);
        }
    }

    if child_pid == 0 {
        loop {
            unsafe {
                libc::pause();
            }
        }
    }

    install_bwrap_signal_forwarders(child_pid);
    unsafe {
        libc::raise(libc::SIGTERM);
    }

    let status = wait_for_bwrap_child(child_pid);
    let child_terminated_by_sigterm =
        libc::WIFSIGNALED(status) && libc::WTERMSIG(status) == libc::SIGTERM;
    unsafe {
        libc::_exit(if child_terminated_by_sigterm { 0 } else { 1 });
    }
}

#[test]
fn managed_proxy_inner_command_includes_route_spec() {
    let permission_profile = read_only_permission_profile();
    for managed_network in [
        ManagedNetworkSandboxContext::default(),
        ManagedNetworkSandboxContext {
            loopback_ports: vec![8080, 9090],
            allow_local_binding: true,
            allow_unix_sockets: vec!["/tmp/daemon.sock".to_string()],
            dangerously_allow_all_unix_sockets: true,
        },
    ] {
        let args = build_inner_seccomp_command(InnerSeccompCommandArgs {
            sandbox_policy_cwd: Path::new("/tmp"),
            command_cwd: Some(Path::new("/tmp/link")),
            permission_profile: &permission_profile,
            managed_network: Some(managed_network.clone()),
            proxy_route_spec: Some("{\"routes\":[]}".to_string()),
            command: vec!["/bin/true".to_string()],
        });

        assert!(args.iter().any(|arg| arg == "--proxy-route-spec"));
        assert!(args.iter().any(|arg| arg == "{\"routes\":[]}"));
        let parsed = LinuxSandboxCommand::try_parse_from(args)
            .expect("inner command should preserve the managed network policy");
        assert_eq!(parsed.managed_network, Some(managed_network));
    }
}

#[test]
fn managed_network_policy_alone_enables_proxy_mode() {
    let parsed = LinuxSandboxCommand::try_parse_from([
        "codex-linux-sandbox",
        "--sandbox-policy-cwd",
        "/tmp",
        "--managed-network",
        "{}",
        "--",
        "/bin/true",
    ])
    .expect("managed network context should enable proxy mode on its own");
    assert_eq!(
        parsed.managed_network,
        Some(ManagedNetworkSandboxContext::default())
    );
}

#[test]
fn malformed_managed_network_policy_is_rejected() {
    let error = LinuxSandboxCommand::try_parse_from([
        "codex-linux-sandbox",
        "--sandbox-policy-cwd",
        "/tmp",
        "--managed-network",
        "{\"dangerouslyAllowAllUnixSockets\":\"true\"}",
        "--",
        "/bin/true",
    ])
    .expect_err("managed network policy should reject a non-boolean grant");
    assert_eq!(error.kind(), clap::error::ErrorKind::ValueValidation);
}

#[test]
fn inner_command_includes_permission_profile_flag() {
    let permission_profile = read_only_permission_profile();
    let args = build_inner_seccomp_command(InnerSeccompCommandArgs {
        sandbox_policy_cwd: Path::new("/tmp"),
        command_cwd: Some(Path::new("/tmp/link")),
        permission_profile: &permission_profile,
        managed_network: None,
        proxy_route_spec: None,
        command: vec!["/bin/true".to_string()],
    });

    assert!(args.iter().any(|arg| arg == "--permission-profile"));
    assert!(
        args.windows(2)
            .any(|window| { window == ["--command-cwd", "/tmp/link"] })
    );
}

#[test]
fn non_managed_inner_command_omits_route_spec() {
    let permission_profile = read_only_permission_profile();
    let args = build_inner_seccomp_command(InnerSeccompCommandArgs {
        sandbox_policy_cwd: Path::new("/tmp"),
        command_cwd: Some(Path::new("/tmp/link")),
        permission_profile: &permission_profile,
        managed_network: None,
        proxy_route_spec: None,
        command: vec!["/bin/true".to_string()],
    });

    assert!(!args.iter().any(|arg| arg == "--proxy-route-spec"));
    let parsed = LinuxSandboxCommand::try_parse_from(args)
        .expect("unmanaged inner command should preserve ordinary sandbox mode");
    assert_eq!(parsed.managed_network, None);
}

#[test]
fn managed_proxy_inner_command_requires_route_spec() {
    let result = std::panic::catch_unwind(|| {
        let permission_profile = read_only_permission_profile();
        build_inner_seccomp_command(InnerSeccompCommandArgs {
            sandbox_policy_cwd: Path::new("/tmp"),
            command_cwd: Some(Path::new("/tmp/link")),
            permission_profile: &permission_profile,
            managed_network: Some(ManagedNetworkSandboxContext::default()),
            proxy_route_spec: None,
            command: vec!["/bin/true".to_string()],
        })
    });
    assert!(result.is_err());
}

#[test]
fn resolve_permission_profile_derives_runtime_policies() {
    let permission_profile = read_only_permission_profile();
    let resolved = resolve_permission_profile(Some(permission_profile.clone()))
        .expect("profile should resolve");

    assert_eq!(resolved.permission_profile, permission_profile);
    assert_eq!(
        resolved.file_system_sandbox_policy,
        read_only_file_system_policy()
    );
    assert_eq!(
        resolved.network_sandbox_policy,
        NetworkSandboxPolicy::Restricted
    );
}

#[test]
fn resolve_permission_profile_preserves_direct_runtime_profile() {
    let temp_dir = tempfile::TempDir::new().expect("tempdir");
    let docs = temp_dir.path().join("docs");
    std::fs::create_dir_all(&docs).expect("create docs");
    let docs = AbsolutePathBuf::from_absolute_path(&docs).expect("absolute docs");
    let file_system_sandbox_policy = FileSystemSandboxPolicy::restricted(vec![
        codex_protocol::permissions::FileSystemSandboxEntry {
            path: codex_protocol::permissions::FileSystemPath::Special {
                value: codex_protocol::permissions::FileSystemSpecialPath::Root,
            },
            access: codex_protocol::permissions::FileSystemAccessMode::Read,
            missing_path_behavior: None,
        },
        codex_protocol::permissions::FileSystemSandboxEntry {
            path: docs.into(),
            access: codex_protocol::permissions::FileSystemAccessMode::Write,
            missing_path_behavior: None,
        },
    ]);
    let permission_profile = PermissionProfile::from_runtime_permissions(
        &file_system_sandbox_policy,
        NetworkSandboxPolicy::Restricted,
    );
    let resolved = resolve_permission_profile(Some(permission_profile.clone()))
        .expect("profile should resolve");

    assert_eq!(resolved.permission_profile, permission_profile);
    assert_eq!(
        resolved.file_system_sandbox_policy,
        file_system_sandbox_policy
    );
    assert_eq!(
        resolved.network_sandbox_policy,
        NetworkSandboxPolicy::Restricted
    );
}

#[test]
fn resolve_permission_profile_rejects_missing_configuration() {
    let err = resolve_permission_profile(/*permission_profile*/ None)
        .expect_err("missing profile should fail");

    assert_eq!(err, ResolvePermissionProfileError::MissingConfiguration);
}

#[test]
fn apply_seccomp_then_exec_with_legacy_landlock_panics() {
    let result = std::panic::catch_unwind(|| {
        ensure_inner_stage_mode_is_valid(
            /*apply_seccomp_then_exec*/ true, /*use_legacy_landlock*/ true,
        )
    });
    assert!(result.is_err());
}

#[test]
#[should_panic(expected = "filesystem-restricted execution requires bubblewrap")]
fn legacy_landlock_cannot_bypass_daemon_socket_isolation() {
    ensure_legacy_landlock_mode_supports_policy(
        /*use_legacy_landlock*/ true,
        &read_only_file_system_policy(),
    );
}

#[test]
fn valid_inner_stage_modes_do_not_panic() {
    ensure_inner_stage_mode_is_valid(
        /*apply_seccomp_then_exec*/ false, /*use_legacy_landlock*/ false,
    );
    ensure_inner_stage_mode_is_valid(
        /*apply_seccomp_then_exec*/ false, /*use_legacy_landlock*/ true,
    );
    ensure_inner_stage_mode_is_valid(
        /*apply_seccomp_then_exec*/ true, /*use_legacy_landlock*/ false,
    );
}
