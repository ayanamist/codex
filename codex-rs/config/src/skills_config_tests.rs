use crate::CONFIG_TOML_FILE;
use crate::ConfigLayerEntry;
use crate::ConfigLayerSource;
use crate::ConfigLayerStack;
use crate::ConfigRequirementsToml;
use codex_utils_absolute_path::AbsolutePathBuf;
use codex_utils_absolute_path::test_support::PathBufExt;
use codex_utils_path_uri::PathUri;
use pretty_assertions::assert_eq;
use tempfile::TempDir;

use super::SkillConfigRule;
use super::SkillConfigRuleSelector;
use super::SkillConfigRules;
use super::bundled_skills_enabled_from_stack;
use super::skill_config_rules_from_stack;

fn user_layer(codex_home: &TempDir, config: &str) -> ConfigLayerEntry {
    let config_path = AbsolutePathBuf::try_from(codex_home.path().join(CONFIG_TOML_FILE))
        .expect("absolute config path");
    ConfigLayerEntry::new(
        ConfigLayerSource::User {
            file: config_path,
            profile: None,
        },
        toml::from_str(config).expect("valid user config"),
    )
}

fn stack(codex_home: &TempDir, user: &str, session: &str) -> ConfigLayerStack {
    ConfigLayerStack::new(
        vec![
            user_layer(codex_home, user),
            ConfigLayerEntry::new(
                ConfigLayerSource::SessionFlags,
                toml::from_str(session).expect("valid session config"),
            ),
        ],
        Default::default(),
        ConfigRequirementsToml::default(),
    )
    .expect("valid config stack")
}

fn path_toggle_config(path: &std::path::Path, enabled: bool) -> String {
    let path = toml::Value::String(path.display().to_string());
    format!(
        r#"[[skills.config]]
path = {path}
enabled = {enabled}
"#
    )
}

#[test]
fn bundled_skills_follow_effective_configuration() {
    let codex_home = TempDir::new().expect("temp dir");

    assert!(bundled_skills_enabled_from_stack(&stack(
        &codex_home,
        "",
        ""
    )));
    assert!(!bundled_skills_enabled_from_stack(&stack(
        &codex_home,
        "[skills.bundled]\nenabled = false\n",
        ""
    )));
    assert!(bundled_skills_enabled_from_stack(&stack(
        &codex_home,
        "[skills.bundled]\nenabled = false\n",
        "[skills.bundled]\nenabled = true\n"
    )));
}

#[test]
fn malformed_bundled_skills_config_defaults_to_enabled() {
    let codex_home = TempDir::new().expect("temp dir");

    assert!(bundled_skills_enabled_from_stack(&stack(
        &codex_home,
        "[skills]\nbundled = 'invalid'\n",
        ""
    )));
}

#[test]
fn session_flags_override_user_enablement() {
    let home = TempDir::new().unwrap();
    let path = home.path().join("skills/demo/SKILL.md");
    let uri = PathUri::from_abs_path(&path.abs());
    for enabled in [false, true] {
        let rules = skill_config_rules_from_stack(&stack(
            &home,
            &path_toggle_config(&path, !enabled),
            &path_toggle_config(&path, enabled),
        ));
        assert_eq!(
            rules
                .resolve_disabled_paths([("demo", &uri)])
                .contains(&uri),
            !enabled
        );
    }
}

#[test]
fn preserves_name_selectors() {
    let codex_home = TempDir::new().expect("temp dir");

    assert_eq!(
        skill_config_rules_from_stack(&stack(
            &codex_home,
            r#"
[[skills.config]]
name = "github:yeet"
enabled = false
"#,
            "",
        )),
        SkillConfigRules {
            entries: vec![SkillConfigRule {
                selector: SkillConfigRuleSelector::Name("github:yeet".to_string()),
                enabled: Some(false),
                policy: None,
            }],
        }
    );
}

