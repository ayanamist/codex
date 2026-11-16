# 项目 MCP 配置

本 fork 可以直接读取受信任项目中的 `.mcp.json`。已有此文件的项目可以继续使用它，
无需先导入到 `.codex/config.toml`。

## 配置本地进程

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "example": {
      "command": "node",
      "args": ["./tools/mcp-server.js"],
      "env": {
        "SERVICE_MODE": "development"
      }
    }
  }
}
```

示例要求机器上已有 `node`，项目中已有对应服务脚本。将它们替换为实际服务的命令和参数。
启动 Codex 并通过现有的项目信任流程确认项目后，配置才可参与服务启动。

本地进程的默认工作目录是声明该服务的 `.mcp.json` 所在目录。
因此，从项目子目录启动 Codex 时，上例中的脚本仍以配置文件所在目录为基准。
可以设置 `cwd`；相对 `cwd` 也以配置文件所在目录为基准。
不带路径的命令通过执行环境的 `PATH` 查找。

## 配置 HTTP 服务

```json
{
  "mcpServers": {
    "api": {
      "type": "http",
      "url": "${MCP_BASE_URL:-https://example.com}/mcp",
      "headers": {
        "Authorization": "Bearer ${MCP_TOKEN}"
      }
    }
  }
}
```

将示例地址换成实际 MCP 地址，并在运行服务连接的主机环境中提供 `MCP_TOKEN`。
已有的 Codex OAuth 登录流程仍可使用。

支持的传输类型如下：

| 服务 | 配置方式 |
| --- | --- |
| 本地进程 | `command`，可省略 `type`，或使用 `stdio`、`local` |
| Streamable HTTP | `url`，可省略 `type`，或使用 `http`、`streamable-http`、`streamable_http` |

同一服务只能选择 `command` 或 `url` 中的一种。旧式 `type: "sse"` 会产生警告并被跳过。

## 环境变量和文件格式

`command`、`args`、`env` 的值、`cwd`、`url` 和 `headers` 的值支持以下替换：

| 写法 | 含义 |
| --- | --- |
| `${VAR}` | 读取环境变量；未设置时跳过该服务并提示变量名 |
| `${VAR:-default}` | 变量未设置时使用默认值；已设置为空字符串时仍使用空字符串 |

变量从实际执行进程或连接服务的主机环境读取。配置诊断不会输出展开后的秘密值。

文件支持注释、末尾逗号和 UTF-8 BOM。也可以省略外层 `mcpServers`，直接写服务名称映射。
一个服务无效时，其他有效服务仍可加载。

## 多份配置如何生效

Codex 从识别到的项目根目录逐级读取到当前工作目录，较近目录中的配置优先。
如果没有识别到项目标记，只读取当前目录范围。

同一服务名的常见优先级为：用户配置、项目根目录配置、较近子目录配置；
同一目录中，`.codex/config.toml` 的优先级高于 `.mcp.json`。
会话覆盖和管理员约束继续生效。

较高优先级的完整 JSON 服务会整体替换同名旧定义，避免从旧服务继承参数或认证头。
原生 TOML 可以用完整连接配置替换 JSON，也可以只增加禁用或工具限制：

```toml
[mcp_servers.example]
enabled = false
```

JSON 中可以使用 `disabled: true` 或 `enabled: false` 禁用服务。
被禁用或无效的高优先级服务不会回退到同名低优先级定义。

## 检查和重新加载

在实际使用的项目目录运行：

```sh
codex mcp list
codex mcp get example
```

修改 `.mcp.json` 后，新建会话或重启 Codex。已有的完整配置刷新路径也会重新读取文件，
目前没有自动文件监视。

遇到警告时，检查服务名、字段类型、环境变量和传输类型。
其他客户端的 `autoApprove`、`alwaysAllow` 等设置不会授予 Codex 权限；
通用 `timeout` 也不会自动猜测单位，请使用 Codex 原生配置中的明确字段。

`codex mcp add` 写入用户全局配置。需要项目共享配置时，直接编辑项目 `.mcp.json`。
插件自带的 `.mcp.json` 和外部客户端配置导入有各自的作用范围。

维护和兼容性边界见 [MCP 配置契约](../project-mcp-configuration.md)。
