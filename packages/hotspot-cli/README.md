# Hotspot Research CLI

Hotspot Research CLI 是一款面向研究者和深度写作者的交互式选题智能助手。它用 `last30days-safe` 从公开可信来源采集最近 7-30 天信号，再用结构化分析帮助你发现“时效性强、数据有支撑、竞争相对较低”的高价值写作/研究选题，并输出可直接进入写作的《选题情报简报》。

它不是热搜摘要工具。它的核心价值是：用数据说话，降低选题不确定性，把“我该写什么”变成可验证、可比较、可继续深挖的研究输入。

## 安装

支持 Python 3.9+：

```bash
pip install --upgrade hotspot-research-cli
```

如果 shell 找不到 `hotspot-research`，可以直接使用模块入口；CLI 会尝试自动创建 `~/.local/bin/hotspot-research` shim：

```bash
python3 -m hotspot_cli run
python3 -m hotspot_cli doctor --fix-entrypoint
```

## 快速开始

首次使用建议先跑配置向导：

```bash
hotspot-research setup
```

向导会做两件事：

- 引导选择模型服务商并保存 API Key。
- 可选引导配置飞书 CLI、完成用户授权，并保存目标群聊 `chat_id`。

启动交互式选题助手：

```bash
hotspot-research run --output-dir ./briefs
```

启动后会显示一个简洁的状态面板：当前模型、缓存 TTL、工作目录、输出目录，以及常用命令提示。交互中可输入：

- `1-8`：选择一个方向并生成 Markdown 简报。
- `refresh`：换一批和当前会话已展示主题不同的候选方向。
- 自然语言追问：例如 `更细分一点`、`加上中国场景`、`和 browser agent 对比`。CLI 会重新规划检索 query、重新抓取公开证据，再生成新的方向表。
- `q`：退出。

已有想法时，直接验证并生成简报：

```bash
hotspot-research brief "中文大模型安全评测的新兴低竞争切口" \
  --field "中文大模型安全" \
  --output-dir ./briefs
```

查看支持的模型服务商：

```bash
hotspot-research config model list
```

交互式配置模型：

```bash
hotspot-research config model setup
```

也可以通过参数配置：

```bash
hotspot-research config model setup --provider deepseek --model deepseek/deepseek-chat
hotspot-research config model setup --provider openai --model gpt-4o-mini
hotspot-research config model setup --provider anthropic --model claude-3-5-sonnet-latest
hotspot-research config model setup --provider ark --model openai/doubao-1-5-lite-32k-250115
hotspot-research config model setup --provider ollama --model ollama/qwen2.5:14b
hotspot-research config model setup \
  --provider openai-compatible \
  --model openai/your-model-name \
  --base-url https://api.example.com/v1
```

没有模型 API Key 也能运行，CLI 会使用本地规则分析器生成可用简报；配置模型后，细分方向、研究缺口和标题建议会更稳定。

### 模型配置避坑

配置命令会在保存前做真实连通性验证。对 DeepSeek、OpenAI、Anthropic、OpenRouter、SiliconFlow、Moonshot、Qwen、Ark、Ollama 等内置 provider，通常只需要选择 provider 并输入 API Key；`base_url` 和默认模型由 preset 提供。只有 `custom/openai-compatible` 这类自定义接口必须同时提供真实 `--base-url` 和 `--model`。

火山方舟 Ark 用户请选择 `ark` 预设：

```bash
hotspot-research config model setup --provider ark
hotspot-research config model verify
hotspot-research config model models --provider ark
hotspot-research config model doctor
```

Ark 的 OpenAI-Compatible Base URL 应为 `https://ark.cn-beijing.volces.com/api/v3`。如果误填 `https://ark.cn-beijing.volces.com/api/coding`，CLI 会自动修正为 `/api/v3`；如果模型名仍是 `openai/your-model-name`，CLI 会替换为已验证可用的默认 Doubao 模型。

缓存相关命令：

```bash
hotspot-research config cache show
hotspot-research config cache set --ttl-hours 6
hotspot-research config cache clear
```

缓存只用于减少重复抓取。SQLite 缓存只读或损坏时不会中断主流程，可用 `config cache clear` 清理后重试。

## 默认交互流程

### 流程一：没思路时发现新兴高价值选题

