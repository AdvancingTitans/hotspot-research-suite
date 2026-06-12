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

启动交互式选题助手：

```bash
hotspot-research run --output-dir ./briefs
```

已有想法时，直接验证并生成简报：

```bash
hotspot-research brief "中文大模型安全评测的新兴低竞争切口" \
  --field "中文大模型安全" \
  --output-dir ./briefs
```

配置 LLM 结构化分析：

```bash
hotspot-research config llm setup \
  --provider openai \
  --model gpt-4o-mini
```

也支持 Anthropic 和本地 Ollama：

```bash
hotspot-research config llm setup --provider anthropic --model claude-3-5-sonnet
hotspot-research config llm setup --provider ollama --model ollama/qwen2.5
```

没有 LLM API Key 也能运行，CLI 会使用本地规则分析器生成可用简报；配置 LLM 后，细分方向、研究缺口和标题建议会更稳定。

## 默认交互流程

### 流程一：没思路时发现新兴高价值选题

1. CLI 询问你感兴趣的领域，支持自由输入，例如 `大模型智能体`、`多模态推理`、`中文大模型安全`、`具身智能`，也可以输入 `随便推荐`、`AI 通用`、`只看 cs.AI`。
2. `last30days-safe` 拉取最近 7-30 天公开信号，来源包括 Hacker News、GitHub、Reddit、Polymarket，以及包内保留的 arXiv/GitHub/HN 二次信号能力。
3. LLM 或本地规则分析器提炼 5-8 个具体细分方向，而不是泛泛的“多模态大模型”。
4. Rich 表格展示：
   - 吸引人的选题名称
   - 为什么现在热门的一句话与数据证据
   - 竞争程度信号
   - 2-3 篇近期代表性热点标题、来源和链接
5. 你可以输入序号选择，也可以自然语言继续追问，例如 `详细说说第 3 个`、`找更细分的子方向`、`加上中国场景`、`和 XXX 对比一下`。

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

## 配置

LLM 配置保存在：

```text
~/.hotspot-research-cli/.env
```

支持变量：

```env
HOTSPOT_LLM_PROVIDER=openai
HOTSPOT_LLM_MODEL=gpt-4o-mini
HOTSPOT_OPENAI_API_KEY=sk-...
OPENAI_API_KEY=sk-...
HOTSPOT_ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_API_KEY=sk-ant-...
HOTSPOT_OLLAMA_BASE_URL=http://localhost:11434
HOTSPOT_CACHE_TTL_SECONDS=21600
```

## 飞书推送

飞书配置与简报发送：

```bash
hotspot-research config lark setup --chat-id oc_xxxxxxxxx --identity bot
hotspot-research send ./briefs/example.md --topic "选题情报简报" --summary "详见附件"
```

CLI 调用本机已安装的 `lark-cli`。如果缺失，请先按飞书官方说明安装并配置：<https://www.feishu.cn/feishu-cli>。

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
