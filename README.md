# pCalmd-AI

基于 LLM 的 JavaScript 反混淆工具，[pCalmd](https://github.com/gitpetyr/pCalmd) 的附属组件。

pCalmd-AI 结合大语言模型与 AST 分析，将混淆后的 JavaScript 代码转换为可读的、结构清晰的代码。工具会将源码按语法边界切分为若干 chunk，依次执行多阶段变换（简化、重命名、注释），并在每一步后校验 AST 完整性。

## 特性

- **AST 感知分块** — 不会在函数/类体内部切割，严格尊重语法边界
- **多阶段流水线** — 简化 -> 重命名 -> 注释，每个阶段可独立开关
- **AST 校验** — 每次变换后验证结构完整性，失败自动重试
- **作用域安全重命名** — 通过 Node.js Bridge 调用 Babel 做作用域分析，确保标识符重命名安全
- **多 AI 供应商** — 通过 LiteLLM 支持 Anthropic、OpenAI、Gemini 及自定义端点
- **结构分析** — 无需 AI 调用即可查看文件结构、导入、函数签名和分块计划
- **异步限速** — 可配置的并发数和每分钟请求数

## 环境要求

- Python >= 3.11
- Node.js（用于 Babel Bridge 的作用域分析）

## 安装

```bash
git clone https://github.com/gitpetyr/pCalmd-AI.git
cd pCalmd-AI

# 安装 Python 包（可编辑模式）
pip install -e .

# 安装 Node.js 依赖（Babel Bridge）
cd src/pcalmd/bridge && npm install && cd -

# （可选）安装开发依赖
pip install -e ".[dev]"
```

## 配置

生成默认配置文件：

```bash
pcalmd init-config
```

会在当前目录创建 `config.toml`。在其中填入 API Key，或通过环境变量设置：

```bash
export ANTHROPIC_API_KEY="sk-..."
# 或
export OPENAI_API_KEY="sk-..."
# 或
export GEMINI_API_KEY="..."
```

### config.toml 参考

```toml
[ai]
provider = "anthropic"                  # anthropic / openai / gemini / custom
model = "claude-sonnet-4-20250514"
api_key = ""
# api_base = "http://localhost:8080/v1" # 仅 custom 模式需要
temperature = 0.2
max_tokens = 8192

[chunking]
max_tokens = 3000        # 每个 chunk 发送给 AI 的最大 token 数
context_tokens = 1000    # 上下文预算（导入、签名等）

[pipeline]
simplify = true          # 删除死代码、常量折叠
rename = true            # 重命名混淆标识符
comment = true           # 添加行内注释
explain = false          # 生成代码解释
verify = true            # 变换后 AST 校验
max_retries = 2          # 校验失败重试次数

[rate_limit]
max_concurrent = 3
requests_per_minute = 50

[output]
format = "file"          # file / stdout / diff
suffix = ".deobfuscated"
```

## 使用

### 反混淆

```bash
# 基本用法
pcalmd deobfuscate obfuscated.js

# 指定输出路径
pcalmd deobfuscate obfuscated.js -o clean.js

# 使用其他供应商/模型
pcalmd deobfuscate obfuscated.js -p openai -m gpt-4o

# 跳过特定阶段
pcalmd deobfuscate obfuscated.js --no-rename --no-comment

# 启用代码解释
pcalmd deobfuscate obfuscated.js --explain

# 输出 unified diff
pcalmd deobfuscate obfuscated.js --format diff

# 预览分块方案（不调用 AI）
pcalmd deobfuscate obfuscated.js --dry-run

# 指定配置文件
pcalmd -c my-config.toml deobfuscate obfuscated.js
```

### 结构分析

不调用 AI，仅分析文件结构：

```bash
pcalmd analyze obfuscated.js
```

输出文件指标、导入列表、全局变量、函数签名以及分块计划。

## 工作原理

1. **解析** — tree-sitter 提取顶层代码单元及全局上下文（导入、签名）
2. **分块** — 贪心装箱算法按 token 预算将代码单元分组
3. **变换** — 对每个 chunk 依次执行启用的变换：
   - **简化** — 删除死代码、常量折叠、简化控制流
   - **重命名** — 根据使用模式和 API 调用推断语义化名称
   - **注释** — 为非显而易见的逻辑添加行内注释
4. **校验** — 每次变换后检查 AST 完整性，失败则重试
5. **重组** — 将处理后的 chunk 合并回完整源码，统一应用全局重命名映射

## 项目结构

```
src/pcalmd/
├── cli.py                 # Click CLI 入口
├── config.py              # Pydantic 配置加载
├── pipeline.py            # 流水线编排
├── ai/                    # LiteLLM 供应商、提示词、限速器
├── parser/                # tree-sitter JS 解析器与 AST 类型
├── chunking/              # AST 感知分块与上下文构建
├── transforms/            # 简化、重命名、注释、解释
├── verification/          # AST 校验与全局重命名映射
├── bridge/                # Python-Node.js Bridge（Babel 作用域分析）
└── output/                # 输出格式化（file / stdout / diff）
```

## 许可证

Copyright (c) 2025 Liveless. 本项目基于 [AGPL-3.0](LICENSE) 许可证发布。