1. CLI 用普通语言询问你如何开始：手动输入领域、让工具推荐近期高价值 AI 选题、偏学术论文方向、偏产业产品/开源方向。
2. 当前配置的大模型会先规划检索 query；手动输入围绕用户关注点检索，默认推荐检索综合 AI 热点，学术/产业模式分别偏向论文评测或产品开源信号。
3. `last30days-safe` 拉取最近 7-30 天公开信号，来源包括 Hacker News、GitHub、Reddit、Polymarket，以及包内保留的 arXiv/GitHub/HN 二次信号能力。
4. LLM 或本地规则分析器提炼 5-8 个具体细分方向，而不是泛泛的“多模态大模型”。
5. Rich 表格展示：
   - 吸引人的选题名称
   - 为什么现在热门的一句话与数据证据
   - 竞争程度信号
   - 2-3 篇近期代表性热点标题、来源和链接
6. 你可以输入序号选择，也可以输入 `refresh` 换一批，或自然语言继续追问，例如 `详细说说第 3 个`、`找更细分的子方向`、`加上中国场景`、`和 XXX 对比一下`。

### 流程二：深入分析并生成《选题情报简报》

选中方向后，CLI 会继续查询不同时间窗口并生成简报：

- 最近 7 天热度
- 最近 30 天热度
- 30-60 天前对照信号
- 趋势判断：上升、平稳、下降或数据不足
- 最新相关文章列表
- 结构化中文简报

简报包含：

1. 为什么这个选题现在具有时效性
2. 当前研究现状
3. 高潜力研究缺口 / 切入角度
4. 每个角度的具体写作/研究问题、价值和可行性
5. 4-6 个高质量标题建议
6. 值得重点阅读的近期文章及理由
7. 潜在风险提示

完整简报会保存为带时间戳的 `.md` 文件，并在终端用 Rich Markdown 渲染。

### 流程三：已有想法时验证与增强

```bash
hotspot-research brief "LLM Agent 记忆演化评测是否是低竞争窗口" --field "大模型智能体"
```

CLI 会把你的想法转换为公开信号查询，输出热度趋势、研究缺口、写作角度、标题建议和必读材料。

## 项目结构

```text
hotspot-cli/
├── src/hotspot_cli/
│   ├── cli.py                 # Typer 入口；run/brief/doctor/config/send
│   ├── assistant_app.py       # Rich + questionary 交互式选题助手
│   ├── assistant_models.py    # Pydantic v2 结构化模型
│   ├── assistant_sources.py   # last30days-safe 数据提供器与趋势计算
│   ├── assistant_analyzer.py  # Instructor/LLM 分析器与本地 fallback
│   ├── assistant_store.py     # SQLite 缓存与历史记录
│   ├── assistant_settings.py  # pydantic-settings + .env 配置
│   ├── assistant_writer.py    # Markdown 简报落盘
│   ├── hotspots.py            # last30days-safe 调用、热点过滤、刷新逻辑
│   └── distribution.py        # 飞书/Lark 分发抽象，预留微信、钉钉
├── tests/
│   ├── test_assistant.py
│   └── test_core.py
├── config.example.json
├── config.example.yaml
└── pyproject.toml
```

## 核心 Pydantic 数据模型

`assistant_models.py` 中的模型保证 LLM 输出和 Markdown 简报结构稳定：

```python
class EvidenceItem(BaseModel):
    title: str
    source: str
    url: str
    published: str | None = None
    score: float = 0
    summary: str = ""

class TopicDirection(BaseModel):
    name: str
    why_now: str
    competition_signal: str
    research_gap: str
    writing_angles: list[str]
    representative_items: list[EvidenceItem]

class TrendMetrics(BaseModel):
    heat_7d: int
    heat_30d: int
    heat_30_60d: int
    trend: Literal["上升", "平稳", "下降", "数据不足"]
    explanation: str

class TopicBrief(BaseModel):
    topic: str
    field: str
    timeliness: str
    current_state: str
    gaps: list[str]
    questions: list[ResearchQuestion]
    title_suggestions: list[str]
    readings: list[ReadingItem]
    risks: list[str]
    trend: TrendMetrics
```

## 数据与缓存

- 数据获取优先通过内嵌 `last30days-safe`，只访问公开端点，不读取浏览器 Cookie、Keychain 或本地私密凭证。
- 缓存使用 SQLite，默认位置为 `~/.hotspot-research-cli/assistant.sqlite`。
- 缓存 key 由查询语句和时间窗口组成，默认 TTL 为 6 小时。
- `--refresh` 会忽略缓存重新抓取。
- 7 天和 30 天窗口会传入 `last30days-safe --days` 执行真实窗口查询；30-60 天对照在 v1 中是保守参考信号，后续会接入 OpenAlex/Google Trends/新闻量增强历史趋势。

## 模型配置

模型配置保存在：

