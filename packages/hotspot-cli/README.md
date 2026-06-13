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

启动后会显示一个简洁的状态面板：当前模型、缓存 TTL、输出目录，以及常用命令提示。随后进入 4 阶段自适应对话。交互中可输入：

- `随便推荐`、`完全没思路`、`AI+人文社科交叉`：从开放兴趣探索开始。
- `换一个方向`、`这个太难了，换简单点的`：重新聚焦并刷新机会扫描。
- `再问我几个问题`：继续补充画像。
- `都看看但帮我排序`：按个人契合度、数据机会、可行性综合排序。
- `1-6`：选择一个方向并生成个性化 Markdown 简报。
- `q`：退出。

CLI 会把你确认后的“选题画像”保存到本地 SQLite。之后再次运行 `hotspot-research run` 时，会优先沿用这份画像，不再重复问背景、目标、优势、顾虑这些问题。你仍然可以输入新的方向临时覆盖本次探索。

查看或清除本地画像：

```bash
hotspot-research config profile show
hotspot-research config profile clear
```

诊断本机命令入口、模型配置、飞书 CLI 和缓存状态：

```bash
hotspot-research doctor
hotspot-research doctor --json
```

`--json` 输出适合复制到 issue、自动化任务或排障脚本中；不会显示 API Key。

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

缓存只用于减少重复抓取。`config cache show` 会展示缓存路径、TTL、条目数、状态分布和来源分布；SQLite 缓存只读或损坏时不会中断主流程，可用 `config cache clear` 清理后重试。

## 默认交互流程

`hotspot-research run` 现在默认是“先理解你，再扫描机会”的自适应流程，而不是单纯按热度列榜。

### 阶段 1：兴趣与领域探索

CLI 先用开放式问题了解你的 broad 兴趣或问题。你可以输入：

- `随便推荐`
- `我完全没思路`
- `我想做 AI+人文社科交叉`
- 一个具体领域，例如 `大模型智能体`、`中文大模型安全`、`AI 写作工具`

系统会先给出 3-5 个初步方向，并询问你更倾向哪个，或是否想继续聚焦某个子领域。

### 阶段 2：构建用户深度画像

这是最关键的一步。CLI 会像聊天一样，根据前文回答自适应追问，每次只问一个最有价值的问题。内部会理解这些维度，但不会用“画像字段”“风险偏好”“输出偏好”这类生硬表达问你：

- 背景与积累：之前做过什么研究、写作或项目
- 真实目标：这次想达成什么结果，比如写文章、发论文、系统学习、职业准备或好奇探索
- 优势与资源：别人不太容易复制的视角、经历、数据、人脉、语言/城市/行业优势
- 当前顾虑：不想碰的方向、觉得麻烦或没把握的地方

你可以回答“没有”“不知道”“还没想好”，CLI 会把这当作有效跳过，不会追着问同一个问题。画像构建结束后，CLI 会用 Rich 面板总结它理解的情况，并允许你确认或补充修正。确认后的画像会保存到本地，后续运行默认沿用。

### 阶段 3：数据驱动的机会扫描 + 初步匹配

确认画像后，CLI 会结合个人画像规划检索 query，通过 `last30days-safe` 与包内公开信号能力扫描 arXiv、GitHub、Hacker News、Reddit 等公开渠道，寻找同时满足以下条件的候选方向：

- 有明显时效性或上升趋势，并有数据支撑
- 存在可切入的研究缺口
- 与你的背景、目标、资源和风险偏好高度匹配

Rich 表格会展示 4-6 个候选选题，并给出：

- 个人契合度
- 数据机会与时效性
- 写作/研究可行性
- 初步匹配理由：个人契合点 + 数据信号 + 研究缺口

### 阶段 4：个性化深度匹配、排序与细化

你可以继续自然语言互动：

- `都看看但帮我排序`
- `这个方向怎么结合我的中文语境优势`
- `找更细的切入点`
- `这个太难了，换简单点的`
- `换一个方向`

CLI 会继续刷新画像约束、重新检索或重新排序。最终选择某个方向后，会计算不同时间窗口并生成《个性化选题情报简报》：

- 最近 7 天热度
- 最近 30 天热度
- 30-60 天前对照信号
- 趋势判断：上升、平稳、下降或数据不足

简报包含：

1. 为什么这个选题最契合你：个人优势 + 数据窗口结合
2. 推荐的 2-4 个具体切入角度及理由
3. 高质量标题建议：学术风格 + 深度文章风格
4. 写作/研究大纲框架建议
5. 必读核心文献与材料，以及为什么重要
6. 潜在风险与应对

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
│   ├── conversation_app.py    # 4 阶段自适应选题对话主流程
│   ├── conversation_models.py # 用户画像、意图、匹配选题、个性化简报模型
│   ├── assistant_app.py       # 旧线性选题流程，保留作内部兼容
│   ├── assistant_models.py    # 证据、趋势、通用简报 Pydantic 模型
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

`conversation_models.py` 和 `assistant_models.py` 共同保证 LLM 输出、用户画像和 Markdown 简报结构稳定。主流程新增模型：

```python
class ResearchProfile(BaseModel):
    broad_interest: str
    selected_focus: str
    background: str
    goal: str
    time_budget: str
    resources: str
    unique_advantages: str
    risk_preference: str
    output_preference: str
    constraints: str
    confidence: float

class ConversationState(BaseModel):
    phase: Literal["interest", "profile", "scan", "match", "brief"]
    turns: list[DialogueTurn]
    profile: ResearchProfile
    initial_directions: list[InitialDirection]
    matched_topics: list[MatchedTopic]
    seen_topics: list[str]
    profile_rounds: int

class IntentResult(BaseModel):
    intent: Literal["answer", "refresh", "narrow", "broaden", "easier", "harder", "rank", "choose", "quit", "unknown"]
    target_index: int | None
    rewritten_focus: str
    note: str

class MatchedTopic(BaseModel):
    name: str
    personal_fit: int
    opportunity_score: int
    feasibility_score: int
    total_score: int
    personal_reason: str
    data_signal: str
    research_gap: str
    representative_items: list[EvidenceItem]

class PersonalizedTopicBrief(BaseModel):
    topic: str
    profile_summary: str
    why_best_fit: str
    angles: list[ResearchQuestion]
    title_suggestions: list[str]
    outline: list[str]
    readings: list[ReadingItem]
    risks: list[str]
    trend: TrendMetrics
```

通用证据与趋势模型：

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
- 用户选题画像也保存在同一个 SQLite 文件，可通过 `hotspot-research config profile show/clear` 查看或清除。
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
