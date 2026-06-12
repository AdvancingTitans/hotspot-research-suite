# Notice And Source Attribution

This repository packages two related components for public-source topic intelligence and brief delivery.

## Included Components

### `skills/last30days-safe`

- Origin: Hermes Agent skill library, `~/.hermes/skills/research/last30days-safe`.
- Upstream metadata in `SKILL.md`: `author: Hermes Agent`, `license: MIT`, `version: 1.0.0`.
- Purpose: safe public-source last-30-days pulse checks across public endpoints such as Hacker News, GitHub, Reddit, and Polymarket.
- Local changes for this repository: packaging only; no behavioral changes were made to the copied upstream skill.

### `packages/hotspot-cli`

- Origin: created locally in `/Users/yjw/agent/hotspot-cli`.
- Purpose: cross-platform Python CLI that guides users through data-backed topic discovery, trend checks, structured Markdown brief generation, local save, and Lark/Feishu distribution.
- Distribution design inputs:
  - Lark CLI IM command help for `lark-cli im +messages-send`.
  - Lark CLI Drive command help for `lark-cli drive +upload`.
  - User requirements for abstract channel interfaces and future WeChat/DingTalk expansion.

## Naming Notes

The user request used `hotpot-research` / `hotpot-cli` in one place. The implemented package name is `hotspot-research-cli`.

## Safety Notes

- Do not commit local credentials, `.env` files, Lark secrets, or generated brief outputs.
- `last30days-safe` intentionally avoids cookies, Keychain, environment credential discovery, and private account data.
- CLI tests use fake runners and do not call live Lark or external APIs.
