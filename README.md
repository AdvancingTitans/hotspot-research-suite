# Hotspot Research Suite

Public-source hotspot discovery, structured research reports, and report delivery automation.

This repository contains:

- `skills/last30days-safe`: a safe public-source last-30-days collection skill from the Hermes Agent skill library.
- `skills/hotspot-research`: a tool-grounded hotspot research skill for topic discovery, scoring, multi-source verification, and report generation.
- `packages/hotspot-cli`: a Python CLI that guides users through domain selection, hotspot selection, report generation, local saving, and Lark/Feishu distribution.

## Quick Start

Install the CLI:

```bash
cd packages/hotspot-cli
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Run the interactive flow:

```bash
hotspot-research run --output-dir ./reports
```

Configure Lark/Feishu delivery:

```bash
hotspot-research config lark setup \
  --chat-id oc_xxxxxxxxxxxxxxxxx \
  --identity bot
```

Generate and push to Lark:

```bash
hotspot-research run --push-lark --output-dir ./reports
```

## Workflow

1. Ask whether the user has a target domain.
2. If a domain is provided, use `last30days-safe` to collect recent public-source signals and produce TOP10 objective hotspots.
3. If no domain is provided, first surface TOP10 mainstream research domains, then run the domain-specific hotspot flow.
4. Support unlimited `refresh` cycles until the user confirms a topic.
5. Generate a structured research report using the `hotspot-research` structure.
6. Save local files and optionally distribute through Lark/Feishu.

## Source Attribution

See [NOTICE.md](NOTICE.md) for source attribution and reference links. In short:

- `last30days-safe` is copied from the Hermes Agent skill library and carries upstream MIT metadata.
- `hotspot-research` and `hotspot-cli` were created locally for this suite.
- WeasyPrint macOS troubleshooting guidance cites public GitHub issues and official documentation.

## Repository Hygiene

Generated reports, virtual environments, local configs, and credentials are ignored by `.gitignore`.

Run tests:

```bash
cd packages/hotspot-cli
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

