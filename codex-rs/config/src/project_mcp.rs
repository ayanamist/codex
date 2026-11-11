//! Compatibility boundary for project `.mcp.json` declarations.
//!
//! Keep this separate from plugin parsing: project paths, variable expansion and
//! server replacement have different semantics from installed plugin packages.

use crate::McpServerConfig;
use serde_json::Map;
use serde_json::Value;
use std::collections::BTreeSet;
use std::path::Path;
use toml::Value as TomlValue;

pub(crate) const FILE_NAME: &str = ".mcp.json";

pub(crate) struct ProjectMcpConfig {
    pub config: TomlValue,
    pub names: BTreeSet<String>,
    pub warnings: Vec<String>,
}

impl ProjectMcpConfig {
    pub fn parse(contents: &str, directory: &Path) -> Self {
        Self::parse_with_env(contents, directory, |name| std::env::var(name).ok())
    }

    fn parse_with_env(
        contents: &str,
        directory: &Path,
        lookup: impl Fn(&str) -> Option<String>,
    ) -> Self {
        let mut result = Self {
            config: TomlValue::Table(Default::default()),
            names: BTreeSet::new(),
            warnings: Vec::new(),
        };
        let contents = contents.strip_prefix('\u{feff}').unwrap_or(contents);
        let parsed = jsonc_parser::parse_to_serde_value::<Value>(contents, &Default::default());
        let Ok(Value::Object(mut document)) = parsed else {
            result.warn(directory, None, "expected a JSONC object");
            return result;
        };
        let servers = if let Some(servers) = document.remove("mcpServers") {
            let Value::Object(servers) = servers else {
                result.warn(directory, None, "`mcpServers` must be an object");
                return result;
            };
            servers
        } else {
            document.remove("$schema");
            document
        };
        let mut normalized = toml::map::Map::new();
        for (name, value) in servers {
            result.names.insert(name.clone());
            let mut warnings = Vec::new();
            let config = match normalize(value, directory, &lookup, &mut warnings) {
                Ok(config) => config,
                Err(message) => {
                    warnings.push(message);
                    disabled_server()
                }
            };
            for warning in warnings {
                result.warn(directory, Some(&name), &warning);
            }
            normalized.insert(name, config);
        }
        result.config = TomlValue::Table(toml::map::Map::from_iter([(
            "mcp_servers".to_string(),
            TomlValue::Table(normalized),
        )]));
        result
    }

    fn warn(&mut self, directory: &Path, server: Option<&str>, message: &str) {
        let file = directory.join(FILE_NAME);
        let subject = server
            .map(|name| format!(" server `{name}`"))
            .unwrap_or_default();
        self.warnings
            .push(format!("{}:{subject}: {message}", file.display()));
    }
}

/// A typed, inert definition masks lower-priority definitions even when this
/// declaration is invalid or explicitly disabled. No endpoint or secret survives.
fn disabled_server() -> TomlValue {
    TomlValue::Table(toml::map::Map::from_iter([
        ("command".to_string(), TomlValue::String(String::new())),
        ("enabled".to_string(), TomlValue::Boolean(false)),
    ]))
}

