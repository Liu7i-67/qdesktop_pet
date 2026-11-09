"""resources —— 资源路径解析（WP2）。

职责：为运行期统一解析 sprites/ 与 assets/ 的绝对路径，兼容两种运行形态：

- 开发态：从本文件位置（``app/resources.py``）向上逐级查找包含
  ``main.py`` 的目录，即项目根；
- PyInstaller 冻结态：单文件 exe 运行时资源被解包到 ``sys._MEIPASS``
  临时目录，直接以其为资源根（构建时需将 sprites/、assets/ 打入包内）。

对外接口（需求文档第 4 节契约）：
    base_dir() -> str      资源根目录
    sprite_dir() -> str    sprites/ 动画帧目录
    asset_path(name) -> str  assets/ 下资源文件的绝对路径
"""
from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["base_dir", "sprite_dir", "asset_path"]


def base_dir() -> str:
    """返回资源根目录（开发态=项目根；冻结态=PyInstaller 解包目录）。"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包运行
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return str(Path(meipass))
        # 兜底：无 _MEIPASS 时退回 exe 所在目录
        return str(Path(sys.executable).resolve().parent)

    here = Path(__file__).resolve().parent  # .../app
    for candidate in (here, *here.parents):
        if (candidate / "main.py").is_file():
            return str(candidate)
    # 兜底：目录结构异常时退回 app/ 的上级
    return str(here.parent)


def sprite_dir() -> str:
    """sprites/ 动画帧目录的绝对路径。"""
    return str(Path(base_dir()) / "sprites")


def asset_path(name: str) -> str:
    """assets/ 下名为 ``name`` 的资源文件的绝对路径（如 ``tray.png``）。"""
    return str(Path(base_dir()) / "assets" / str(name))
