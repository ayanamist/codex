# Skills

For information about skills, refer to [this documentation](https://developers.openai.com/codex/skills).

This fork also supports `disable-model-invocation` in `SKILL.md` YAML frontmatter.
An explicit `policy.allow_implicit_invocation` in `agents/openai.yaml` takes
precedence. When that setting is absent, the frontmatter value is inverted:
`disable-model-invocation: true` disables implicit invocation, and `false` allows
it. When both settings are absent, implicit invocation remains enabled.
Explicit invocation remains available through the existing skill selection path.
See [invocation policy compatibility](fork/skill-invocation-policy.md) for scope,
community references, and verification.