#[test]
fn preserves_order_across_path_and_name_selectors() {
    let codex_home = TempDir::new().expect("temp dir");
    let skill_path = codex_home.path().join("skills/demo/SKILL.md");

    assert_eq!(
        skill_config_rules_from_stack(&stack(
            &codex_home,
            &path_toggle_config(&skill_path, /*enabled*/ false),
            r#"
[[skills.config]]
name = "github:yeet"
enabled = true
"#,
        )),
        SkillConfigRules {
            entries: vec![
                SkillConfigRule {
                    selector: SkillConfigRuleSelector::Path(PathUri::from_abs_path(
                        &skill_path.abs()
                    )),
                    enabled: Some(false),
                    policy: None,
                },
                SkillConfigRule {
                    selector: SkillConfigRuleSelector::Name("github:yeet".to_string()),
                    enabled: Some(true),
                    policy: None,
                },
            ],
        }
    );
}

#[test]
fn path_rule_disables_selected_path() {
    let codex_home = TempDir::new().expect("temp dir");
    let path = codex_home.path().join("disable-by-path/SKILL.md").abs();
    let rules = SkillConfigRules {
        entries: vec![SkillConfigRule {
            selector: SkillConfigRuleSelector::Path(PathUri::from_abs_path(&path)),
            enabled: Some(false),
            policy: None,
        }],
    };

    assert_eq!(
        rules.resolve_disabled_paths(std::iter::empty()),
        [PathUri::from_abs_path(&path)].into_iter().collect()
    );
}

#[test]
fn later_name_rule_reenables_path_disabled_skill() {
    let codex_home = TempDir::new().expect("temp dir");
    let path = codex_home.path().join("reenable-by-name/SKILL.md").abs();
    let rules = SkillConfigRules {
        entries: vec![
            SkillConfigRule {
                selector: SkillConfigRuleSelector::Path(PathUri::from_abs_path(&path)),
                enabled: Some(false),
                policy: None,
            },
            SkillConfigRule {
                selector: SkillConfigRuleSelector::Name("demo".to_string()),
                enabled: Some(true),
                policy: None,
            },
        ],
    };

    assert_eq!(
        rules.resolve_disabled_paths([("demo", &PathUri::from_abs_path(&path))]),
        Default::default()
    );
}

#[test]
fn later_path_rule_reenables_one_skill_disabled_by_name() {
    let codex_home = TempDir::new().expect("temp dir");
    let root = codex_home.path().join("reenable-by-path");
    let first_path = root.join("first/SKILL.md").abs();
    let second_path = root.join("second/SKILL.md").abs();
    let rules = SkillConfigRules {
        entries: vec![
            SkillConfigRule {
                selector: SkillConfigRuleSelector::Name("demo".to_string()),
                enabled: Some(false),
                policy: None,
            },
            SkillConfigRule {
                selector: SkillConfigRuleSelector::Path(PathUri::from_abs_path(&first_path)),
                enabled: Some(true),
                policy: None,
            },
        ],
    };

    assert_eq!(
        rules.resolve_disabled_paths([
            ("demo", &PathUri::from_abs_path(&first_path)),
            ("demo", &PathUri::from_abs_path(&second_path)),
        ]),
        [PathUri::from_abs_path(&second_path)].into_iter().collect()
    );
}

fn rules_for_project(
    stack: &ConfigLayerStack,
    cwd: &std::path::Path,
    root: Option<&std::path::Path>,
) -> SkillConfigRules {
    let project = super::skill_project_for_cwd(stack, cwd, root);
    super::skill_config_rules_with_project(stack, project.as_ref())
}

