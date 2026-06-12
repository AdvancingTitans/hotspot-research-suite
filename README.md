# Hotspot Research Suite

Public-source hotspot discovery, structured research reports, and report delivery automation.

This repository contains:

- `skills/last30days-safe`: a safe public-source last-30-days collection skill from the Hermes Agent skill library.
- `skills/hotspot-research`: a tool-grounded hotspot research skill for topic discovery, scoring, multi-source verification, and report generation.
- `packages/hotspot-cli`: a Python CLI that guides users through domain selection, hotspot selection, report generation, local saving, and Lark/Feishu distribution.

## Quick Start

Install the CLI from PyPI. Python 3.9+ is supported:

```bash
pip install hotspot-research-cli
```

If your shell cannot find the `hotspot-research` command after a user install, use the module entrypoint, which does not depend on shell `PATH`:

```bash
python3 -m hotspot_cli run --output-dir ./reports
```

When started through the module entrypoint, the CLI will try to create a lightweight `~/.local/bin/hotspot-research` shim automatically. You can also repair it explicitly:

```bash
python3 -m hotspot_cli doctor --fix-entrypoint
```

You can also run diagnostics:

```bash
python3 -m hotspot_cli doctor
```

Install from a local checkout for development:

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

The CLI calls a locally installed `lark-cli`. If it is missing, install Feishu CLI from the official page: <https://www.feishu.cn/feishu-cli>, then run `lark-cli config init`.

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

## Publishing

### GitHub

This repo includes `scripts/push-github.zsh`, which reads the GitHub token from:

```text
~/.config/hotspot-research-suite/github_token
```

The token file is local-only and must never be committed. The current machine has been configured from `/tmp/.gh_token`. To recreate it:

```bash
mkdir -p ~/.config/hotspot-research-suite
cp /tmp/.gh_token ~/.config/hotspot-research-suite/github_token
chmod 600 ~/.config/hotspot-research-suite/github_token
```

Push with:

```bash
scripts/push-github.zsh origin main
```

### PyPI

The package name is `hotspot-research-cli`. Release is configured through GitHub Actions Trusted Publishing in `.github/workflows/publish.yml`.

Configure a PyPI pending publisher with:

- PyPI project: `hotspot-research-cli`
- GitHub owner: `AdvancingTitans`
- GitHub repository: `hotspot-research-suite`
- Workflow filename: `publish.yml`
- Environment: `pypi`

Then publish a release by pushing a path-scoped tag:

```bash
git tag hotspot-research-cli/v0.1.0
scripts/push-github.zsh origin hotspot-research-cli/v0.1.0
```

Run tests:

```bash
cd packages/hotspot-cli
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
