"""数据目录切换的单元与接口测试。

每个用例都在临时目录里跑，绝不碰真实用户数据：
- JDSCOPE_CONFIG 指向临时配置根；
- JDSCOPE_HOME 在需要「模拟已被环境变量锁定」的用例里单独设置。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, db, location  # noqa: E402


class LocationBase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("JDSCOPE_CONFIG", "JDSCOPE_HOME")}
        self._tmp = tempfile.mkdtemp(prefix="jdscope-loc-")
        self.root = Path(self._tmp) / "config"
        os.environ["JDSCOPE_CONFIG"] = str(self.root)
        os.environ.pop("JDSCOPE_HOME", None)
        config.ensure_dirs(config.data_home())
        conn = db.connect()
        db.init_db(conn)
        conn.execute("INSERT OR REPLACE INTO settings(k, v) VALUES('probe','v1')")
        conn.commit()
        conn.close()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _read_probe(self, home: Path) -> str:
        conn = db.connect(home / config.DB_NAME)
        try:
            row = conn.execute("SELECT v FROM settings WHERE k='probe'").fetchone()
            return row["v"] if row else ""
        finally:
            conn.close()


class TestLocationSwitch(LocationBase):
    def test_default_is_config_root(self):
        self.assertEqual(config.data_home(), self.root)
        self.assertEqual(config.data_home_source(), "default")

    def test_switch_requires_absolute_path(self):
        with self.assertRaises(location.SwitchError):
            location.switch_to("relative-dir")

    def test_switch_rejects_same_path(self):
        with self.assertRaises(location.SwitchError):
            location.switch_to(str(self.root))

    def test_switch_migrates_database(self):
        target = Path(self._tmp) / "data2"
        result = location.switch_to(str(target), migrate=True)
        self.assertTrue(result["ok"])
        self.assertEqual(config.data_home(), target)
        self.assertEqual(config.data_home_source(), "custom")
        self.assertEqual(self._read_probe(target), "v1")
        pointer = json.loads((self.root / config.LOCATION_FILE).read_text(encoding="utf-8"))
        self.assertEqual(pointer["data_home"], str(target))

    def test_switch_without_migration_leaves_new_empty_db(self):
        target = Path(self._tmp) / "data3"
        result = location.switch_to(str(target), migrate=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["copied_files"], 0)
        self.assertEqual(self._read_probe(target), "")

    def test_refuses_existing_database_while_migrating(self):
        target = Path(self._tmp) / "occupied"
        target.mkdir(parents=True)
        # 目标里已有一份别的库
        with db.connect(target / config.DB_NAME) as conn:
            db.init_db(conn)
            conn.execute("INSERT OR REPLACE INTO settings(k, v) VALUES('probe','other')")
            conn.commit()
        with self.assertRaises(location.SwitchError):
            location.switch_to(str(target), migrate=True)
        # 失败不能改指针
        self.assertEqual(config.data_home(), self.root)

    def test_adopts_existing_database_when_not_migrating(self):
        target = Path(self._tmp) / "occupied"
        target.mkdir(parents=True)
        with db.connect(target / config.DB_NAME) as conn:
            db.init_db(conn)
            conn.execute("INSERT OR REPLACE INTO settings(k, v) VALUES('probe','other')")
            conn.commit()
        result = location.switch_to(str(target), migrate=False)
        self.assertTrue(result["adopted"])
        self.assertEqual(self._read_probe(target), "other")

    def test_reset_returns_to_default(self):
        target = Path(self._tmp) / "data4"
        location.switch_to(str(target), migrate=True)
        back = location.reset(migrate=True)
        self.assertTrue(back["ok"])
        self.assertEqual(config.data_home(), self.root)
        self.assertEqual(config.data_home_source(), "default")
        self.assertFalse((self.root / config.LOCATION_FILE).exists())

    def test_env_locked_rejects_switch(self):
        os.environ["JDSCOPE_HOME"] = str(self.root)
        self.assertEqual(config.data_home_source(), "env")
        with self.assertRaises(location.SwitchError):
            location.switch_to(str(Path(self._tmp) / "nope"))

    def test_corrupt_pointer_falls_back(self):
        (self.root / config.LOCATION_FILE).write_text("{ not json", encoding="utf-8")
        self.assertEqual(config.data_home(), self.root)
        self.assertEqual(config.data_home_source(), "default")

    def test_describe_reports_state(self):
        info = location.describe()
        self.assertEqual(info["home"], str(self.root))
        self.assertEqual(info["source"], "default")
        self.assertFalse(info["env_locked"])
        self.assertTrue(info["has_db"])
        self.assertTrue(info["writable"])


class TestFastApiClientHttp(unittest.TestCase):
    """接口层冒烟：data-dir 能读、非法路径给明确错误。"""

    @classmethod
    def setUpClass(cls):
        import threading
        from app.api import make_server

        cls._saved = {k: os.environ.get(k) for k in ("JDSCOPE_CONFIG", "JDSCOPE_HOME")}
        cls._tmp = tempfile.mkdtemp(prefix="jdscope-loc-api-")
        os.environ["JDSCOPE_CONFIG"] = cls._tmp
        os.environ.pop("JDSCOPE_HOME", None)
        cls.httpd = make_server(0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        for key, value in cls._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        import shutil
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def call(self, path, method="GET", body=None):
        import urllib.error
        import urllib.request

        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read().decode("utf-8"))

    def test_get_data_dir(self):
        info = self.call("/api/data-dir")
        self.assertIn("home", info)
        self.assertIn(info["source"], ("default", "custom", "env"))

    def test_post_relative_path_returns_error(self):
        out = self.call("/api/data-dir", "POST", {"path": "somewhere"})
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
