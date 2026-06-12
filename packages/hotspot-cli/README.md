# Hotspot Research CLI

一款跨平台 Python CLI，用交互式问答引导用户通过 `last30days-safe` 选择近 30 天客观热点，并按 `hotspot-research` 结构生成本地研究报告；支持通过 `lark-cli` 将选题简介和报告文件推送到飞书群。分发层已预留微信、钉钉等渠道扩展接口。

CLI 的 PyPI wheel 已内嵌 `hotspot-research` skill。用户不需要安装 Codex、Hermes 或其他 agent 框架；首次运行 `run` 或 `doctor` 时，CLI 会自动把 skill 资源安装到本机，并用这些模板、脚本和研究框架生成报告。

## 功能

- 交互式分支流程：
  - 有指定领域：直接拉取该领域 TOP10 客观热点。
  - 无指定领域：先拉取 TOP10 主流研究领域，选定领域后再拉取热点。
- 支持 `refresh` 无限换批，直到用户确认领域/选题。
- 热点过滤规则：
  - 保留政策、监管、市场数据、融资、学术成果、技术迭代、产品发布、供应链、产业事件等客观赛道热点。
  - 剔除纯网络炒作、短期娱乐八卦、金融投机类热点。
  - 每个候选展示评分、来源类型和数据依据。
- 报告本地保存：
  - Markdown
  - HTML
  - PDF（若本机 WeasyPrint/native 依赖可用）
- 默认生成深度研究底稿，而不是短摘要：
  - 执行摘要、一句话定义、选题理由
  - 纵向分析、横向竞争图谱、横纵交汇洞察
  - 专题深挖、未来 30-90 天观察指标、行动建议
  - 信息来源表、未确认事项与后续验证路径
  - 所有展开内容仅基于候选 evidence 与 URL，不编造融资额、市场规模或收入数据
- 内嵌 skill + 二次取证：
  - 自动安装包内 `hotspot-research` skill
  - 读取 skill 的报告模板和市场研究框架
  - 对 GitHub / arXiv / Hacker News / 普通网页 URL 做二次抓取
  - 将 stars、forks、issues、论文标题、作者、摘要、讨论数据等写入“来源画像”
- 飞书推送：
  - 文本简介：`lark-cli im +messages-send`
  - 报告文件：`lark-cli im +messages-send --file`
  - 可选 Drive 备份上传：配置 `upload_folder_token` 后调用 `lark-cli drive +upload`

## 项目结构

```text
hotspot-cli/
├── src/hotspot_cli/
│   ├── cli.py            # Typer/Rich 交互入口
│   ├── config.py         # JSON/YAML 配置管理
│   ├── hotspots.py       # last30days-safe 调用、热点筛选与刷新
│   ├── report.py         # hotspot-research 报告结构与本地文件生成
│   └── distribution.py   # 多渠道分发抽象，内置 LarkChannel
├── templates/
│   └── report-template.md
├── tests/
│   └── test_core.py
├── config.example.json
├── config.example.yaml
└── pyproject.toml
```

## 安装

支持 Python 3.9+。macOS 系统自带 `pip3` 若绑定 Python 3.9，也可以直接安装 0.1.1 或更新版本。

PyPI 发布后可直接安装：

```bash
pip install hotspot-research-cli
```

如果安装成功但 shell 提示 `command not found: hotspot-research`，说明 Python 的 user-base bin 目录不在 `PATH` 中。无需手动创建软链，可直接使用不依赖 PATH 的模块入口：

```bash
python3 -m hotspot_cli run --output-dir ./reports
```

通过模块入口启动时，CLI 会尝试自动创建 `~/.local/bin/hotspot-research` shim；也可以显式修复：

```bash
python3 -m hotspot_cli doctor --fix-entrypoint
```

也可以先运行诊断：

```bash
python3 -m hotspot_cli doctor
```

`doctor` 会同时检查命令入口、飞书 CLI 和内嵌 `hotspot-research` skill 安装状态。

如果曾经因为 0.1.0 的 Python 版本限制安装失败，重新执行：

```bash
pip3 install --upgrade hotspot-research-cli
```

本地开发安装：