#[test]
fn policy_overrides_merge_fields_across_global_project_and_session() {
    use codex_protocol::protocol::Product;
    use codex_skills::SkillPolicy;
    let home = TempDir::new().unwrap();
    let cwd = home.path().join("project");
    let key = toml::Value::String(cwd.display().to_string());
    let stack = stack(
        &home,
        &format!(
            r#"
[[skills.config]]
name = "demo"
enabled = false
policy = {{ allow_implicit_invocation = false, products = ["codex"] }}
[projects.{key}]
skills.config = [{{ name = "demo", enabled = true, policy = {{ allow_implicit_invocation = true }} }}]
"#
        ),
        r#"
[[skills.config]]
name = "demo"
policy = { products = [] }
"#,
    );
    let rules = rules_for_project(&stack, &cwd, None);
    let path = PathUri::from_abs_path(&cwd.join("SKILL.md").abs());
    let mut policy = Some(SkillPolicy {
        allow_implicit_invocation: Some(false),
        products: vec![Product::Chatgpt],
    });
    rules.apply_policy("demo", &path, &mut policy);
    assert_eq!(
        policy,
        Some(SkillPolicy {
            allow_implicit_invocation: Some(true),
            products: vec![]
        })
    );
    assert!(rules.resolve_disabled_paths([("demo", &path)]).is_empty());
    let other = rules_for_project(&stack, &home.path().join("other"), None);
    other.apply_policy("demo", &path, &mut policy);
    assert_eq!(
        policy.as_ref().unwrap().allow_implicit_invocation,
        Some(false)
    );
    assert!(
        other
            .resolve_disabled_paths([("demo", &path)])
            .contains(&path)
    );
}

#[test]
fn repeated_selectors_preserve_omitted_fields_and_mixed_selector_order() {
    use codex_protocol::protocol::Product;
    let home = TempDir::new().unwrap();
    let path = home.path().join("skills/demo/SKILL.md").abs();
    let quoted = toml::Value::String(path.display().to_string());
    let config = format!(
        r#"
[[skills.config]]
name = "demo"
enabled = false
policy = {{ allow_implicit_invocation = false, products = ["chatgpt"] }}
[[skills.config]]
path = {quoted}
policy = {{ products = ["codex"] }}
[[skills.config]]
name = "demo"
policy = {{ allow_implicit_invocation = true }}
"#
    );
    let rules = skill_config_rules_from_stack(&stack(&home, &config, ""));
    let path = PathUri::from_abs_path(&path);
    let mut policy = None;
    rules.apply_policy("demo", &path, &mut policy);
    let policy = policy.unwrap();
    assert_eq!(policy.allow_implicit_invocation, Some(true));
    assert_eq!(policy.products, vec![Product::Codex]);
    assert!(
        rules
            .resolve_disabled_paths([("demo", &path)])
            .contains(&path)
    );
    let mut untouched = None;
    rules.apply_policy(
        "other",
        &PathUri::from_abs_path(&home.path().join("other").abs()),
        &mut untouched,
    );
    assert_eq!(untouched, None);
}

#[test]
fn project_selection_reuses_cwd_then_repository_without_parent_inheritance() {
    let home = TempDir::new().unwrap();
    let root = home.path().join("repo");
    let cwd = root.join("src");
    let quote = |path: &std::path::Path| toml::Value::String(path.display().to_string());
    let root_key = quote(&root);
    let cwd_key = quote(&cwd);
    let parent_key = quote(home.path());
    let config = format!(
        r#"
[projects.{parent_key}]
skills.config = [{{ name = "parent", enabled = false }}]
[projects.{root_key}]
skills.config = [{{ name = "root", enabled = false }}]
[projects.{cwd_key}]
trust_level = "trusted"
"#
    );
    let config = stack(&home, &config, "");
    // An existing cwd entry is selected as a whole, even without skill rules.
    assert!(
        rules_for_project(&config, &cwd, Some(&root))
            .entries
            .is_empty()
    );
    let rules = rules_for_project(&config, &root.join("other"), Some(&root));
    assert_eq!(
        rules.entries[0].selector,
        SkillConfigRuleSelector::Name("root".into())
    );
    assert!(
        rules_for_project(&config, &home.path().join("unrelated"), None)
            .entries
            .is_empty()
    );
}

