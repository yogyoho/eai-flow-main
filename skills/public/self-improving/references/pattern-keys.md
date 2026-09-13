# Pattern-Key 分类法(area.symptom)

`pattern_key = area.symptom`,两级小写连字符。**reuse-before-mint**:先在 ledger 里 grep 已有 key,近似即复用;只有多个条目会共享时才允许新 symptom。禁止在 key 里放文件名/版本号/主机名。

## Area 枚举(11 个,与平台 schema 同构,勿自造)

| area | 范围 | 常见 symptom 示例 |
|---|---|---|
| `deps` | 包管理/依赖 | module-not-found, npm-error, version-conflict, peer-dep-conflict |
| `fs` | 文件系统 | no-such-file, permission-denied, path-escape |
| `net` | 网络 | connection-refused, timeout, dns-failure, proxy-blocked |
| `shell` | shell/CLI | command-not-found, nonzero-exit, quoting-error |
| `vcs` | git 等版本控制 | fatal-error, merge-conflict, push-rejected |
| `runtime` | 语言运行时错误 | python-exception, syntax-error, type-error, oom |
| `api` | 外部 API/服务行为 | rate-limit, schema-mismatch, missing-endpoint, auth-401 |
| `auth` | 凭据/权限 | token-expired, missing-scope, csrf-failure |
| `build` | 编译/打包/CI | compile-error, missing-artifact, typecheck-failure |
| `config` | 配置/环境变量 | missing-env, invalid-json, wrong-default |
| `tools` / `mcp` | 工具与 MCP 调用 | tool-error, server-down, schema-violation, timeout |
| `skill` / `data` | 技能内容与数据契约 | template-slot-missing, stale-reference, schema-drift |

> 拿不准 area 时:错误发生在哪个层就选哪个层;纯粹"不知道"才允许 `runtime.error` / `runtime.failure`(含义=未分类),triage 时应替换为具体 key。

## 错误文本速查(specific → generic,先匹配上面的,再落到下面的)

| 错误文本含 | pattern_key |
|---|---|
| command not found | shell.command-not-found |
| No such file / ENOENT | fs.no-such-file |
| Permission denied / EACCES | fs.permission-denied |
| ModuleNotFoundError / ImportError | deps.module-not-found |
| npm ERR! / pnpm 报错块 | deps.npm-error |
| Traceback (most recent call last) | runtime.python-exception |
| SyntaxError | runtime.syntax-error |
| TypeError | runtime.type-error |
| fatal: (git) | vcs.fatal-error |
| exit code / non-zero | shell.nonzero-exit |
| MCP tool / server 报错 | mcp.tool-error |
| error:/Error:/ERROR:(兜底) | runtime.error |
| failed / FAILED(兜底) | runtime.failure |

原则:**先具体后兜底**。一条含 `Traceback` 的输出里有 `ModuleNotFoundError`,取 `deps.module-not-found`(specific 胜 generic)。

## 判定不捕获的信号

- 一次性 typo/漏参数且当场修掉
- 纯用户偏好陈述(进 memory,不进 ledger)
- 密钥相关且脱敏后失去诊断价值
