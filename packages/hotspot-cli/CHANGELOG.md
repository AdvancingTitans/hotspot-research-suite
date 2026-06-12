# Changelog

## Unreleased

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