#[test]
fn policy_only_entries_inherit_enablement_and_other_policy_fields() {
    use codex_protocol::protocol::Product;
    use codex_skills::SkillPolicy;
    let home = TempDir::new().unwrap();
    let rules = skill_config_rules_from_stack(&stack(
        &home,
        r#"
[[skills.config]]
name = "demo"
policy = { allow_implicit_invocation = false }
"#,
        "",
    ));
    let path = PathUri::from_abs_path(&home.path().join("SKILL.md").abs());
    let mut policy = Some(SkillPolicy {
        allow_implicit_invocation: Some(true),
        products: vec![Product::Codex],
    });
    rules.apply_policy("demo", &path, &mut policy);
    assert_eq!(
        policy.unwrap(),
        SkillPolicy {
            allow_implicit_invocation: Some(false),
            products: vec![Product::Codex]
        }
    );
    assert!(rules.resolve_disabled_paths([("demo", &path)]).is_empty());
}

#[test]
fn invalid_policy_fields_and_types_are_rejected() {
    for config in [
        "name='demo'\npolicy={allow_implicit_invocation='false'}",
        "name='demo'\npolicy={products=['unknown-product']}",
        "name='demo'\npolicy={unknown_field=true}",
    ] {
        assert!(
            toml::from_str::<super::SkillConfig>(config).is_err(),
            "{config}"
        );
    }
}

#[cfg(unix)]
#[test]
fn project_selection_preserves_canonical_path_preference() {
    let home = TempDir::new().unwrap();
    let root = home.path().join("repo");
    std::fs::create_dir(&root).unwrap();
    let alias = home.path().join("alias");
    std::os::unix::fs::symlink(&root, &alias).unwrap();
    let root_key = toml::Value::String(root.display().to_string());
    let alias_key = toml::Value::String(alias.display().to_string());
    let config = stack(
        &home,
        &format!(
            r#"
[projects.{root_key}]
skills.config = [{{ name = "canonical", enabled = false }}]
[projects.{alias_key}]
skills.config = [{{ name = "alias", enabled = false }}]
"#
        ),
        "",
    );
    assert_eq!(
        rules_for_project(&config, &alias, None).entries[0].selector,
        SkillConfigRuleSelector::Name("canonical".into())
    );
}

#[test]
fn repeated_project_rules_across_layers_inherit_each_field() {
    use codex_protocol::protocol::Product;
    let home = TempDir::new().unwrap();
    let cwd = home.path().join("repo");
    let key = toml::Value::String(cwd.display().to_string());
    let config = stack(
        &home,
        &format!(
            r#"
[projects.{key}]
skills.config = [{{ name = "demo", enabled = false, policy = {{ products = ["codex"], allow_implicit_invocation = false }} }}]
"#
        ),
        &format!(
            r#"
[projects.{key}]
skills.config = [{{ name = "demo", policy = {{ allow_implicit_invocation = true }} }}]
"#
        ),
    );
    let rules = rules_for_project(&config, &cwd, None);
    let path = PathUri::from_abs_path(&cwd.join("SKILL.md").abs());
    let mut policy = None;
    rules.apply_policy("demo", &path, &mut policy);
    assert_eq!(
        policy.unwrap(),
        codex_skills::SkillPolicy {
            allow_implicit_invocation: Some(true),
            products: vec![Product::Codex]
        }
    );
    assert!(
        rules
            .resolve_disabled_paths([("demo", &path)])
            .contains(&path)
    );
}

#[test]
fn project_local_layers_do_not_supply_local_skill_overrides() {
    let home = TempDir::new().unwrap();
    let cwd = home.path().join("repo").abs();
    let key = toml::Value::String(cwd.display().to_string());
    let config = ConfigLayerStack::new(
        vec![
            user_layer(&home, ""),
            ConfigLayerEntry::new(
                ConfigLayerSource::Project {
                    dot_codex_folder: cwd.join(".codex"),
                },
                toml::from_str(&format!(
                    r#"
[[skills.config]]
name = "demo"
policy = {{ allow_implicit_invocation = false }}
[projects.{key}]
skills.config = [{{ name = "demo", enabled = false }}]
"#
                ))
                .unwrap(),
            ),
        ],
        Default::default(),
        ConfigRequirementsToml::default(),
    )
    .unwrap();
    assert!(
        rules_for_project(&config, cwd.as_path(), None)
            .entries
            .is_empty()
    );
}
