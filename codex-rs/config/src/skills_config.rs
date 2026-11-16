//! Skill-related configuration types shared across crates.

use std::collections::HashSet;
use std::num::NonZeroUsize;

use crate::ConfigLayerSource;
use crate::ConfigLayerStack;
use crate::config_toml::ProjectConfig;
use codex_protocol::protocol::Product;
use codex_skills::SkillPolicy;
use codex_utils_absolute_path::AbsolutePathBuf;
use codex_utils_path_uri::PathUri;
use schemars::JsonSchema;
use serde::Deserialize;
use serde::Serialize;
use tracing::warn;

const fn default_enabled() -> bool {
    true
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq, JsonSchema)]
#[schemars(deny_unknown_fields)]
pub struct SkillConfig {
    /// Path-based selector.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path: Option<AbsolutePathBuf>,
    /// Name-based selector.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub enabled: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub policy: Option<SkillPolicyOverride>,
}

/// Field-level overrides; absence inherits and an empty products list removes restrictions.
#[derive(Serialize, Deserialize, Debug, Clone, Default, PartialEq, Eq, Hash, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SkillPolicyOverride {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub allow_implicit_invocation: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub products: Option<Vec<Product>>,
}

/// Per-project skill rules stored alongside the existing project trust setting.
#[derive(Serialize, Deserialize, Debug, Clone, Default, PartialEq, Eq, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ProjectSkillsConfig {
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub config: Vec<SkillConfig>,
}

/// Skills required from one environment or plugin before inference.
#[derive(Serialize, Deserialize, Debug, Clone, Default, PartialEq, Eq, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ScopedSkillsConfig {
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub required: Vec<String>,
}

#[derive(Serialize, Deserialize, Debug, Clone, Default, PartialEq, Eq, JsonSchema)]
#[schemars(deny_unknown_fields)]
pub struct SkillsConfig {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bundled: Option<BundledSkillsConfig>,

    /// Whether turns receive the automatic skills instructions block.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub include_instructions: Option<bool>,

    /// Maximum tokens used by the available-skills catalog. Defaults to 2% of
    /// the model context window and is capped at 10,000 tokens when set.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_context_tokens: Option<NonZeroUsize>,

    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub config: Vec<SkillConfig>,
}

#[derive(Serialize, Deserialize, Debug, Clone, PartialEq, Eq, JsonSchema)]
#[schemars(deny_unknown_fields)]
pub struct BundledSkillsConfig {
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

impl Default for BundledSkillsConfig {
    fn default() -> Self {
        Self { enabled: true }
    }
}

impl TryFrom<toml::Value> for SkillsConfig {
    type Error = toml::de::Error;

    fn try_from(value: toml::Value) -> Result<Self, Self::Error> {
        SkillsConfig::deserialize(value)
    }
}

/// Selects configured skills by their name or canonical document path.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum SkillConfigRuleSelector {
    Name(String),
    Path(PathUri),
}

/// Enables or disables every skill matched by its selector.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct SkillConfigRule {
    pub selector: SkillConfigRuleSelector,
    pub enabled: Option<bool>,
    pub policy: Option<SkillPolicyOverride>,
}

/// Ordered effective skill enablement rules from configuration layers.
#[derive(Debug, Clone, Default, PartialEq, Eq, Hash)]
pub struct SkillConfigRules {
    pub entries: Vec<SkillConfigRule>,
}

impl SkillConfigRules {
    /// Applies only explicitly configured policy fields, in matching-rule order.
    pub fn apply_policy(&self, name: &str, path: &PathUri, policy: &mut Option<SkillPolicy>) {
        for entry in &self.entries {
            let matches = match &entry.selector {
                SkillConfigRuleSelector::Name(selector) => selector == name,
                SkillConfigRuleSelector::Path(selector) => selector == path,
            };
            let Some(overrides) = entry.policy.as_ref().filter(|_| matches) else {
                continue;
            };
            if overrides.allow_implicit_invocation.is_none() && overrides.products.is_none() {
                continue;
            }
            let policy = policy.get_or_insert_with(SkillPolicy::default);
            if let Some(value) = overrides.allow_implicit_invocation {
                policy.allow_implicit_invocation = Some(value);
            }
            if let Some(value) = &overrides.products {
                policy.products.clone_from(value);
            }
        }
    }

    /// Applies rules in order; later rules override earlier rules for matching skills.
    ///
    /// Explicit path selectors remain effective even when no current skill matches.
    pub fn resolve_disabled_paths<'a>(
        &self,
        skills: impl IntoIterator<Item = (&'a str, &'a PathUri)> + Clone,
    ) -> HashSet<PathUri> {
        let mut disabled_paths = HashSet::new();

        for entry in &self.entries {
            let Some(enabled) = entry.enabled else {
                continue;
            };
            match &entry.selector {
                SkillConfigRuleSelector::Path(path) => {
                    if enabled {
                        disabled_paths.remove(path);
                    } else {
                        disabled_paths.insert(path.clone());
                    }
                }
                SkillConfigRuleSelector::Name(name) => {
                    for (skill_name, path) in skills.clone() {
                        if skill_name != name {
                            continue;
                        }
                        if enabled {
                            disabled_paths.remove(path);
                        } else {
                            disabled_paths.insert(path.clone());
                        }
                    }
                }
            }
        }

        disabled_paths
    }
}

