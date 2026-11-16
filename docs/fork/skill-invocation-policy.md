# Skill 策略维护契约

范围：本地 skill 声明兼容和用户配置覆盖，包括 host、executor 和插件技能。
核对日期：2026-11-16；工作区版本：`0.169.0`。
关键词：skills、policy、frontmatter、projects、executor、plugins、cache。
配置示例见 [中文使用手册](usage/skills.md)。

## 声明解析

先解析 skill 自身的调用策略：

| `agents/openai.yaml` 的 `policy.allow_implicit_invocation` | `SKILL.md` 的 `disable-model-invocation` | 自动调用 |
| --- | --- | --- |
| `true` | 任意或缺失 | 允许 |
| `false` | 任意或缺失 | 禁止 |
| 缺失 | `true` | 禁止 |
| 缺失 | `false` 或缺失 | 允许 |

Frontmatter 字段只接受可选 YAML 布尔值；`null` 按未设置处理。
可选 `openai.yaml` 不可读或无效时沿用原有忽略并警告行为，再使用 frontmatter 回退。
回退只补充缺失的调用字段，保留 products、dependencies 和 interface 等其他元数据。

## 本地覆盖

策略顺序为：声明解析结果、用户全局规则、选中的工作区规则、会话规则。
覆盖按字段进行；省略的 enabled、policy 或策略字段继承旧值。
空 policy 不改变任何字段；products 整体替换，空列表清除产品限制。
调用策略、产品过滤、启用状态相互独立。

每条规则恰好选择 name 或绝对 SKILL.md path。name 按最终目录名称精确、区分大小写匹配，
包括插件命名空间；多个同名副本都会匹配。按顺序处理重复选择器，后面的规则只覆盖显式字段。
不能让仅覆盖 policy 的后续条目抹去已有 enabled 或 products 决定。

工作区复用已有 projects 键选择规则：cwd、规范路径、仓库根查找；
cwd 项目条目整体优先于仓库条目，不任意继承父目录或嵌套项目。
同一项目键在用户、profile 和会话层间保留字段继承。
只读取用户和会话来源的单个 skill 规则；项目 `.codex/config.toml` 不参与该覆盖。
角色文件保持只能禁用的权限，不能替换父级调用或产品策略。

## 发现、过滤与缓存

| 源码 | 责任 |
| --- | --- |
| [`skills/src/parser.rs`](../../codex-rs/skills/src/parser.rs) | 共享 frontmatter 解析和声明策略回退 |
| [`config/src/skills_config.rs`](../../codex-rs/config/src/skills_config.rs) | 选择器、范围顺序、项目键选择和按字段覆盖 |
| [`ext/skills/src/loader/host_merge.rs`](../../codex-rs/ext/skills/src/loader/host_merge.rs) | host 合并后策略覆盖 |
| [`ext/skills/src/loader/environment.rs`](../../codex-rs/ext/skills/src/loader/environment.rs) | 环境扫描、V1/V2 发现策略处理 |
| [`exec-server/src/discoverV2/capability_discoveries.rs`](../../codex-rs/exec-server/src/discoverV2/capability_discoveries.rs) | 独立 executor 的 V2 声明元数据解析 |
| [`core-plugins/src/loader.rs`](../../codex-rs/core-plugins/src/loader.rs) | 保留原始清单，在有效策略就绪后过滤产品并处理命令优先级 |
| [`core/src/config/edit.rs`](../../codex-rs/core/src/config/edit.rs) | 切换启用状态时保留 policy、内联数组和重复规则 |

本地覆盖在命名空间解析之后、产品过滤之前应用。
host、executor 各发现路径和插件的缓存身份都需要包含有效规则。
共享解析快照保留来源原始策略；覆盖不得写回 skill 文件或 executor 发现源。
host 快照向 executor 目录准备传递当前工作区规则。
本地规则并不改写 executor 自身配置。

## 验证入口与限制

测试覆盖选择器顺序、字段继承、工作区隔离、插件命名空间、缓存身份、三条 executor
发现路径一致性、配置编辑保留字段以及角色权限。
源文件分别为 `config/src/skills_config_tests.rs`、`ext/skills` 中的 loader/provider 测试、
`core-plugins` 的 loader 测试及 `core/src/config/edit_tests.rs`。

本地覆盖不取消插件市场级安装或产品限制，不控制冻结的 Cloud skill provider。
外部路径工作区仍受现有 native-cwd loader 契约限制。
发布包必须同时包含 fork CLI 和独立 executor；打包契约见 [构建与发布](release-management.md)。

只读核对：

```sh
rg -n 'SkillPolicyOverride|apply_policy|ConfigLayerSource::User|project' codex-rs/config/src/skills_config.rs
rg -n 'disable_model_invocation|allow_implicit_invocation' codex-rs/skills/src/parser.rs
git diff --check
```

在约定的构建环境中，从仓库根目录执行对应测试：

```sh
cargo nextest run --manifest-path codex-rs/Cargo.toml -p codex-config -p codex-skills-extension -p codex-core-plugins -p codex-skills --lib --offline -E 'package(codex-config) & (test(skills_config) | test(project_trust) | test(deserialize_skill)) | package(codex-skills-extension) & (test(loader::) | test(host_service) | test(provider::) | test(policy_cache)) | package(codex-core-plugins) & (test(loader) | test(plugin_cache_identity)) | package(codex-skills)'
cargo nextest run --manifest-path codex-rs/Cargo.toml -p codex-skills-extension --test executor_file_system_authority --test skills_extension --offline -E 'test(executor_discovery_routes_produce_equivalent_catalog_metadata) | test(v2_)'
cargo nextest run --manifest-path codex-rs/Cargo.toml -p codex-core --lib --offline -E 'test(config::edit::tests::) | test(apply_role_skills_config_disables_skill_for_spawned_agent)'
```

以上保留验证方式，不作为本次文档整理重新执行测试的声明。
