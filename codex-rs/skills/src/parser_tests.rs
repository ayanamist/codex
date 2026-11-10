use pretty_assertions::assert_eq;

use super::ParsedSkillFrontmatter;
use super::parse_skill_frontmatter_metadata;

#[test]
fn parses_repairs_and_sanitizes_frontmatter() {
    let parsed = parse_skill_frontmatter_metadata(
        "---\nname:  deploy  service\ndescription: Build for AWS: ECS\nmetadata:\n  short-description:  Deploy   safely\n---\n",
        || "fallback".to_string(),
    )
    .expect("valid frontmatter");

    assert_eq!(
        parsed,
        ParsedSkillFrontmatter {
            name: "deploy service".to_string(),
            description: "Build for AWS: ECS".to_string(),
            short_description: Some("Deploy safely".to_string()),
            disable_model_invocation: None,
        }
    );
}

#[test]
fn uses_default_name_and_requires_description() {
    let parsed = parse_skill_frontmatter_metadata("---\ndescription: Demo skill\n---\n", || {
        "demo".to_string()
    })
    .expect("valid frontmatter");
    assert_eq!(
        parsed,
        ParsedSkillFrontmatter {
            name: "demo".to_string(),
            description: "Demo skill".to_string(),
            short_description: None,
            disable_model_invocation: None,
        }
    );

    let error =
        parse_skill_frontmatter_metadata("---\nname: demo\n---\n", || "fallback".to_string())
            .expect_err("description should be required");
    assert_eq!(error.to_string(), "missing field `description`");
}

#[test]
fn repairs_short_descriptions_containing_colons_and_apostrophes() {
    let parsed = parse_skill_frontmatter_metadata(
        "---\nname: short\ndescription: Short skill\nmetadata:\n  short-description: What's included: builds and tests\n---\n",
        || "fallback".to_string(),
    )
    .expect("frontmatter with an unquoted short description should be repaired");

    assert_eq!(
        parsed,
        ParsedSkillFrontmatter {
            name: "short".to_string(),
            description: "Short skill".to_string(),
            short_description: Some("What's included: builds and tests".to_string()),
            disable_model_invocation: None,
        }
    );
}

#[test]
fn repairs_unrecognized_frontmatter_fields_that_need_quotes() {
    let parsed = parse_skill_frontmatter_metadata(
        "---\nname: unknown\ndescription: Unknown fields\nargument-hint: <duration: e.g. 7d, 2w>\ntags: [next,@supabase/ssr]\n---\n",
        || "fallback".to_string(),
    )
    .expect("frontmatter with unrecognized fields should be repaired");

    assert_eq!(
        parsed,
        ParsedSkillFrontmatter {
            name: "unknown".to_string(),
            description: "Unknown fields".to_string(),
            short_description: None,
            disable_model_invocation: None,
        }
    );
}

#[test]
fn preserves_block_scalar_bodies_while_repairing_other_fields() {
    let parsed = parse_skill_frontmatter_metadata(
        "---\nname: block\ndescription: |-\n  Build for AWS: ECS\nargument-hint: <duration: e.g. 7d>\n---\n",
        || "fallback".to_string(),
    )
    .expect("frontmatter repair should preserve block scalar bodies");

    assert_eq!(
        parsed,
        ParsedSkillFrontmatter {
            name: "block".to_string(),
            description: "Build for AWS: ECS".to_string(),
            short_description: None,
            disable_model_invocation: None,
        }
    );
}

#[test]
fn preserves_overlong_descriptions_and_short_descriptions() {
    let description = "💡".repeat(/*n*/ 1_025);
    let short_description = "x".repeat(/*n*/ 1_025);
    let parsed = parse_skill_frontmatter_metadata(
        &format!(
            "---\nname: long\ndescription: {description}\nmetadata:\n  short-description: {short_description}\n---\n"
        ),
        || "fallback".to_string(),
    )
    .expect("descriptions should not be truncated during frontmatter parsing");

    assert_eq!(
        parsed,
        ParsedSkillFrontmatter {
            name: "long".to_string(),
            description,
            short_description: Some(short_description),
            disable_model_invocation: None,
        }
    );
}

#[test]
fn invocation_policy_prefers_metadata_then_frontmatter_then_default() {
    use crate::SkillPolicy;
    use crate::parse_skill_metadata;

    for disable_model_invocation in [None, Some(false), Some(true)] {
        let field = disable_model_invocation
            .map(|value| format!("disable-model-invocation: {value}\n"))
            .unwrap_or_default();
        let parsed = parse_skill_frontmatter_metadata(
            &format!("---\nname: demo\ndescription: Demo skill\n{field}---\n"),
            || "fallback".to_string(),
        )
        .expect("valid frontmatter");
        assert_eq!(parsed.disable_model_invocation, disable_model_invocation);

        for metadata in [
            "{}",
            "interface: {display_name: Demo}",
            "policy: {}",
            "policy: {products: [codex]}",
            "policy: {allow_implicit_invocation: true, products: [codex]}",
            "policy: {allow_implicit_invocation: false, products: [codex]}",
        ] {
            let policy = parse_skill_metadata(metadata)
                .expect("valid metadata")
                .policy;
            let expected_invocation = policy
                .as_ref()
                .and_then(|policy| policy.allow_implicit_invocation)
                .or(disable_model_invocation.map(|disable| !disable));
            let products = policy
                .as_ref()
                .map(|policy| policy.products.clone())
                .unwrap_or_default();
            let expected =
                (policy.is_some() || disable_model_invocation.is_some()).then_some(SkillPolicy {
                    allow_implicit_invocation: expected_invocation,
                    products,
                });
            assert_eq!(parsed.resolve_policy(policy), expected, "{field}{metadata}");
        }
    }
}

#[test]
fn rejects_non_boolean_disable_model_invocation() {
    for value in ["'true'", "1", "[]", "{}", "sometimes"] {
        let error = parse_skill_frontmatter_metadata(
            &format!(
                "---\nname: demo\ndescription: Demo skill\ndisable-model-invocation: {value}\n---\n"
            ),
            || "fallback".to_string(),
        )
        .expect_err("invocation flag must be a boolean");
        assert!(error.to_string().contains("invalid YAML"));
    }
}