```text
~/.hotspot-research-cli/.env
```

支持的内置服务商：

- `deepseek`：默认推荐，中文分析性价比较高。
- `openai`：OpenAI 官方模型。
- `anthropic`：Claude 系列。
- `openrouter`：多模型聚合。
- `siliconflow`：国内 OpenAI-Compatible 聚合服务。
- `moonshot`：Moonshot Kimi。
- `qwen`：通义千问 DashScope OpenAI-Compatible。
- `ollama`：本地模型。
- `openai-compatible`：任意兼容 OpenAI Chat Completions 的网关，例如 OneAPI、LiteLLM Proxy、火山/智谱兼容接口等。

常用命令：

```bash
hotspot-research config model list
hotspot-research config model show
hotspot-research config model setup
```

底层变量示例：

```env
HOTSPOT_LLM_PROVIDER=deepseek
HOTSPOT_LLM_MODEL=deepseek/deepseek-chat
HOTSPOT_LLM_API_KEY=
HOTSPOT_LLM_BASE_URL=
HOTSPOT_DEEPSEEK_API_KEY=
HOTSPOT_OPENAI_API_KEY=sk-...
OPENAI_API_KEY=sk-...
HOTSPOT_ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_API_KEY=sk-ant-...
HOTSPOT_OPENROUTER_API_KEY=
HOTSPOT_SILICONFLOW_API_KEY=
HOTSPOT_MOONSHOT_API_KEY=
HOTSPOT_QWEN_API_KEY=
HOTSPOT_OLLAMA_BASE_URL=http://localhost:11434
HOTSPOT_CACHE_TTL_SECONDS=21600
```

## 飞书推送

CLI 调用本机已安装的 `lark-cli`。设计参考了 `larksuite/cli` 的官方流程：先 `config init --new` 配置应用，再 `auth login --recommend` 获取用户授权，最后用 `auth status` 验证。

安装 lark-cli：

```bash
npx @larksuite/cli@latest install
```

一条命令引导授权并保存群聊：

```bash
hotspot-research config lark auth --init --recommend --chat-id oc_xxxxxxxxx
```

只检查当前飞书 CLI 和授权状态：

```bash
hotspot-research config lark doctor
```

手动保存群聊配置：

```bash
hotspot-research config lark setup --chat-id oc_xxxxxxxxx --identity bot
```

发送简报：

```bash
hotspot-research send ./briefs/example.md --topic "选题情报简报" --summary "详见附件"
```

交互式生成 Markdown 简报后，CLI 会主动询问是否发送到飞书群：

- 未安装 `lark-cli`：提示安装和配置命令。
- 已安装但未授权：提示运行 `hotspot-research config lark auth --init`。
- 已授权但未配置群聊：提示把机器人加入目标群，并输入 `chat_id` 保存。
- 已授权且已配置群聊：直接发送简报文件和选题简介。

如果缺失 `lark-cli`，请先按飞书官方说明安装并配置：<https://github.com/larksuite/cli>。

### 飞书身份说明

- `--identity bot`：以机器人身份发送。需要机器人在群里，并且飞书应用后台已开通相关 IM 权限。
- `--identity user`：以用户身份发送。需要运行 `lark-cli auth login --recommend` 或按缺失 scope 精确授权。
- 发送失败时，先运行 `hotspot-research config lark doctor` 查看安装和授权状态。

## 交互设计参考

- `larksuite/cli`：采用“安装 → config init → auth login → auth status”的三步配置路径，并把人类友好 shortcut、结构化输出和 agent 友好命令分层。
- `xtherk/open-claude-code`：保留 Claude Code 类终端工具的配置状态、认证状态、可诊断命令和启动交互体验作为参考；本 CLI 采用更轻量的 Typer/Rich/questionary 实现。

## 扩展方向

v1 已预留接口，但暂不默认启用：

- OpenAlex：获取更强的引用数据、论文量和长期趋势。
- Google Trends：补充搜索兴趣激增信号。
- 新闻量统计：补充媒体覆盖强度。
- 本地 embedding 聚类：对近期论文和开源项目做主题簇发现。
- 微信、钉钉：实现 `DistributionChannel` 即可接入。

## 测试

```bash
cd packages/hotspot-cli
PYTHONPATH=src python -m unittest discover -s tests -v
```

## 发布

包名：`hotspot-research-cli`。

GitHub Actions Trusted Publishing 使用路径 tag 触发：

```bash
git tag hotspot-research-cli/v0.2.0
scripts/push-github.zsh origin hotspot-research-cli/v0.2.0
```
