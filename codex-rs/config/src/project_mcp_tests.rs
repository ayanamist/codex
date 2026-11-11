use super::*;
use pretty_assertions::assert_eq;

fn directory() -> std::path::PathBuf {
    std::env::temp_dir().join("codex-project-mcp-tests")
}

fn parse(text: &str) -> ProjectMcpConfig {
    ProjectMcpConfig::parse_with_env(text, &directory(), |name| match name {
        "TOKEN" => Some("fixture-secret".to_string()),
        "EMPTY" => Some(String::new()),
        _ => None,
    })
}

fn servers(config: &ProjectMcpConfig) -> &toml::Table {
    config.config["mcp_servers"].as_table().unwrap()
}

#[test]
fn jsonc_and_bare_shapes_preserve_launch_settings() {
    for text in [
        "\u{feff}{ /* comment */ \"$schema\":\"metadata\", \"mcpServers\": {\"test\": {\"command\":\"node\",\"args\":[\"./server.js\",],},},}",
        r#"{"test":{"type":"local","command":"node","args":["./server.js"]}}"#,
    ] {
        let config = parse(text);
        assert!(config.warnings.is_empty(), "{:?}", config.warnings);
        assert_eq!(servers(&config)["test"]["command"].as_str(), Some("node"));
        assert_eq!(
            servers(&config)["test"]["args"][0].as_str(),
            Some("./server.js")
        );
        assert_eq!(
            servers(&config)["test"]["cwd"].as_str(),
            directory().to_str()
        );
    }
}

#[test]
fn headers_variables_defaults_and_oauth_aliases_are_normalized() {
    let config = parse(
        r#"{"mcpServers":{"api":{
        "type":"streamable-http","url":"${BASE:-https://example.test}/mcp",
        "headers":{"Authorization":"Bearer ${TOKEN}","X-Empty":"${EMPTY:-fallback}"},
        "oauth":{"clientId":"fixture-client","callbackPort":4567}
    }}}"#,
    );
    assert!(config.warnings.is_empty(), "{:?}", config.warnings);
    let api = &servers(&config)["api"];
    assert_eq!(api["url"].as_str(), Some("https://example.test/mcp"));
    assert_eq!(
        api["http_headers"]["Authorization"].as_str(),
        Some("Bearer fixture-secret")
    );
    assert_eq!(api["http_headers"]["X-Empty"].as_str(), Some(""));
    assert_eq!(api["oauth"]["client_id"].as_str(), Some("fixture-client"));
    assert_eq!(api["oauth"]["callback_port"].as_integer(), Some(4567));
}

#[test]
fn stdio_values_expand_and_relative_cwd_uses_declaring_directory() {
    let config = parse(
        r#"{"worker":{"command":"${BIN:-python3}","args":["${SCRIPT:-main.py}"],"cwd":"tools","env":{"KEY":"${TOKEN}"}}}"#,
    );
    assert!(config.warnings.is_empty());
    let worker = &servers(&config)["worker"];
    assert_eq!(worker["command"].as_str(), Some("python3"));
    assert_eq!(worker["args"][0].as_str(), Some("main.py"));
    assert_eq!(worker["env"]["KEY"].as_str(), Some("fixture-secret"));
    assert_eq!(worker["cwd"].as_str(), directory().join("tools").to_str());
}

#[test]
fn malformed_wrapper_does_not_become_a_server() {
    for text in [r#"{"mcpServers":[]}"#, "{", "[]"] {
        let config = parse(text);
        assert!(config.names.is_empty());
        assert_eq!(config.warnings.len(), 1);
    }
}

#[test]
fn invalid_servers_are_isolated_and_diagnostics_do_not_echo_values() {
    let config = parse(
        r#"{"mcpServers":{
        "valid":{"command":"node"},
        "sse":{"type":"sse","url":"https://example.test/sse?token=fixture-secret"},
        "missing":{"url":"https://example.test","headers":{"Authorization":"${MISSING}"}},
        "bad":{"command":"node","args":["fixture-secret",false]},
        "mixed":{"command":"node","url":"https://example.test"},
        "scalar":"fixture-secret",
        "unsupported":{"type":"ws","url":"wss://example.test"}
    } }"#,
    );
    assert_eq!(servers(&config)["valid"]["enabled"].as_bool(), Some(true));
    assert_eq!(config.warnings.len(), 6);
    for name in ["sse", "missing", "bad", "mixed", "scalar", "unsupported"] {
        assert_eq!(servers(&config)[name]["enabled"].as_bool(), Some(false));
        assert!(config.names.contains(name));
    }
    let warnings = config.warnings.join("\n");
    assert!(warnings.contains("legacy SSE"));
    assert!(warnings.contains("MISSING"));
    assert!(!warnings.contains("fixture-secret"));
}

