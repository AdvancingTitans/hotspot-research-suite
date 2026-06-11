# Notice And Source Attribution

This repository packages three related components for public-source hotspot research and report delivery.

## Included Components

### `skills/last30days-safe`

- Origin: Hermes Agent skill library, `~/.hermes/skills/research/last30days-safe`.
- Upstream metadata in `SKILL.md`: `author: Hermes Agent`, `license: MIT`, `version: 1.0.0`.
- Purpose: safe public-source last-30-days pulse checks across public endpoints such as Hacker News, GitHub, Reddit, and Polymarket.
- Local changes for this repository: packaging only; no behavioral changes were made to the copied upstream skill.

### `skills/hotspot-research`

- Origin: created locally in `/Users/yjw/agent/hotspot-research`.
- Purpose: tool-grounded hotspot discovery, topic scoring, multi-source research, and structured report generation.
- Design inputs:
  - Hermes `last30days-safe` workflow for safe public-source collection.
  - Local research-report workflow requirements supplied by the user.
  - Kami-style document delivery requirements for Markdown/HTML/PDF outputs.
- WeasyPrint macOS fix references:
  - Kozea/WeasyPrint issue #2694: `https://github.com/Kozea/WeasyPrint/issues/2694`
  - tw93/Kami issue #15: `https://github.com/tw93/Kami/issues/15`
  - awslabs/generative-ai-atlas PR #43: `https://github.com/awslabs/generative-ai-atlas/pull/43`
  - WeasyPrint documentation: `https://doc.courtbouillon.org/weasyprint/stable/first_steps.html`

### `packages/hotspot-cli`

- Origin: created locally in `/Users/yjw/agent/hotspot-cli`.
- Purpose: cross-platform Python CLI that guides users through research-domain selection, last-30-days hotspot selection, report generation, local save, and Lark/Feishu distribution.
- Distribution design inputs:
  - Lark CLI IM command help for `lark-cli im +messages-send`.
  - Lark CLI Drive command help for `lark-cli drive +upload`.
  - User requirements for abstract channel interfaces and future WeChat/DingTalk expansion.

## Naming Notes

The user request used `hotpot-research` / `hotpot-cli` in one place. The implemented project names are `hotspot-research` and `hotspot-cli`.

## Safety Notes

- Do not commit local credentials, `.env` files, Lark secrets, or generated report outputs.
- `last30days-safe` intentionally avoids cookies, Keychain, environment credential discovery, and private account data.
- CLI tests use fake runners and do not call live Lark or external APIs.

