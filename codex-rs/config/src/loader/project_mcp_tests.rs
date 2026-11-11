use super::tests::TestFileSystem;
use super::*;
use pretty_assertions::assert_eq;
use tempfile::TempDir;

struct Fixture {
    _temp: TempDir,
    home: std::path::PathBuf,
    project: AbsolutePathBuf,
}

impl Fixture {
    fn new(trust: &str, user_servers: &str) -> Self {
        let temp = tempfile::tempdir().unwrap();
        let home = temp.path().join("home");
        let project = AbsolutePathBuf::from_absolute_path(temp.path().join("project")).unwrap();
        std::fs::create_dir_all(&home).unwrap();
        std::fs::create_dir_all(project.as_path()).unwrap();
        std::fs::write(project.join(".project-root"), "").unwrap();
        let quoted = TomlValue::String(project.as_path().display().to_string());
        std::fs::write(home.join(CONFIG_TOML_FILE), format!(
            "project_root_markers=['.project-root']\n{user_servers}\n[projects.{quoted}]\ntrust_level='{trust}'\n"
        )).unwrap();
        Self {
            _temp: temp,
            home,
            project,
        }
    }

    async fn load(&self, cwd: &AbsolutePathBuf, flags: &[(String, TomlValue)]) -> ConfigLayerStack {
        load_config_layers_state(
            &TestFileSystem,
            &self.home,
            Some(cwd.clone()),
            flags,
            LoaderOverrides::without_managed_config_for_tests(),
            &crate::NoopThreadConfigLoader,
        )
        .await
        .unwrap()
    }
}

fn write(path: &AbsolutePathBuf, file: &str, text: &str) {
    std::fs::create_dir_all(path).unwrap();
    std::fs::write(path.join(file), text).unwrap();
}

#[tokio::test]
async fn discovers_root_without_dot_codex_from_nested_directory_and_reloads() {
    let fixture = Fixture::new("trusted", "");
    let nested = fixture.project.join("src");
    std::fs::create_dir_all(&nested).unwrap();
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"mcpServers":{"worker":{"command":"node","args":["server.js"]}}}"#,
    );
    let stack = fixture.load(&nested, &[]).await;
    let config = stack.effective_config();
    assert_eq!(
        config["mcp_servers"]["worker"]["cwd"].as_str(),
        Some(fixture.project.as_path().to_str().unwrap())
    );
    assert!(!stack.is_projectless());
    assert!(stack.startup_warnings().unwrap().is_empty());
    assert!(!fixture.project.join(".codex").exists());
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"worker":{"url":"https://new.test/mcp"}}"#,
    );
    let reloaded = fixture.load(&nested, &[]).await.effective_config();
    assert_eq!(
        reloaded["mcp_servers"]["worker"]["url"].as_str(),
        Some("https://new.test/mcp")
    );
    assert!(reloaded["mcp_servers"]["worker"].get("command").is_none());
}

#[tokio::test]
async fn nested_json_atomically_replaces_user_and_root_credentials() {
    let fixture = Fixture::new(
        "trusted",
        "[mcp_servers.api]\nurl='https://user.test'\nhttp_headers.Authorization='user-value'",
    );
    let child = fixture.project.join("child");
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"api":{"url":"https://root.test","headers":{"X-Root":"root-value"}}}"#,
    );
    write(&child, ".mcp.json", r#"{"api":{"command":"node"}}"#);
    let stack = fixture.load(&child, &[]).await;
    let config = stack.effective_config();
    let api = &config["mcp_servers"]["api"];
    assert_eq!(api["command"].as_str(), Some("node"));
    assert!(api.get("url").is_none());
    assert!(api.get("http_headers").is_none());
    assert!(
        !stack
            .origins()
            .contains_key("mcp_servers.api.http_headers.Authorization")
    );

    let local = super::local::load_local_config_layers_with_overrides(
        &TestFileSystem,
        &fixture.home,
        &child,
        &LoaderOverrides::without_managed_config_for_tests(),
    )
    .await
    .unwrap();
    let mut projected = TomlValue::Table(Default::default());
    for layer in local.config.layers {
        crate::merge_toml_values(&mut projected, &layer.toml);
    }
    assert_eq!(projected["mcp_servers"], config["mcp_servers"]);
}

#[tokio::test]
async fn native_controls_and_complete_definitions_have_expected_precedence() {
    let fixture = Fixture::new("trusted", "");
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"worker":{"command":"node","env":{"JSON_ONLY":"value"}},"api":{"url":"https://json.test","headers":{"Authorization":"json-value"}}}"#,
    );
    let native = fixture.project.join(".codex");
    write(
        &native,
        "config.toml",
        "[mcp_servers.worker]\nenabled=false\ndisabled_tools=['write']\n[mcp_servers.api]\nurl='https://native.test'",
    );
    let config = fixture.load(&fixture.project, &[]).await.effective_config();
    assert_eq!(
        config["mcp_servers"]["worker"]["command"].as_str(),
        Some("node")
    );
    assert_eq!(
        config["mcp_servers"]["worker"]["enabled"].as_bool(),
        Some(false)
    );
    assert_eq!(
        config["mcp_servers"]["worker"]["disabled_tools"][0].as_str(),
        Some("write")
    );
    assert_eq!(
        config["mcp_servers"]["api"]["url"].as_str(),
        Some("https://native.test")
    );
    assert!(config["mcp_servers"]["api"].get("http_headers").is_none());
    let config = fixture
        .load(
            &fixture.project,
            &[(
                "mcp_servers.worker.enabled".to_string(),
                TomlValue::Boolean(true),
            )],
        )
        .await
        .effective_config();
    assert_eq!(
        config["mcp_servers"]["worker"]["enabled"].as_bool(),
        Some(true)
    );
}

