"""运行时配置与路径解析。

设计约定：
- 仓库内不出现任何绝对路径、也不出现任何个人数据。
- 所有可变数据（数据库、导出报告）放在用户数据目录，默认
  ``%LOCALAPPDATA%\\JDScope``，可用环境变量 ``JDSCOPE_HOME`` 覆盖。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "JDScope"
APP_VERSION = "0.1.0"

# 仓库内的静态资源根目录（打包后为 PyInstaller 解包目录）
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB_DIR = BASE_DIR / "app" / "web"
ASSETS_DIR = BASE_DIR / "assets"


def data_home() -> Path:
    """用户数据目录：数据库、导出报告都在这里，不进版本库。"""
    override = os.environ.get("JDSCOPE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def ensure_dirs() -> Path:
    home = data_home()
    (home).mkdir(parents=True, exist_ok=True)
    (home / "reports").mkdir(parents=True, exist_ok=True)
    (home / "backups").mkdir(parents=True, exist_ok=True)
    return home


def db_path() -> Path:
    return data_home() / "jdscope.db"


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