fn normalize(
    value: Value,
    directory: &Path,
    lookup: &impl Fn(&str) -> Option<String>,
    warnings: &mut Vec<String>,
) -> Result<TomlValue, String> {
    let Value::Object(mut object) = value else {
        return Err("skipped: server must be an object".to_string());
    };
    for key in ["enabled", "disabled"] {
        if object.get(key).is_some_and(|value| !value.is_boolean()) {
            return Err(format!("skipped: `{key}` must be a boolean"));
        }
    }
    let transport = object.remove("type");
    if transport.as_ref() == Some(&Value::String("sse".to_string())) {
        return Err("skipped: legacy SSE transport is not supported".to_string());
    }
    if object.get("disabled") == Some(&Value::Bool(true))
        || object.get("enabled") == Some(&Value::Bool(false))
    {
        return Ok(disabled_server());
    }
    object.remove("disabled");
    let command = object.contains_key("command");
    let url = object.contains_key("url");
    match transport.as_ref().and_then(Value::as_str) {
        None if transport.is_none() => {}
        Some("stdio" | "local") if command && !url => {}
        Some("http" | "streamable-http" | "streamable_http") if url && !command => {}
        _ => return Err("skipped: unsupported `type` or conflicting transport fields".to_string()),
    }
    if command == url {
        return Err("skipped: specify exactly one of `command` or `url`".to_string());
    }

    // These are metadata or vendor-specific policies, not Codex permissions.
    for key in ["description", "name", "$schema"] {
        object.remove(key);
    }
    for key in ["timeout", "autoApprove", "alwaysAllow", "tools"] {
        if object.remove(key).is_some() {
            warnings.push(format!(
                "ignored vendor-specific `{key}`; use native Codex settings"
            ));
        }
    }
    alias(&mut object, "headers", "http_headers")?;
    alias(&mut object, "disabledTools", "disabled_tools")?;
    if let Some(Value::Object(oauth)) = object.get_mut("oauth") {
        for (from, to) in [
            ("clientId", "client_id"),
            ("clientSecret", "client_secret"),
            ("callbackUrl", "callback_url"),
            ("callbackPort", "callback_port"),
        ] {
            alias(oauth, from, to)?;
        }
        if let Some(key) = oauth.keys().find(|key| {
            ![
                "client_id",
                "client_secret",
                "callback_url",
                "callback_port",
                "token_endpoint_auth_method",
                "authorization_server_issuer",
            ]
            .contains(&key.as_str())
        }) {
            return Err(format!("skipped: unsupported OAuth field `{key}`"));
        }
    }
    // Authentication helpers and execution extensions need an explicit contract.
    // Do not silently load a partially interpreted authentication configuration.
    const SUPPORTED: &[&str] = &[
        "command",
        "args",
        "env",
        "cwd",
        "url",
        "http_headers",
        "enabled",
        "env_vars",
        "env_http_headers",
        "bearer_token_env_var",
        "oauth",
        "scopes",
        "oauth_resource",
        "startup_timeout_sec",
        "startup_timeout_ms",
        "tool_timeout_sec",
        "enabled_tools",
        "disabled_tools",
        "required",
    ];
    if let Some(key) = object.keys().find(|key| !SUPPORTED.contains(&key.as_str())) {
        return Err(format!("skipped: unsupported field `{key}`"));
    }
    for key in ["command", "url", "cwd"] {
        if let Some(value) = object.get_mut(key) {
            expand_string(value, key, lookup)?;
        }
    }
    if let Some(args) = object.get_mut("args") {
        let Value::Array(args) = args else {
            return Err("skipped: `args` must be an array".to_string());
        };
        for value in args {
            expand_string(value, "args", lookup)?;
        }
    }
    for key in ["env", "http_headers"] {
        if let Some(values) = object.get_mut(key) {
            let Value::Object(values) = values else {
                return Err(format!("skipped: `{key}` must be an object"));
            };
            for value in values.values_mut() {
                expand_string(value, key, lookup)?;
            }
        }
    }
    if command {
        if object
            .get("command")
            .and_then(Value::as_str)
            .is_none_or(|value| value.trim().is_empty())
        {
            return Err("skipped: `command` must not be empty".to_string());
        }
        let cwd = object.get("cwd").and_then(Value::as_str).map(Path::new);
        let cwd = match cwd {
            Some(cwd) if cwd.is_absolute() => cwd.to_path_buf(),
            Some(cwd) => directory.join(cwd),
            None => directory.to_path_buf(),
        };
        object.insert(
            "cwd".to_string(),
            Value::String(cwd.to_string_lossy().into_owned()),
        );
    } else if object
        .get("url")
        .and_then(Value::as_str)
        .is_none_or(|value| value.trim().is_empty())
    {
        return Err("skipped: `url` must not be empty".to_string());
    }
    let config: McpServerConfig = serde_path_to_error::deserialize(Value::Object(object))
        .map_err(|error| format!("skipped: invalid field `{}`", error.path()))?;
    TomlValue::try_from(config).map_err(|_| "skipped: invalid server configuration".to_string())
}

fn alias(object: &mut Map<String, Value>, from: &str, to: &str) -> Result<(), String> {
    if let Some(value) = object.remove(from) {
        if object.contains_key(to) {
            return Err(format!("skipped: specify only one of `{from}` and `{to}`"));
        }
        object.insert(to.to_string(), value);
    }
    Ok(())
}

fn expand_string(
    value: &mut Value,
    field: &str,
    lookup: &impl Fn(&str) -> Option<String>,
) -> Result<(), String> {
    let Value::String(text) = value else {
        return Err(format!("skipped: `{field}` values must be strings"));
    };
    *text = expand(text, lookup)
        .map_err(|name| format!("skipped: unset variable `{name}` in `{field}`"))?;
    Ok(())
}

fn expand(text: &str, lookup: &impl Fn(&str) -> Option<String>) -> Result<String, String> {
    let mut result = String::new();
    let mut rest = text;
    while let Some(start) = rest.find("${") {
        result.push_str(&rest[..start]);
        let reference = &rest[start + 2..];
        let Some(end) = reference.find('}') else {
            result.push_str(&rest[start..]);
            return Ok(result);
        };
        let reference = &reference[..end];
        let (name, default) = reference
            .split_once(":-")
            .map_or((reference, None), |(name, default)| (name, Some(default)));
        if name.is_empty()
            || !name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
        {
            // Other clients' substitution languages are not environment variables.
            return Err("unsupported substitution".to_string());
        }
        match lookup(name) {
            Some(value) => result.push_str(&value),
            None => match default {
                Some(default) => result.push_str(default),
                None => return Err(name.to_string()),
            },
        }
        rest = &rest[start + 2 + end + 1..];
    }
    result.push_str(rest);
    Ok(result)
}

/// Apply one layer while keeping complete JSON-origin registrations atomic.
/// Native-only TOML continues using its existing recursive merge semantics.
#[derive(Default)]
pub(crate) struct ProjectMcpMerge {
    json_names: BTreeSet<String>,
}

impl ProjectMcpMerge {
    pub fn merge(
        &mut self,
        base: &mut TomlValue,
        overlay: &TomlValue,
        names: &BTreeSet<String>,
    ) -> BTreeSet<String> {
        let mut replaced = BTreeSet::new();
        if let Some(servers) = overlay.get("mcp_servers").and_then(TomlValue::as_table) {
            for (name, server) in servers {
                let replaces = names.contains(name)
                    || self.json_names.contains(name)
                        && (server.get("command").is_some() || server.get("url").is_some());
                if replaces {
                    replaced.insert(name.clone());
                    if let Some(existing) = base
                        .get_mut("mcp_servers")
                        .and_then(TomlValue::as_table_mut)
                    {
                        existing.remove(name);
                    }
                    if !names.contains(name) {
                        self.json_names.remove(name);
                    }
                }
                if names.contains(name) {
                    self.json_names.insert(name.clone());
                }
            }
        }
        crate::merge_toml_values(base, overlay);
        replaced
    }
}

#[cfg(test)]
#[path = "project_mcp_tests.rs"]
mod tests;
