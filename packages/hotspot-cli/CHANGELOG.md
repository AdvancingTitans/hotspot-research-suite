# Changelog

## [0.2.6] - 2026-06-13

- Persist the user's topic profile locally in SQLite so repeated `hotspot-research run` sessions can reuse it without asking the same questions again.
- Add `hotspot-research config profile show` and `hotspot-research config profile clear` for inspecting and resetting the saved profile.
- Make stage 2 profile building feel more conversational: ask background, real goal, unique advantages/resources, and concerns with warm natural prompts.
- Treat answers such as “没有”“不知道”“还没想好” as valid skips and avoid repeating equivalent profile questions.
- Reject LLM-generated profile questions that sound like a form or do not match the current conversational topic, falling back to curated natural prompts.

## [0.2.5] - 2026-06-13

- Replace the default `run` flow with a 4-stage adaptive topic interview: interest exploration, user profile building, data-backed opportunity scan, and personalized matching/brief generation.
- Add conversation state and Pydantic models for `ResearchProfile`, `ConversationState`, `IntentResult`, `MatchedTopic`, and `PersonalizedTopicBrief`.
- Add LLM-assisted natural-language intent recognition and adaptive one-question-at-a-time profile follow-up, with local fallback rules when no model key is configured.
- Match candidate topics by personal fit, data opportunity, and feasibility instead of ranking by heat alone.
- Generate a personalized Markdown topic brief explaining why the selected topic fits the user, with angles, titles, outline, readings, risks, and trend data.
- Make non-TTY input fall back to plain `input()` so automated smoke tests and piped demos do not break on questionary prompts.

## [0.2.4] - 2026-06-13

- Replace the slogan-style startup panel with a Claude Code-inspired status dashboard showing model, cache TTL, cwd, output directory, quick commands, and recent activity hints.
- Add LLM-driven search planning for default, academic, industry, manual, refresh, and follow-up paths so each mode retrieves distinct evidence-backed topics.
- Make `refresh` avoid topics already shown in the current session.
- Expand the refresh query pool and suppress zero-evidence placeholder topics from recommendation tables.
- Re-query public evidence for natural-language follow-up prompts instead of filtering the previous table only.
- After saving a Markdown brief, ask whether to send it to a Lark/Feishu group and guide the user through lark-cli install/auth/chat_id setup when anything is missing.
- Add `lark_auth_status` diagnostics and tests for missing authorization.

## [0.2.3] - 2026-06-12

- Add `hotspot-research config model verify` to validate the current provider/base URL/model/API key with a real minimal chat completion before users start research.
- Add `hotspot-research config model models` to fetch provider model IDs from `/models`, helping users avoid placeholder or retired model names.
- Add `hotspot-research config model doctor` with Ark-specific diagnostics and direct fix commands.
- Make Ark setup one-step: `--provider ark` supplies the verified `/api/v3` base URL and a working Doubao model; known-bad `/api/coding` URLs are auto-repaired.
- Reject incomplete custom OpenAI-Compatible configs unless both `--base-url` and a real `--model` are supplied.
- Add `hotspot-research config cache show/set/clear` for cache TTL inspection, tuning, and recovery from read-only or damaged SQLite cache files.
- Use direct JSON-mode LiteLLM calls plus Pydantic validation for OpenAI-compatible providers to avoid Instructor schema incompatibilities.

## [0.2.2] - 2026-06-12

- Make the no-idea startup path use multiple broad AI topic seeds instead of one narrow query.
- Add automatic fallback from `last30days-safe` to public GitHub/Hacker News/arXiv/Reddit signal collection when the safe collector returns no items.
- Return an actionable "data insufficient, broaden verification" direction instead of ending the flow with no options.
- Suppress the non-fatal urllib3 LibreSSL warning that appears on macOS Command Line Tools Python 3.9.
- Add a first-class Volcengine Ark preset with the verified `/api/v3` OpenAI-Compatible base URL and a working Doubao chat model.
- Force LiteLLM to use its local model-cost map so restricted networks do not print irrelevant fetch warnings during interactive use.
- Fix package `__version__` to match the published CLI line.

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