/// Returns whether bundled skills are enabled by the effective configuration.
pub fn bundled_skills_enabled_from_stack(config_layer_stack: &ConfigLayerStack) -> bool {
    let effective_config = config_layer_stack.effective_config();
    let Some(skills_value) = effective_config
        .as_table()
        .and_then(|table| table.get("skills"))
    else {
        return true;
    };

    let skills: SkillsConfig = match skills_value.clone().try_into() {
        Ok(skills) => skills,
        Err(err) => {
            warn!("invalid skills config: {err}");
            return true;
        }
    };

    skills.bundled.unwrap_or_default().enabled
}

/// Resolves skill enablement rules from user and session configuration layers.
pub fn skill_config_rules_from_stack(config_layer_stack: &ConfigLayerStack) -> SkillConfigRules {
    skill_config_rules_with_project(config_layer_stack, None)
}

/// Global rules, then the selected project's rules, then session flags.
/// Keep all entries: dropping a repeated selector would lose omitted-field inheritance
/// and can change ordering relative to a different matching selector.
pub fn skill_config_rules_with_project(
    config_layer_stack: &ConfigLayerStack,
    project: Option<&ProjectConfig>,
) -> SkillConfigRules {
    let mut rules = SkillConfigRules::default();
    for session in [false, true] {
        if session && let Some(skills) = project.and_then(|project| project.skills.as_ref()) {
            append_rules(&mut rules, skills.config.clone());
        }
        for layer in config_layer_stack.all_layers_low_to_high() {
            let applies = if session {
                matches!(layer.name, ConfigLayerSource::SessionFlags)
            } else {
                matches!(layer.name, ConfigLayerSource::User { .. })
            };
            if !applies {
                continue;
            }
            let Some(skills_value) = layer.config.get("skills") else {
                continue;
            };
            match skills_value.clone().try_into() {
                Ok(SkillsConfig { config, .. }) => append_rules(&mut rules, config),
                Err(err) => warn!("invalid skills config: {err}"),
            }
        }
    }
    rules
}

fn append_rules(rules: &mut SkillConfigRules, config: Vec<SkillConfig>) {
    for entry in config {
        let Some(selector) = skill_config_rule_selector(&entry) else {
            continue;
        };
        rules.entries.push(SkillConfigRule {
            selector,
            enabled: entry.enabled,
            policy: entry.policy,
        });
    }
}

/// Reuses the existing cwd/canonical/repository-root project selection contract.
/// Only user and session layers supply local project skill overrides.
pub fn skill_project_for_cwd(
    stack: &ConfigLayerStack,
    cwd: &std::path::Path,
    repo_root: Option<&std::path::Path>,
) -> Option<ProjectConfig> {
    let mut projects = toml::Value::Table(Default::default());
    for layer in stack.all_layers_low_to_high() {
        if matches!(
            layer.name,
            ConfigLayerSource::User { .. } | ConfigLayerSource::SessionFlags
        ) && let Some(value) = layer.config.get("projects")
        {
            let mut overlay = value.clone();
            if let Some(entries) = overlay.as_table_mut() {
                for (key, project) in entries {
                    let previous = projects.get(key).and_then(project_skill_entries);
                    let current = project
                        .get_mut("skills")
                        .and_then(|skills| skills.get_mut("config"))
                        .and_then(toml::Value::as_array_mut);
                    if let (Some(previous), Some(current)) = (previous, current) {
                        *current = previous.iter().chain(current.iter()).cloned().collect();
                    }
                }
            }
            crate::merge_toml_values(&mut projects, &overlay);
        }
    }
    let projects = match projects.try_into() {
        Ok(projects) => projects,
        Err(err) => {
            warn!("invalid project skills config: {err}");
            return None;
        }
    };
    crate::config_toml::ConfigToml {
        projects: Some(projects),
        ..Default::default()
    }
    .get_active_project(cwd, repo_root)
}

fn project_skill_entries(project: &toml::Value) -> Option<&Vec<toml::Value>> {
    project.get("skills")?.get("config")?.as_array()
}

fn skill_config_rule_selector(entry: &SkillConfig) -> Option<SkillConfigRuleSelector> {
    match (entry.path.as_ref(), entry.name.as_deref()) {
        (Some(path), None) => Some(SkillConfigRuleSelector::Path(PathUri::from_abs_path(
            &path.canonicalize().unwrap_or_else(|_| path.clone()),
        ))),
        (None, Some(name)) => {
            let name = name.trim();
            if name.is_empty() {
                warn!("ignoring empty skills.config name override");
                None
            } else {
                Some(SkillConfigRuleSelector::Name(name.to_string()))
            }
        }
        (Some(_), Some(_)) => {
            warn!("ignoring skills.config entry with both path and name selectors");
            None
        }
        (None, None) => {
            warn!("ignoring skills.config entry without a path or name selector");
            None
        }
    }
}

#[cfg(test)]
#[path = "skills_config_tests.rs"]
mod tests;
