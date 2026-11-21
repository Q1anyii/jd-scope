"""数据目录切换：校验 → 迁移 → 原子落指针。

数据库连接是「每次请求新建、用完即关」，所以切换数据目录不需要重启进程，
下一次请求自然连到新库。切换失败的每一步都先验证再落指针，绝不会把指针指到
一个打不开的目录上。
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from . import config, db


class SwitchError(Exception):
    """用户侧可预期的错误，直接把 message 展示到界面。"""


def _nearest_existing(path: Path) -> Path:
    cur = path
    while not cur.exists() and cur != cur.parent:
        cur = cur.parent
    return cur


def _probe_writable(path: Path) -> bool:
    base = _nearest_existing(path)
    probe = base / f".jdscope-write-probe-{os.getpid()}"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def describe() -> dict:
    """当前数据位置的完整状态，供设置页展示。"""
    home = config.data_home()
    dbfile = home / config.DB_NAME
    source = config.data_home_source()
    return {
        "home": str(home),
        "config_root": str(config.config_root()),
        "source": source,
        "env_locked": source == "env",
        "exists": home.exists(),
        "has_db": dbfile.is_file(),
        "db_bytes": dbfile.stat().st_size if dbfile.is_file() else 0,
        "writable": _probe_writable(home),
    }


def _normalize(raw: str) -> Path:
    text = (raw or "").strip().strip('"')
    if not text:
        raise SwitchError("请填写数据目录路径")
    if "\x00" in text:
        raise SwitchError("路径包含非法字符")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise SwitchError("请填写绝对路径，例如 D:\\JDScopeData")
    return config._abs(path)


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def _checkpoint(db_file: Path) -> None:
    """把 WAL 合并回主库，尽量让复制出来的是单一文件。"""
    if not db_file.is_file():
        return
    for attempt in range(6):
        try:
            conn = sqlite3.connect(str(db_file))
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
            return
        except sqlite3.Error:
            time.sleep(0.12 * (attempt + 1))
    # 拿不到排他锁也不阻断：下面会连 -wal/-shm 一起复制，SQLite 能自行恢复


def _copy_payload(src: Path, dst: Path) -> int:
    """复制数据库与报告/备份目录，返回复制的文件数。"""
    _checkpoint(src / config.DB_NAME)
    copied = 0
    for name in (config.DB_NAME, config.DB_NAME + "-wal", config.DB_NAME + "-shm"):
        source = src / name
        if not source.is_file():
            continue
        shutil.copy2(source, dst / name)
        copied += 1
    for sub in ("reports", "backups"):
        source_dir = src / sub
        if not source_dir.is_dir():
            continue
        target_dir = dst / sub
        target_dir.mkdir(parents=True, exist_ok=True)
        for item in source_dir.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(source_dir)
            out = target_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, out)
            copied += 1
    return copied


def _verify(db_file: Path) -> None:
    try:
        with db.connect(db_file) as conn:
            db.init_db(conn)
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        raise SwitchError(f"目标目录无法建立数据库：{exc}") from exc


def switch_to(raw: str, migrate: bool = True) -> dict:
    if config.data_home_source() == "env":
        raise SwitchError("当前由环境变量 JDSCOPE_HOME 指定位置，需先移除该变量才能在界面切换")

    target = _normalize(raw)
    current = config.data_home()
    if _same(target, current):
        raise SwitchError("新位置与当前数据目录相同")
    if target.exists() and not target.is_dir():
        raise SwitchError("该路径已存在且不是文件夹")

    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SwitchError(f"无法创建目录：{exc.strerror or exc}") from exc
    if not _probe_writable(target):
        raise SwitchError("该目录不可写，请换一个位置")

    target_db = target / config.DB_NAME
    current_db = current / config.DB_NAME
    adopted = target_db.is_file()
    copied = 0

    if adopted:
        if migrate and current_db.is_file():
            raise SwitchError(
                "目标目录里已经有数据库（可能属于另一份副本）。"
                "请换一个空目录；或取消「迁移现有数据」，直接使用该目录里的数据"
            )
    elif migrate and current_db.is_file():
        copied = _copy_payload(current, target)

    _verify(target_db)
    config.set_data_home(target)
    config.ensure_dirs(target)
    return {
        "ok": True,
        "home": str(target),
        "adopted": adopted,
        "copied_files": copied,
        "source": config.data_home_source(),
    }


def reset(migrate: bool = True) -> dict:
    if config.data_home_source() == "env":
        raise SwitchError("当前由环境变量 JDSCOPE_HOME 指定位置，需先移除该变量")

    current = config.data_home()
    default = config.config_root()
    if current == default:
        raise SwitchError("当前已经在默认数据目录")

    try:
        default.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SwitchError(f"无法创建默认目录：{exc.strerror or exc}") from exc

    default_db = default / config.DB_NAME
    adopted = default_db.is_file()
    copied = 0
    if not adopted and migrate and (current / config.DB_NAME).is_file():
        copied = _copy_payload(current, default)

    _verify(default_db)
    config.set_data_home(None)
    config.ensure_dirs(default)
    return {"ok": True, "home": str(default), "adopted": adopted,
            "copied_files": copied, "source": "default"}


def open_folder() -> dict:
    home = config.ensure_dirs()
    try:
        if sys.platform == "win32":
            os.startfile(str(home))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(home)])
        else:
            subprocess.Popen(["xdg-open", str(home)])
    except OSError as exc:
        raise SwitchError(f"无法打开目录：{exc}") from exc
    return {"ok": True, "home": str(home)}