#[tokio::test]
async fn higher_native_transport_replaces_ancestor_json() {
    let fixture = Fixture::new("trusted", "");
    let child = fixture.project.join("child");
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"api":{"url":"https://root.test","headers":{"Authorization":"root-value"}}}"#,
    );
    write(
        &child.join(".codex"),
        "config.toml",
        "[mcp_servers.api]\ncommand='node'",
    );
    let config = fixture.load(&child, &[]).await.effective_config();
    assert_eq!(
        config["mcp_servers"]["api"]["command"].as_str(),
        Some("node")
    );
    assert!(config["mcp_servers"]["api"].get("url").is_none());
    assert!(config["mcp_servers"]["api"].get("http_headers").is_none());
}

#[tokio::test]
async fn sse_and_invalid_entries_warn_without_reactivating_lower_servers() {
    let fixture = Fixture::new("trusted", "[mcp_servers.old]\ncommand='must-not-run'");
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"mcpServers":{"old":{"type":"sse","url":"https://example.test/sse?private=not-for-diagnostics"},"good":{"command":"node"},"invalid":{"command":"node","args":false}}}"#,
    );
    let stack = fixture.load(&fixture.project, &[]).await;
    let config = stack.effective_config();
    assert_eq!(
        config["mcp_servers"]["old"]["enabled"].as_bool(),
        Some(false)
    );
    assert_ne!(
        config["mcp_servers"]["old"]["command"].as_str(),
        Some("must-not-run")
    );
    assert_eq!(
        config["mcp_servers"]["good"]["command"].as_str(),
        Some("node")
    );
    let warnings = stack.startup_warnings().unwrap().join("\n");
    assert!(warnings.contains(".mcp.json"));
    assert!(warnings.contains("old"));
    assert!(warnings.contains("SSE"));
    assert!(!warnings.contains("not-for-diagnostics"));
}

#[tokio::test]
async fn untrusted_json_is_not_expanded_or_activated() {
    let fixture = Fixture::new("untrusted", "");
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"worker":{"command":"${CODEX_MCP_TEST_MISSING}"}}"#,
    );
    let stack = fixture.load(&fixture.project, &[]).await;
    assert!(stack.effective_config().get("mcp_servers").is_none());
    assert!(
        stack
            .startup_warnings()
            .unwrap()
            .iter()
            .all(|warning| !warning.contains("CODEX_MCP_TEST_MISSING"))
    );
    assert!(
        stack.all_layers_low_to_high().any(|layer| matches!(
            layer.name,
            ConfigLayerSource::Project { .. }
        ) && layer.is_disabled())
    );
}

#[tokio::test]
async fn malformed_file_warns_and_preserves_native_configuration() {
    let fixture = Fixture::new("trusted", "");
    write(&fixture.project, ".mcp.json", "{");
    write(
        &fixture.project.join(".codex"),
        "config.toml",
        "[mcp_servers.native]\ncommand='node'",
    );
    let stack = fixture.load(&fixture.project, &[]).await;
    assert_eq!(
        stack.effective_config()["mcp_servers"]["native"]["command"].as_str(),
        Some("node")
    );
    assert_eq!(stack.startup_warnings().unwrap().len(), 1);
}

#[tokio::test]
async fn project_boundary_and_ignore_project_config_apply_to_json() {
    let fixture = Fixture::new("trusted", "");
    write(
        &fixture.project.parent().unwrap(),
        ".mcp.json",
        r#"{"outside":{"command":"outside"}}"#,
    );
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"inside":{"command":"inside"}}"#,
    );
    let config = fixture.load(&fixture.project, &[]).await.effective_config();
    assert!(config["mcp_servers"].get("outside").is_none());
    let stack = load_config_layers_state(
        &TestFileSystem,
        &fixture.home,
        Some(fixture.project.clone()),
        &[],
        LoaderOverrides {
            ignore_project_config: true,
            ..LoaderOverrides::without_managed_config_for_tests()
        },
        &crate::NoopThreadConfigLoader,
    )
    .await
    .unwrap();
    assert!(stack.effective_config().get("mcp_servers").is_none());
}

#[tokio::test]
async fn no_project_marker_scopes_discovery_to_cwd() {
    let fixture = Fixture::new("trusted", "");
    std::fs::remove_file(fixture.project.join(".project-root")).unwrap();
    let child = fixture.project.join("child");
    write(
        &fixture.project,
        ".mcp.json",
        r#"{"outside":{"command":"outside"}}"#,
    );
    write(&child, ".mcp.json", r#"{"inside":{"command":"inside"}}"#);
    let quoted = TomlValue::String(child.as_path().display().to_string());
    std::fs::write(
        fixture.home.join(CONFIG_TOML_FILE),
        format!(
            "project_root_markers=['.project-root']\n[projects.{quoted}]\ntrust_level='trusted'"
        ),
    )
    .unwrap();
    let config = fixture.load(&child, &[]).await.effective_config();
    assert!(config["mcp_servers"].get("outside").is_none());
    assert_eq!(
        config["mcp_servers"]["inside"]["command"].as_str(),
        Some("inside")
    );
}
