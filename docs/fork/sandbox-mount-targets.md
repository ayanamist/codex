# Linux 沙箱清理维护契约

范围：Linux bubblewrap 文件系统沙箱的临时挂载点。
核对日期：2026-11-16；工作区版本：`0.169.0`。
关键词：bubblewrap、bwrap、identity、inode、SIGKILL、cleanup。
用户可见行为见 [中文使用手册](usage/linux-sandbox.md)。

## 创建与回收

缺失的受保护元数据路径可能需要在宿主可写 bind mount 下创建空目录，供只读 tmpfs 挂载。
缺失的普通只读子路径也可能需要空文件占位。
监督辅助进程负责注册所有者和回收；最后一个活跃所有者正常退出时执行清理。

辅助程序尝试在启动 bubblewrap 前创建缺失挂载点，文件使用排他创建。
成功创建后，在进程标记旁的 `identity.json` 保存设备号、inode 和纳秒级 ctime，
通过临时文件加 rename 写入，避免暴露半份身份记录。

后续注册即使观察到路径已经存在，只要不存在活跃所有者，且保存身份与当前对象匹配，
就可以回收先前异常退出留下的占位。必须遵守：

- 真实预存对象、被替换对象和修改后的对象保留。
- 文件还必须是空的普通文件，防止粗粒度时间戳漏掉写入。
- 目录只做非递归删除，非空目录不能递归清理。
- 过期 PID 标记不足以证明对象归属。
- 无身份记录时保留原有正常清理语义，但不能据此回收历史遗留对象。

## 源码与限制

| 源码 | 责任 |
| --- | --- |
| [`protocol/src/permissions.rs`](../../codex-rs/protocol/src/permissions.rs) | 工作区及其他可写根下的元数据保护 |
| [`linux-sandbox/src/bwrap.rs`](../../codex-rs/linux-sandbox/src/bwrap.rs) | 构造挂载与占位需求 |
| [`linux-sandbox/src/linux_run_main.rs`](../../codex-rs/linux-sandbox/src/linux_run_main.rs) | 所有者注册、身份记录、监督和回收 |
| [`arg0/src/lib.rs`](../../codex-rs/arg0/src/lib.rs) | CLI 内置 Linux sandbox 别名分派 |

身份记录依赖创建成功后的写入，因此仍存在创建后、记录前被终止的窗口。
没有后台扫描；回收需要后续沙箱再次覆盖相同路径。
PID 存在性检查可能因 PID 复用推迟回收，但不能绕过对象身份检查。
单独配置的沙箱可执行文件必须包含相同实现。

## 核对与测试

```sh
rg -n 'identity.json|cleanup_synthetic_mount_targets|SyntheticMountIdentity' codex-rs/linux-sandbox/src/linux_run_main.rs
git diff --check
```

在约定的构建环境中，从仓库根目录执行对应测试：

```sh
cargo test --offline --manifest-path codex-rs/Cargo.toml -p codex-linux-sandbox --lib cleanup_synthetic_mount_targets -- --nocapture
cargo test --offline --manifest-path codex-rs/Cargo.toml -p codex-linux-sandbox --test all sandbox_reclaims_metadata_mount_targets_after_helper_is_killed -- --nocapture
```

回归应覆盖正常退出、杀死监督进程、再次启动回收、真实数据保留和身份变化。
真实 helper 集成验证需要可用的 bundled 或系统 bubblewrap。
外层沙箱若重映射 app-server socket 目录所有者，可能先触发其独立的权限校验；
嵌套 root fixture 缺少可用 bwrap 时也无法到达预期断言。
这些环境前提需与实现结果分别判断。本次文档整理未重新运行编译测试。
