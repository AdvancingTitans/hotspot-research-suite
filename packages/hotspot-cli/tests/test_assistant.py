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