```bash
cd /Users/yjw/agent/hotspot-research-suite/packages/hotspot-cli
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

如果使用 macOS 系统 Python 遇到依赖或动态库问题，建议改用 Homebrew Python：

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

## 启动交互式流程

```bash
hotspot-research run --output-dir ./reports
```

流程：

1. 终端询问：`你是否有想要研究的指定领域？`
2. 如果直接输入领域，例如 `人工智能`，CLI 会拉取该领域 TOP10 客观热点。
3. 如果直接回车，CLI 会先展示 TOP10 主流研究领域。
4. 在领域和热点列表里：
   - 输入序号确认；
   - 输入 `refresh` 换一批；
   - 非法输入会提示并重新询问。
5. 确认选题后生成深度研究报告，并输出本地绝对路径。

生成报告的默认目标是可继续编辑的长文研究底稿：CLI 会把候选热点的来源、评分、证据字段和 URL 组织成完整研究框架，并对可识别 URL 做二次取证；如果当前数据不足以支持市场规模、融资、收入、监管状态等强结论，会明确列入“未确认与后续验证”，而不是用模型猜测补齐。

## 飞书配置

CLI 会调用本机已安装的 `lark-cli`。如果本机没有 `lark-cli`，请先从飞书官方页面安装：<https://www.feishu.cn/feishu-cli>。首次使用飞书前，先按 `lark-cli` 官方流程配置：

```bash
lark-cli config init --new
```

如需用户身份发送，需要授权：

```bash
lark-cli auth login --scope "im:message"
```

Bot 身份通常需要在飞书开发者后台开通 IM 和 Drive 相关权限，并确保机器人在目标群内。

### 交互式配置

```bash
hotspot-research config lark setup
```

### 命令行参数配置

```bash
hotspot-research config lark setup \
  --chat-id oc_xxxxxxxxxxxxxxxxx \
  --identity bot \
  --message-template '选题：{topic}
简介：{summary}
本地报告：{report_path}'
```

可选：把报告额外上传到云空间指定文件夹：

```bash
hotspot-research config lark setup \
  --chat-id oc_xxxxxxxxxxxxxxxxx \
  --upload-folder-token fldxxxxxxxxx
```

### 查看与重置配置

```bash
hotspot-research config show
hotspot-research config reset
```

默认配置文件：

```text
~/.hotspot-research-cli/config.json
```

也可指定配置文件，支持 JSON/YAML：

```bash
hotspot-research config show --config ./config.example.yaml
```

## 生成后推送飞书

生成报告并推送：

```bash
hotspot-research run --push-lark --output-dir ./reports
```

推送已有报告：

```bash
hotspot-research send ./reports/example.pdf \
  --topic "个人手机智能体" \
  --summary "近30天 AI 手机和移动智能体交汇热点"
```

## 异常排查

- `last30days-safe 执行失败`：检查网络、GitHub/Reddit/HN/Polymarket 是否可访问。
- `未获取到符合规则的客观热点`：输入 `refresh`，或换一个更具体的领域。
- `缺少飞书群 chat_id`：运行 `hotspot-research config lark setup`。
- `lark-cli 权限不足`：按错误里的 scope 到飞书后台开权限；user 身份需执行 `lark-cli auth login --scope ...`。
- `报告目录无法写入`：换 `--output-dir` 到有权限的目录。
- `PDF 未生成`：检查 `/Users/yjw/agent/hotspot-research/scripts/render_pdf_weasy.py`；macOS 通常需要 Homebrew 的 `pango/cairo/glib`。

## 新增微信、钉钉等渠道

新增渠道只需实现 `DistributionChannel`：

```python
from pathlib import Path
from hotspot_cli.distribution import DistributionChannel


class DingTalkChannel(DistributionChannel):
    def send(
        self,
        *,
        chat_id: str,
        topic: str,
        summary: str,
        report_path: Path,
        identity: str,
        message_template: str,
        upload_folder_token: str = "",
    ) -> None:
        ...
```

注册：

```python
registry = ChannelRegistry()
registry.register("dingtalk", DingTalkChannel())
```

约束：

- 不修改 `HotspotService` 和 `ReportGenerator`。
- 渠道只负责消息/文件分发。
- 渠道配置应放入独立 config section，避免污染飞书配置。
- 所有外部命令都用参数数组调用，避免 shell 拼接。

## 测试

```bash
cd /Users/yjw/agent/hotspot-research-suite/packages/hotspot-cli
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## PyPI 发布

包名：`hotspot-research-cli`。

仓库已内置 GitHub Actions Trusted Publishing 工作流：`.github/workflows/publish.yml`。首次发布前，在 PyPI 创建 pending publisher：

- Project name: `hotspot-research-cli`
- Owner: `AdvancingTitans`
- Repository: `hotspot-research-suite`
- Workflow: `publish.yml`
- Environment: `pypi`

确认 PyPI 侧配置完成后，推送 tag 即可触发发布：

```bash
git tag hotspot-research-cli/v0.1.0
scripts/push-github.zsh origin hotspot-research-cli/v0.1.0
```
