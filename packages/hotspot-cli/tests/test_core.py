import tempfile
import unittest
from pathlib import Path

from hotspot_cli.config import ConfigManager
from hotspot_cli.distribution import LarkChannel
from hotspot_cli.hotspots import HotspotCandidate, HotspotFilter, HotspotService


class CoreTests(unittest.TestCase):
    def test_config_manager_round_trip_and_reset(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = ConfigManager(Path(td) / "config.json")

            manager.update_lark(chat_id="oc_123", identity="bot", message_template="简报：{topic}")

            loaded = manager.load()
            self.assertEqual(loaded.lark.chat_id, "oc_123")
            self.assertEqual(loaded.lark.identity, "bot")
            self.assertEqual(loaded.lark.message_template, "简报：{topic}")

            manager.reset()
            self.assertEqual(manager.load().lark.chat_id, "")

    def test_hotspot_filter_keeps_objective_industry_items(self) -> None:
        candidates = [
            HotspotCandidate(
                title="具身智能机器人获得新一轮融资并发布产业政策",
                domain="人工智能",
                score=42,
                sources=["github", "hn"],
                evidence="github stars=21; HN comments=42; policy signal",
                source_urls=["https://example.com/robotics"],
            ),
            HotspotCandidate(
                title="明星八卦带火AI概念币短线暴涨",
                domain="娱乐",
                score=100,
                sources=["reddit"],
                evidence="reddit score=999",
                source_urls=["https://example.com/hype"],
            ),
        ]

        kept = HotspotFilter().filter(candidates)

        self.assertEqual([item.title for item in kept], ["具身智能机器人获得新一轮融资并发布产业政策"])

    def test_hotspot_service_refresh_returns_different_batch(self) -> None:
        batches = [
            [HotspotCandidate("A", "AI", 10, ["github"], "github stars=10", ["u1"])],
            [HotspotCandidate("B", "AI", 11, ["hn"], "HN comments=11; policy signal", ["u2"])],
        ]
        service = HotspotService(collector=lambda topic, offset=0: batches[offset])

        first = service.top_hotspots("AI")
        second = service.top_hotspots("AI", refresh_index=1)

        self.assertEqual(first[0].title, "A")
        self.assertEqual(second[0].title, "B")

    def test_lark_channel_builds_message_and_file_commands(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            brief = Path(td) / "brief.md"
            brief.write_text("hello", encoding="utf-8")
            calls: list[list[str]] = []
            channel = LarkChannel(runner=lambda argv, cwd=None: calls.append(argv + ([f"cwd={cwd}"] if cwd else [])) or "ok")

            channel.send(
                chat_id="oc_abc",
                topic="个人手机智能体",
                summary="这是简介",
                report_path=brief,
                identity="bot",
                message_template="选题：{topic}\n简介：{summary}",
            )

            self.assertEqual(calls[0][:3], ["lark-cli", "im", "+messages-send"])
            self.assertIn("--chat-id", calls[0])
            self.assertTrue(any("选题：个人手机智能体" in arg for arg in calls[0]))
            self.assertEqual(calls[1][:3], ["lark-cli", "im", "+messages-send"])
            self.assertIn("--file", calls[1])
            self.assertIn("brief.md", calls[1])


if __name__ == "__main__":
    unittest.main()
