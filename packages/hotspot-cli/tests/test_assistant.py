import tempfile
import unittest
from pathlib import Path

from hotspot_cli.hotspots import HotspotCandidate


class AssistantTests(unittest.TestCase):
    def test_topic_models_and_fallback_analyzer_create_specific_directions(self) -> None:
        from hotspot_cli.assistant_analyzer import FallbackTopicAnalyzer
        from hotspot_cli.assistant_models import TopicDiscoveryInput

        candidates = [
            HotspotCandidate(
                "EvoArena: Tracking Memory Evolution for Robust LLM Agents",
                "大模型智能体",
                42,
                ["arxiv"],
                "arXiv submitted=2026-06-10; paper signal; memory evolution benchmark for LLM agents",
                ["https://arxiv.org/abs/2606.00001"],
            ),
            HotspotCandidate(
                "browser-use/browser-use",
                "大模型智能体",
                560,
                ["github"],
                "GitHub stars=72000; forks=9000; issues=500; updated=2026-06-12; browser automation agents",
                ["https://github.com/browser-use/browser-use"],
            ),
        ]

        result = FallbackTopicAnalyzer().discover_directions(
            TopicDiscoveryInput(field="大模型智能体", window_days=30, candidates=candidates)
        )

        self.assertGreaterEqual(len(result.directions), 2)
        self.assertLessEqual(len(result.directions), 8)
        self.assertIn("为什么现在热门", result.directions[0].why_now)
        self.assertTrue(result.directions[0].representative_items)

    def test_sqlite_cache_round_trip_by_query_and_window(self) -> None:
        from hotspot_cli.assistant_store import AssistantStore

        with tempfile.TemporaryDirectory() as td:
            store = AssistantStore(Path(td) / "assistant.sqlite")
            payload = {"items": [{"title": "A"}]}

            self.assertIsNone(store.get_cache("agent", 30, max_age_seconds=3600))
            store.set_cache("agent", 30, payload)

            self.assertEqual(store.get_cache("agent", 30, max_age_seconds=3600), payload)
            self.assertIsNone(store.get_cache("agent", 7, max_age_seconds=3600))

    def test_sqlite_cache_write_failure_does_not_break_flow(self) -> None:
        import sqlite3

        from hotspot_cli.assistant_store import AssistantStore

        class ReadonlyStore(AssistantStore):
            def _init_db(self) -> None:
                self.available = True

            def _connect(self):  # type: ignore[no-untyped-def]
                raise sqlite3.OperationalError("attempt to write a readonly database")

        store = ReadonlyStore(Path("/tmp/readonly.sqlite"))

        self.assertIsNone(store.get_cache("agent", 30, max_age_seconds=3600))
        store.set_cache("agent", 30, {"items": []})
        store.add_history("brief", "title", {})
        self.assertFalse(store.available)

    def test_model_presets_include_common_cn_and_global_providers(self) -> None:
        from hotspot_cli.model_presets import MODEL_PRESETS

        for provider in ["deepseek", "openai", "anthropic", "openrouter", "siliconflow", "moonshot", "qwen", "ark", "ollama", "openai-compatible"]:
            self.assertIn(provider, MODEL_PRESETS)
        self.assertEqual(MODEL_PRESETS["deepseek"].model, "deepseek/deepseek-chat")
        self.assertTrue(MODEL_PRESETS["qwen"].base_url)
        self.assertEqual(MODEL_PRESETS["ark"].base_url, "https://ark.cn-beijing.volces.com/api/v3")

    def test_save_llm_env_supports_openai_compatible_base_url(self) -> None:
        import os
        from unittest.mock import patch

        import hotspot_cli.assistant_settings as settings_mod
        from hotspot_cli.assistant_settings import save_llm_env

        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            with patch.object(settings_mod, "USER_ENV_PATH", env_path):
                path = save_llm_env(
                    provider="openai-compatible",
                    model="openai/custom-model",
                    api_key="test-key",
                    base_url="https://api.example.com/v1",
                )

            text = path.read_text(encoding="utf-8")
            self.assertIn("HOTSPOT_LLM_PROVIDER=openai-compatible", text)
            self.assertIn("HOTSPOT_LLM_BASE_URL=https://api.example.com/v1", text)
            self.assertIn("OPENAI_BASE_URL=https://api.example.com/v1", text)
            self.assertIn("OPENAI_API_KEY=test-key", text)

    def test_save_llm_env_supports_ark_preset(self) -> None:
        from unittest.mock import patch

        import hotspot_cli.assistant_settings as settings_mod
        from hotspot_cli.assistant_settings import save_llm_env

        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            with patch.object(settings_mod, "USER_ENV_PATH", env_path):
                path = save_llm_env(
                    provider="ark",
                    model="openai/doubao-1-5-lite-32k-250115",
                    api_key="test-key",
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                )

            text = path.read_text(encoding="utf-8")
            self.assertIn("HOTSPOT_LLM_PROVIDER=ark", text)
            self.assertIn("HOTSPOT_ARK_API_KEY=test-key", text)
            self.assertIn("ARK_API_KEY=test-key", text)
            self.assertIn("OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3", text)

    def test_prepare_model_config_repairs_ark_base_and_placeholder_model(self) -> None:
        from hotspot_cli.model_config import prepare_model_config

        plan = prepare_model_config(
            provider="ark",
            model="openai/your-model-name",
            api_key="test-key",
            base_url="https://ark.cn-beijing.volces.com/api/coding",
        )

        self.assertEqual(plan.provider, "ark")
        self.assertEqual(plan.base_url, "https://ark.cn-beijing.volces.com/api/v3")
        self.assertEqual(plan.model, "openai/doubao-1-5-lite-32k-250115")
        self.assertTrue(plan.warnings)

    def test_prepare_model_config_requires_custom_base_and_real_model(self) -> None:
        from hotspot_cli.model_config import prepare_model_config

        with self.assertRaises(ValueError):
            prepare_model_config(provider="custom", model="openai/your-model-name", api_key="test-key", base_url="")

    def test_set_user_env_value_preserves_existing_values(self) -> None:
        from unittest.mock import patch

        import hotspot_cli.assistant_settings as settings_mod
        from hotspot_cli.assistant_settings import set_user_env_value

        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            env_path.write_text("HOTSPOT_LLM_PROVIDER=ark\n", encoding="utf-8")
            with patch.object(settings_mod, "USER_ENV_PATH", env_path):
                path = set_user_env_value("HOTSPOT_CACHE_TTL_SECONDS", "1800")

            text = path.read_text(encoding="utf-8")
            self.assertIn("HOTSPOT_LLM_PROVIDER=ark", text)
            self.assertIn("HOTSPOT_CACHE_TTL_SECONDS=1800", text)

    def test_provider_passes_window_days_to_last30days_client(self) -> None:
        from hotspot_cli.assistant_sources import Last30DaysProvider
        from hotspot_cli.assistant_store import AssistantStore

        class FakeClient:
            def __init__(self) -> None:
                self.calls = []

            def collect(self, topic: str, *, limit: int = 20, days: int = 30) -> dict:
                self.calls.append((topic, limit, days))
                return {
                    "items": [
                        {
                            "title": f"{topic} item",
                            "source": "hn",
                            "url": "https://example.com/item",
                            "score": 12,
                            "snippet": f"days={days}",
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as td:
            fake = FakeClient()
            provider = Last30DaysProvider(store=AssistantStore(Path(td) / "assistant.sqlite"), client=fake)

            items = provider.search("agent memory", window_days=7, limit=5, refresh=True)

            self.assertEqual(fake.calls, [("agent memory", 5, 7)])
            self.assertIn("days=7", items[0].evidence)

    def test_chinese_ai_field_expands_to_verifiable_public_queries(self) -> None:
        from hotspot_cli.assistant_app import _normalize_field_queries

        queries = _normalize_field_queries("大模型智能体")

        self.assertIn("大模型智能体", queries)
        self.assertIn("LLM agents benchmark arxiv", queries)
        self.assertGreater(len(queries), 1)

    def test_provider_falls_back_to_public_signal_client_when_safe_source_is_empty(self) -> None:
        from hotspot_cli.assistant_sources import Last30DaysProvider
        from hotspot_cli.assistant_store import AssistantStore

        class EmptyClient:
            def collect(self, topic: str, *, limit: int = 20, days: int = 30) -> dict:
                return {"items": []}

        class FakeSignalClient:
            def collect(self, query: str, domain: str, *, limit: int, refresh_index: int = 0) -> list[HotspotCandidate]:
                return [
                    HotspotCandidate(
                        "New LLM agent benchmark",
                        domain,
                        24,
                        ["arxiv"],
                        "arXiv submitted=2026-06-12; benchmark evidence",
                        ["https://arxiv.org/abs/2606.00001"],
                    )
                ]

        with tempfile.TemporaryDirectory() as td:
            provider = Last30DaysProvider(
                store=AssistantStore(Path(td) / "assistant.sqlite"),
                client=EmptyClient(),
                signal_client=FakeSignalClient(),
            )

            items = provider.search("agent benchmark", refresh=True)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].sources, ["arxiv"])

    def test_fallback_analyzer_returns_actionable_direction_when_candidates_empty(self) -> None:
        from hotspot_cli.assistant_analyzer import FallbackTopicAnalyzer
        from hotspot_cli.assistant_models import TopicDiscoveryInput

        result = FallbackTopicAnalyzer().discover_directions(
            TopicDiscoveryInput(field="近期高价值 AI 选题", window_days=30, candidates=[])
        )

        self.assertEqual(len(result.directions), 1)
        self.assertIn("数据不足", result.directions[0].why_now)
        self.assertTrue(result.directions[0].representative_items)

    def test_direction_count_is_topped_up_from_fallback(self) -> None:
        from hotspot_cli.assistant_analyzer import _ensure_direction_count
        from hotspot_cli.assistant_models import EvidenceItem, TopicDirection, TopicDiscoveryResult

        def direction(name: str) -> TopicDirection:
            return TopicDirection(
                name=name,
                why_now="为什么现在热门：有公开信号。",
                competition_signal="竞争信号",
                research_gap="研究缺口",
                representative_items=[EvidenceItem(title=name, source="test", url="")],
            )

        primary = TopicDiscoveryResult(field="AI", directions=[direction("A"), direction("B")])
        fallback = TopicDiscoveryResult(field="AI", directions=[direction("B"), direction("C"), direction("D"), direction("E")])

        merged = _ensure_direction_count(primary, fallback)

        self.assertEqual([item.name for item in merged.directions], ["A", "B", "C", "D", "E"])

    def test_trend_metrics_use_pydantic_field_names(self) -> None:
        from hotspot_cli.assistant_sources import Last30DaysProvider
        from hotspot_cli.assistant_store import AssistantStore

        class FakeClient:
            def collect(self, topic: str, *, limit: int = 20, days: int = 30) -> dict:
                score = {7: 20, 30: 120, 60: 40}.get(days, 10)
                return {
                    "items": [
                        {
                            "title": f"{topic} item",
                            "source": "github",
                            "url": "https://example.com/item",
                            "score": score,
                        }
                    ]
                }

        with tempfile.TemporaryDirectory() as td:
            provider = Last30DaysProvider(store=AssistantStore(Path(td) / "assistant.sqlite"), client=FakeClient())

            trend = provider.trend("agent memory", refresh=True)

            self.assertGreater(trend.heat_7d, 0)
            self.assertGreater(trend.heat_30d, 0)
            self.assertGreater(trend.heat_30_60d, 0)

    def test_brief_markdown_contains_required_sections_and_is_saved(self) -> None:
        from hotspot_cli.assistant_analyzer import FallbackTopicAnalyzer
        from hotspot_cli.assistant_models import TopicSelection
        from hotspot_cli.assistant_writer import BriefWriter

        with tempfile.TemporaryDirectory() as td:
            selection = TopicSelection(
                name="记忆演化评测：LLM Agent 长程可靠性的低竞争窗口",
                field="大模型智能体",
                query="LLM agent memory evolution benchmark",
                rationale="近 7 天出现论文信号，GitHub 生态也在升温，但细分研究仍然具体。",
                evidence=[
                    HotspotCandidate(
                        "EvoArena: Tracking Memory Evolution for Robust LLM Agents",
                        "大模型智能体",
                        42,
                        ["arxiv"],
                        "arXiv submitted=2026-06-10; paper signal",
                        ["https://arxiv.org/abs/2606.00001"],
                    )
                ],
            )
            brief = FallbackTopicAnalyzer().create_brief(selection)
            path = BriefWriter(Path(td)).save(brief)
            text = path.read_text(encoding="utf-8")

            self.assertTrue(path.name.endswith(".md"))
            for section in [
                "为什么这个选题现在具有时效性",
                "当前研究现状",
                "高潜力研究缺口",
                "标题建议",
                "值得重点阅读",
                "潜在风险提示",
            ]:
                self.assertIn(section, text)


if __name__ == "__main__":
    unittest.main()
