use super::*;
use codex_config::SkillConfigRule;
use codex_config::SkillConfigRuleSelector;
use codex_config::SkillConfigRules;
use codex_config::SkillPolicyOverride;
use codex_exec_server::DiscoverV2CapabilitiesResponse;
use codex_exec_server::ExecutorCapabilityDiscoveryV2Snapshot;
use codex_exec_server::ExecutorSkill;
use codex_skills::SkillPolicy;
use codex_utils_path_uri::PathUri;

#[tokio::test]
async fn executor_v2_cache_reprojects_same_discovery_when_workspace_policy_changes() {
    let state = SkillsThreadState::new(
        SkillsExtensionConfig {
            include_instructions: true,
            catalog_deltas_enabled: false,
            omit_descriptions: false,
            max_context_tokens: None,
            bundled_skills_enabled: false,
            cloud_skill_enabled: false,
            shadow_selection_enabled: false,
        },
        false,
        None,
    );
    let providers = SkillProviders::new().with_executor_provider(Arc::new(
        crate::ExecutorSkillProvider::new_with_restriction_product(Some(
            codex_protocol::protocol::Product::Codex,
        )),
    ));
    let snapshots = vec![ExecutorCapabilityDiscoveryV2Snapshot {
        environment_id: "remote".into(),
        result: Ok(Arc::new(DiscoverV2CapabilitiesResponse {
            skills: vec![ExecutorSkill {
                name: "research".into(),
                description: "Research".into(),
                short_description: None,
                path: PathUri::parse("file:///skills/research/SKILL.md").unwrap(),
                discovery_root: None,
                dependencies: None,
                policy: Some(SkillPolicy {
                    allow_implicit_invocation: Some(true),
                    products: vec![],
                }),
            }],
            ..Default::default()
        })),
    }];
    let mut query = SkillListQuery {
        skill_config_rules: SkillConfigRules {
            entries: vec![SkillConfigRule {
                selector: SkillConfigRuleSelector::Name("research".into()),
                enabled: None,
                policy: Some(SkillPolicyOverride {
                    allow_implicit_invocation: Some(false),
                    products: None,
                }),
            }],
        },
        turn_id: "same-turn".into(),
        executor_roots: vec![],
        host_snapshot: None,
        include_host_skills: false,
        include_bundled_skills: false,
        include_cloud_skills: false,
        mcp_resources: None,
        executor_capability_discovery: None,
        executor_capability_discovery_v2: Some(snapshots),
    };
    let hidden = state
        .refresh_executor_catalog(&providers, query.clone())
        .await;
    assert!(!hidden.entries[0].prompt_visible);
    query.skill_config_rules.entries[0]
        .policy
        .as_mut()
        .unwrap()
        .allow_implicit_invocation = Some(true);
    let visible = state
        .refresh_executor_catalog(&providers, query.clone())
        .await;
    assert!(visible.entries[0].prompt_visible);
    query.skill_config_rules.entries[0]
        .policy
        .as_mut()
        .unwrap()
        .products = Some(vec![codex_protocol::protocol::Product::Chatgpt]);
    assert!(
        state
            .refresh_executor_catalog(&providers, query.clone())
            .await
            .entries
            .is_empty()
    );
    query.skill_config_rules.entries[0]
        .policy
        .as_mut()
        .unwrap()
        .products = Some(vec![]);
    assert!(
        state
            .refresh_executor_catalog(&providers, query)
            .await
            .entries[0]
            .prompt_visible
    );
    assert!(!hidden.entries[0].prompt_visible);
}
