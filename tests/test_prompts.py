"""设置页提示词：默认值、保存/恢复默认，以及两类任务实际使用自定义提示词。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, llm  # noqa: E402


class TestPromptSettings(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("JDSCOPE_CONFIG", "JDSCOPE_HOME")}
        self._tmp = tempfile.mkdtemp(prefix="jdscope-prompt-")
        os.environ["JDSCOPE_CONFIG"] = self._tmp
        os.environ.pop("JDSCOPE_HOME", None)
        config.ensure_dirs(config.data_home())
        from app.api import Api

        self.api = Api()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_defaults_and_roundtrip(self):
        cfg = self.api.get_settings(None, None, {})
        self.assertEqual(cfg["prompt_defaults"]["jd_analysis"], llm.SYSTEM_PARSE)
        self.assertEqual(cfg["prompt_defaults"]["resume_rewrite"], llm.SYSTEM_SUGGEST)
        self.assertEqual(cfg["prompts"], {"jd_analysis": "", "resume_rewrite": ""})

        self.assertTrue(self.api.save_settings(
            None, {"prompts": {"jd_analysis": "自定义 JD", "resume_rewrite": "自定义改写"}}, {}
        )["ok"])
        cfg = self.api.get_settings(None, None, {})
        self.assertEqual(cfg["prompts"]["jd_analysis"], "自定义 JD")
        self.assertEqual(cfg["prompts"]["resume_rewrite"], "自定义改写")

        # 传默认原文等价于清掉覆盖；传空值也恢复默认
        self.api.save_settings(None, {"prompts": {"jd_analysis": llm.SYSTEM_PARSE}}, {})
        self.api.save_settings(None, {"prompts": {"resume_rewrite": ""}}, {})
        cfg = self.api.get_settings(None, None, {})
        self.assertEqual(cfg["prompts"], {"jd_analysis": "", "resume_rewrite": ""})

    def test_overlong_prompt_rejected(self):
        out = self.api.save_settings(None, {"prompts": {"jd_analysis": "x" * 20001}}, {})
        self.assertIn("error", out)

    def test_custom_prompt_reaches_both_models(self):
        cfg = {
            "base_url": "http://stub", "api_key": "k", "model": "m",
            "prompts": {"jd_analysis": "CUSTOM-JD", "resume_rewrite": "CUSTOM-REWRITE"},
        }
        with patch("app.llm.chat", return_value='{"items":[]}') as chat:
            llm.parse_jd_items(cfg, "JD 原文")
            self.assertEqual(chat.call_args.args[1][0]["content"], "CUSTOM-JD")

            llm.suggest_rewrite(cfg, "JD", "简历")
            self.assertEqual(chat.call_args.args[1][0]["content"], "CUSTOM-REWRITE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
