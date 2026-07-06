# Hotspot Research Suite

**AI research agent for trend discovery, public-source analysis, and Lark-ready Chinese briefs.**

Hotspot Research Suite helps researchers and deep writers find timely, evidence-backed, relatively low-competition topics before everyone else writes the same piece.

```bash
pip install --upgrade hotspot-research-cli
hotspot-research setup
hotspot-research brief "中文大模型安全评测的新兴低竞争切口" --field "中文大模型安全"
```

Use it when you need topic intelligence, must-read source lists, trend metrics, and a structured Markdown brief that can be sent to Feishu/Lark.

## Why Star This Repo

- Turns recent public signals into concrete research and writing directions.
- Combines a reusable agent skill with a PyPI CLI.
- Uses Pydantic models and SQLite cache so outputs are structured and repeatable.
- Built for Chinese long-form research workflows and Lark distribution.

## Related Repos

- [`hotspot-research-skill`](https://github.com/AdvancingTitans/hotspot-research-skill): standalone installable skill for long-form research reports.
- [`pain-miner`](https://github.com/AdvancingTitans/pain-miner): community pain-point mining for micro-product ideas.
- [`awesome-ai-agent-research-tools`](https://github.com/AdvancingTitans/awesome-ai-agent-research-tools): the curated entrypoint for all related tools.

The current default product is `hotspot-research-cli`: an interactive topic intelligence assistant for researchers and deep writers. It helps users discover timely, evidence-backed, relatively low-competition writing and research topics, then saves a structured Chinese 《选题情报简报》 as Markdown.

## Components

- `skills/last30days-safe`: safe public-source collection skill from the Hermes Agent skill library.
- `packages/hotspot-cli`: PyPI package `hotspot-research-cli`.

## Install

```bash
pip install --upgrade hotspot-research-cli
```

Start the topic assistant:

```bash
hotspot-research setup
hotspot-research run --output-dir ./briefs
```

Validate an existing idea:

```bash
hotspot-research brief "中文大模型安全评测的新兴低竞争切口" --field "中文大模型安全"
```

Configure structured LLM analysis:

```bash
hotspot-research config model list
hotspot-research config model setup --provider deepseek --model deepseek/deepseek-chat
hotspot-research config lark auth --init --recommend --chat-id oc_xxxxxxxxx
```

## What The CLI Produces

The default `run` flow asks for a field, gathers recent public signals through `last30days-safe`, proposes 5-8 concrete emerging directions, supports numeric selection or natural-language follow-up, then generates a Markdown brief with:

- timeliness and data signals
- current research coverage
- high-potential research gaps
- concrete writing/research questions
- title suggestions
- recent must-read materials
- risk notes
- trend metrics for 7-day, 30-day, and 30-60-day comparison windows

See [packages/hotspot-cli/README.md](packages/hotspot-cli/README.md) for full CLI usage, architecture, Pydantic models, cache behavior, LLM configuration, and extension guidance.

## Source Attribution

See [NOTICE.md](NOTICE.md) for source attribution and reference links.

- `last30days-safe` is copied from the Hermes Agent skill library and carries upstream MIT metadata.
- `hotspot-cli` was created locally for this suite.

## Development

```bash
cd packages/hotspot-cli
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Publishing

This repo includes `scripts/push-github.zsh`, which reads the GitHub token from:

```text
~/.config/hotspot-research-suite/github_token
```

The token file is local-only and must never be committed.

PyPI publishing uses GitHub Actions Trusted Publishing in `.github/workflows/publish.yml`. Push a path-scoped tag to publish:

```bash
git tag hotspot-research-cli/v0.2.0
scripts/push-github.zsh origin hotspot-research-cli/v0.2.0
```
