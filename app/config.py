"""运行时配置与路径解析。

路径分成两层：

- **配置根** ``config_root()``：固定位置，只放一个 ``location.json``，用来记住
  「用户把数据放到哪了」。它不随数据位置变化，所以不会出现「指针存在指针里」的鸡生蛋问题。
- **数据目录** ``data_home()``：数据库、导出报告、备份都在这里，可以被用户改到任意盘。

解析优先级：``JDSCOPE_HOME`` 环境变量 > ``location.json`` 里的自定义路径 > 配置根。
环境变量一旦设置即视为「由外部锁定」，界面上不再允许切换。
``JDSCOPE_CONFIG`` 可单独改变配置根（自测用，避免读到真实用户的位置指针）。

设计约定：仓库内不出现任何绝对路径、也不出现任何个人数据。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "JDScope"
APP_VERSION = "0.3.4"

# 仓库内的静态资源根目录（打包后为 PyInstaller 解包目录）
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIR = BASE_DIR / "app" / "web"
ASSETS_DIR = BASE_DIR / "assets"

LOCATION_FILE = "location.json"
DB_NAME = "jdscope.db"


def _abs(path: Path | str) -> Path:
    """转绝对路径。

    刻意不用 ``Path.resolve()``：Windows 上它会把带 8.3 别名的目录（如
    ``CACHEM~1``）改写成短名，界面里就会显示出一个陌生的路径。
    """
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def config_root() -> Path:
    """配置根：存放位置指针，位置永不变。"""
    explicit = os.environ.get("JDSCOPE_CONFIG")
    if explicit:
        return _abs(explicit)
    override = os.environ.get("JDSCOPE_HOME")
    if override:
        # 只设了数据目录时，指针也放那儿，方便整体隔离
        return _abs(override)
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def _location_path() -> Path:
    return config_root() / LOCATION_FILE


def _read_location() -> Path | None:
    """读位置指针。文件损坏或为空一律当作「没设置过」，不让坏数据卡住启动。"""
    try:
        raw = json.loads(_location_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = (raw or {}).get("data_home") if isinstance(raw, dict) else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Path(value).expanduser()
    except (OSError, ValueError):
        return None


def data_home_source() -> str:
    """数据目录来源：env / custom / default。"""
    if os.environ.get("JDSCOPE_HOME"):
        return "env"
    return "custom" if _read_location() is not None else "default"


def data_home() -> Path:
    override = os.environ.get("JDSCOPE_HOME")
    if override:
        return _abs(override)
    custom = _read_location()
    return _abs(custom) if custom is not None else config_root()


def set_data_home(path: Path | None) -> None:
    """写位置指针；``None`` 表示回到默认位置。先写临时文件再原子替换。"""
    root = config_root()
    root.mkdir(parents=True, exist_ok=True)
    target = _location_path()
    if path is None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return
    tmp = target.with_name(LOCATION_FILE + ".tmp")
    payload = {"data_home": str(path)}
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def ensure_dirs(home: Path | None = None) -> Path:
    home = home or data_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "reports").mkdir(parents=True, exist_ok=True)
    (home / "backups").mkdir(parents=True, exist_ok=True)
    return home


def db_path(home: Path | None = None) -> Path:
    return (home or data_home()) / DB_NAME


DEFAULT_LLM_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL = "deepseek-chat"

# 评分权重（四个维度，总和 100）
DEFAULT_WEIGHTS = {
    "must": 30.0,      # 必备要求覆盖
    "duty": 30.0,      # 职责同构度
    "nice": 15.0,      # 加分项覆盖
    "constraint": 25.0 # 硬性条件符合度
}

# 判定阈值
VERDICT_GO = 72.0
VERDICT_MAYBE = 55.0
