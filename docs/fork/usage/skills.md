# Skill 配置

本 fork 支持通过用户配置管理 skill 的启用状态、自动调用策略和产品限制，
也支持在同一份配置中按工作区设置规则。修改后重启 Codex。

## 配置文件位置

编辑 `$CODEX_HOME/config.toml`，默认是 `~/.codex/config.toml`。
下面的全局规则和工作区规则都写在这个用户配置文件中。

工作区规则放在已有的 `[projects."绝对路径"]` 条目下，保留原来的 `trust_level`。
项目自己的 `.codex/config.toml` 中的 `skills.config` 不参与这些单个 skill 的覆盖规则。

## 禁用或启用 skill

按 Codex 技能目录中显示的完整名称禁用：

```toml
[[skills.config]]
name = "research"
enabled = false
```

设为 `enabled = true` 可重新启用。删除这条规则后，会恢复其他匹配规则决定的状态。
名称区分大小写；插件 skill 要包含目录中显示的命名空间，例如 `sample:sample-search`。
按名称匹配会影响所有同名 skill。

只想匹配某一份文件时，使用绝对 `SKILL.md` 路径：

```toml
[[skills.config]]
path = "/absolute/path/to/skill/SKILL.md"
enabled = false
```

每条规则必须且只能设置 `name` 或 `path` 中的一个。

## 保留手动调用，关闭自动调用

```toml
[[skills.config]]
name = "research"
policy = { allow_implicit_invocation = false }
```

这条规则让 skill 保持可用，并关闭模型自动选择它的能力；仍可以通过现有的技能选择方式显式调用。
`enabled = false` 则会禁用它的可用性。
如果前面的规则已禁用该 skill，还需要显式设置 `enabled = true` 才能重新启用。

## 仅在某个工作区允许自动调用

下面是一份完整示例：全局关闭 `research` 自动调用，在指定工作区重新允许，
并在该工作区禁用 `code-review`。

```toml
[[skills.config]]
name = "research"
policy = { allow_implicit_invocation = false, products = ["codex"] }

[projects."/absolute/path/to/project"]
trust_level = "trusted"
skills.config = [
  { name = "research", policy = { allow_implicit_invocation = true } },
  { name = "code-review", enabled = false },
]
```

把示例路径换成实际工作区的绝对路径。如果该项目条目已经存在，直接合并字段，
不要重复声明同名 TOML 表，也不要为了配置 skill 修改已有的信任级别。

工作区选择沿用已有的当前目录、规范路径和仓库根目录查找规则。
如果当前目录有匹配的项目条目，它会优先于仓库根目录条目，即使其中没有 skill 规则。
没有当前目录条目时，Git 子目录可以使用仓库条目；不会任意继承所有父目录项目的规则。

## 规则优先级和继承

规则按以下顺序覆盖：

1. skill 自己声明的策略。
2. 用户配置中的全局 `skills.config`。
3. 当前工作区条目中的 `skills.config`。
4. 会话级 `skills.config` 覆盖。

覆盖按字段进行。省略的 `enabled`、`policy` 或某个策略字段会继承之前的值；
`policy = {}` 不改变策略。同一范围中，后面的匹配规则覆盖前面显式设置的相同字段。
名称规则和路径规则也遵循这个顺序。

`policy.products` 可使用 `codex`、`chatgpt`、`atlas`，后面的列表会整体替换旧列表。
`products = []` 清除 skill 自身的产品限制。
上例的工作区规则只修改自动调用，因此保留全局的 `products = ["codex"]`。
`enabled = true` 不会自动取消调用策略或产品限制。

这些设置适用于本地配置控制的 skill，包括带命名空间的插件 skill；
插件市场本身的安装或产品限制仍单独生效，Cloud 提供的 skill 不在此覆盖范围内。

## Skill 作者如何声明调用策略

在 `SKILL.md` 的 YAML frontmatter 中写入：

```yaml
---
name: example
description: 按用户明确请求执行示例任务。
disable-model-invocation: true
---
```

`true` 表示禁止自动调用，`false` 表示允许，未设置时默认允许。
字段必须是 YAML 布尔值；`null` 按未设置处理。

如果 skill 的 `agents/openai.yaml` 显式设置了以下字段，它优先于 frontmatter：

```yaml
policy:
  allow_implicit_invocation: false
```

用户配置中的策略覆盖在这两种声明解析后应用。
因此，使用者可以在自己的用户配置中调整策略，无需修改已安装的 skill 文件。

维护和发现路径说明见 [Skill 策略契约](../skill-invocation-policy.md)。
