# Changelog

## [0.2.1] - 2026-06-12

- Add a first-run `hotspot-research setup` wizard for model and Lark/Feishu configuration.
- Replace opaque field hints such as `AI 通用` and `只看 cs.AI` with plain-language startup choices.
- Add `config model list/show/setup` while keeping `config llm` as a backwards-compatible alias.
- Add model presets for DeepSeek, OpenAI, Anthropic Claude, OpenRouter, SiliconFlow, Moonshot Kimi, Qwen DashScope, Ollama, and custom OpenAI-Compatible endpoints.
- Pass API keys and custom base URLs into LiteLLM/Instructor so OpenAI-Compatible providers work without manual environment tweaking.
- Add `config lark auth` and `config lark doctor`, following lark-cli's recommended `config init --new`, `auth login --recommend`, and `auth status` flow.
- Document setup flows and source-design references from `larksuite/cli` and `xtherk/open-claude-code`.

## [0.2.0] - 2026-06-12

- Redesign the default CLI into an interactive topic intelligence assistant for researchers and deep writers.
- Make `hotspot-research run` discover 5-8 evidence-backed emerging directions and generate a structured Chinese 《选题情报简报》.
- Add `hotspot-research brief` for validating and strengthening an existing topic idea.
- Add Pydantic v2 models for evidence, topic directions, trend metrics, research questions, readings, and final briefs.
- Add SQLite caching keyed by query and time window, with `--refresh` to bypass cache.
- Add `questionary`, `pydantic-settings`, `python-dotenv`, `litellm`, and `instructor` integration, with a local fallback analyzer when no LLM key is configured.
- Add `config llm setup` for OpenAI, Anthropic, and local Ollama configuration.
- Pass real `--days` windows into the bundled `last30days-safe` collector for 7-day and 30-day signal checks.
- Remove the previous long-form report workflow and bundled `hotspot-research` skill; the CLI now focuses only on topic intelligence briefs.

## [0.1.3] - 2026-06-12

- Bundle the standalone `hotspot-research` skill inside the Python wheel and install it automatically on first run or `doctor`.
- Generate reports through the bundled skill resources so users do not need Codex, Hermes, or another agent framework installed.
- Add second-pass source enrichment for GitHub, arXiv, Hacker News, and generic web URLs before drafting.
- Replace the short report stub with a deep research-report draft modeled on the daily automation output.
- Add full sections for selection rationale, longitudinal analysis, competitive map, integrated insights, deep dives, future watchlist, action recommendations, sources, and unverified-items appendix.
- Keep the expanded report grounded in candidate evidence and URLs instead of inventing market-size, funding, or revenue numbers.

## [0.1.2] - 2026-06-12

- Broaden hotspot discovery across GitHub, Hacker News, arXiv, and Reddit public signals.
- Make `refresh` fetch a genuinely different batch via pagination/query rotation.
- Remove internal skill-status narration from the interactive flow.
- Add `doctor` diagnostics for command entrypoints and Feishu/Lark CLI readiness.
- Add automatic `~/.local/bin/hotspot-research` shim repair via `run` and `doctor --fix-entrypoint`.
- Document `python3 -m hotspot_cli run` as a PATH-independent fallback.

## [0.1.1] - 2026-06-12

- Add Python 3.9 compatibility for macOS system `pip3`.
- Replace Python 3.10-only union type syntax in runtime modules.

## [0.1.0] - 2026-06-11

- Initial PyPI-ready release.
- Add interactive domain and hotspot selection flow.
- Bundle safe last-30-days public-source collection fallback.
- Generate local Markdown/HTML/PDF-ready reports.
- Add Lark/Feishu distribution channel and extensible channel interface.