#[test]
fn disabled_flags_mask_inherited_servers_without_resolving_variables() {
    for text in [
        r#"{"server":{"disabled":true}}"#,
        r#"{"server":{"enabled":false,"command":"${MISSING}"}}"#,
        r#"{"server":{"enabled":true,"disabled":true}}"#,
    ] {
        let config = parse(text);
        assert!(config.warnings.is_empty());
        assert_eq!(servers(&config)["server"]["enabled"].as_bool(), Some(false));
    }
}

#[test]
fn transport_aliases_and_conflicts() {
    for kind in ["http", "streamable-http", "streamable_http"] {
        let config = parse(&format!(
            r#"{{"api":{{"type":"{kind}","url":"https://example.test/mcp"}}}}"#
        ));
        assert!(config.warnings.is_empty());
    }
    for text in [
        r#"{"api":{"type":"stdio","url":"https://example.test"}}"#,
        r#"{"api":{"url":"https://example.test","headers":{},"http_headers":{}}}"#,
        r#"{"api":{"type":123,"command":"node"}}"#,
    ] {
        assert_eq!(parse(text).warnings.len(), 1);
    }
}

#[test]
fn vendor_permission_and_timeout_fields_do_not_change_codex_policy() {
    let config = parse(
        r#"{"api":{"command":"node","autoApprove":["*"],"timeout":1000,"description":"metadata"}}"#,
    );
    assert_eq!(config.warnings.len(), 2);
    assert!(
        servers(&config)["api"]
            .get("default_tools_approval_mode")
            .is_none()
    );
    assert!(servers(&config)["api"].get("tool_timeout_sec").is_none());
    assert_eq!(
        parse(r#"{"api":{"url":"https://example.test","headersHelper":"get-token"}}"#)
            .warnings
            .len(),
        1
    );
}

#[test]
fn json_replaces_entries_and_native_control_overrides_remain_partial() {
    let user: TomlValue = toml::from_str(
        "[mcp_servers.api]\nurl='https://old.test'\nhttp_headers.Authorization='user-credential'",
    )
    .unwrap();
    let json = parse(r#"{"api":{"command":"node","env":{"ONLY":"project"}}}"#);
    let mut merged = user;
    let mut policy = ProjectMcpMerge::default();
    policy.merge(&mut merged, &json.config, &json.names);
    assert!(merged["mcp_servers"]["api"].get("url").is_none());
    assert!(merged["mcp_servers"]["api"].get("http_headers").is_none());
    let controls =
        toml::from_str("[mcp_servers.api]\nenabled=false\ndisabled_tools=['write']").unwrap();
    policy.merge(&mut merged, &controls, &BTreeSet::new());
    assert_eq!(
        merged["mcp_servers"]["api"]["command"].as_str(),
        Some("node")
    );
    assert_eq!(
        merged["mcp_servers"]["api"]["enabled"].as_bool(),
        Some(false)
    );
    let native = toml::from_str("[mcp_servers.api]\nurl='https://native.test'").unwrap();
    policy.merge(&mut merged, &native, &BTreeSet::new());
    let api = &merged["mcp_servers"]["api"];
    assert!(api.get("command").is_none());
    assert!(api.get("env").is_none());
    assert_eq!(api["url"].as_str(), Some("https://native.test"));
}

#[test]
fn native_only_merging_is_unchanged() {
    let mut policy = ProjectMcpMerge::default();
    let mut merged =
        toml::from_str("[mcp_servers.api]\ncommand='node'\nargs=['server.js']").unwrap();
    policy.merge(
        &mut merged,
        &toml::from_str("[mcp_servers.api]\ncommand='node2'").unwrap(),
        &BTreeSet::new(),
    );
    assert_eq!(
        merged["mcp_servers"]["api"]["args"][0].as_str(),
        Some("server.js")
    );
}
