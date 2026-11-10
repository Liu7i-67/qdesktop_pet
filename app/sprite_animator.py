"""SpriteAnimator —— 精灵逐帧动画播放器（WP2）。

严格实现需求文档第 4 节契约：

- 帧文件约定 ``{sprite_dir}/{name}_{i:02d}.png``，从 00 开始连续编号；
  缺失（没有任何帧）或编号不连续时 ``play`` 抛 ``ValueError``；
- QTimer 按 fps 推帧：严格逐帧推进 0,1,2,…,N-1 循环回绕，不做跳帧追赶；
- ``loop=False`` 的单播动画播完停在末帧，且恰好发射一次
  ``animation_finished(name)``；
- ``flipped=True`` 时每帧 QPixmap 水平镜像（QTransform 镜像变换）；
- 帧统一按 ``logical_size``（默认 150）SmoothTransformation 缩放后经
  ``frame_changed(QPixmap)`` 发射；
- ``fps=None`` 使用各动画默认 fps 表（与第 4 节资产契约一致）；
- ``play`` 播放新动画或同名重播都从头开始；``stop()`` 停定时器、不再发帧。
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QTransform

__all__ = ["SpriteAnimator", "DEFAULT_FPS"]

# 各动画默认 fps 表（fps=None 时使用；与需求文档第 4 节资产契约一致）
DEFAULT_FPS: dict[str, float] = {
    "idle": 3.0,
    "walk": 10.0,
    "walk_side": 10.0,
    "drag": 6.0,
    "jump": 12.0,
    "happy": 6.0,
    "quack": 8.0,
    "surprised": 6.0,
    "sleep": 2.0,
}
_FALLBACK_FPS = 6.0  # 表外自定义动画的兜底 fps


class SpriteAnimator(QObject):
    """按帧目录驱动的逐帧动画播放器。

    实现状态说明：``current_loop`` / ``current_fps`` 为最近一次 ``play``
    的参数快照，供 ``PetWindow.set_flipped`` 重发 ``play`` 时复用
    （契约方法之外仅此两个只读状态属性，行为契约不受影响）。
    """

    frame_changed = Signal(QPixmap)   # 每帧发射（已按 logical_size 缩放、已含翻转）
    animation_finished = Signal(str)  # 非循环动画播完，参数为动画名

    def __init__(self, sprite_dir: str, logical_size: int = 150) -> None:
        super().__init__()
        if int(logical_size) <= 0:
            raise ValueError(f"logical_size 必须为正整数，收到 {logical_size!r}")
        self._sprite_dir = Path(sprite_dir)
        self._logical_size = int(logical_size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._frames: list[QPixmap] = []  # 当前动画的原始帧（未缩放/未翻转）
        self._name = ""                   # 当前动画名（未播放过为空串）
        self._loop = True
        self._index = 0
        self._flipped = False

        self.current_loop = True          # 最近一次 play 的 loop 参数快照
        self.current_fps: float | None = None  # 最近一次 play 的 fps 参数快照

        self._cache: dict[str, QPixmap] = {}  # 已解码帧缓存，key=帧文件路径

    # ------------------------------------------------------------------
    # 契约接口
    # ------------------------------------------------------------------
    def play(
        self,
        name: str,
        loop: bool = True,
        fps: float | None = None,
        flipped: bool = False,
    ) -> None:
        """播放动画 ``name``；新动画或同名重播都从头开始。"""
        name = str(name)
        frames = self._load_frames(name)
        rate = self._resolve_fps(name, fps)
        if rate <= 0:
            raise ValueError(f"fps 必须为正数，收到 {fps!r}")

        self._timer.stop()  # 重播/换动画：先停旧定时器，从头开始
        self._frames = frames
        self._name = name
        self._loop = bool(loop)
        self._flipped = bool(flipped)
        self._index = 0
        self.current_loop = self._loop
        self.current_fps = None if fps is None else float(fps)

        self._timer.setInterval(max(1, int(round(1000.0 / rate))))
        self._emit_frame()  # 立即呈现第 0 帧，避免动画切换瞬间停留在旧画面
        self._timer.start()

    def current_animation(self) -> str:
        """返回当前动画名（尚未播放过任何动画时为空串）。"""
        return self._name

    def stop(self) -> None:
        """停止播放：停定时器，此后不再发射 frame_changed。"""
        self._timer.stop()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_fps(name: str, fps: float | None) -> float:
        if fps is None:
            return float(DEFAULT_FPS.get(name, _FALLBACK_FPS))
        return float(fps)

    def _probe_indices(self, name: str) -> list[int]:
        """探测 ``{name}_XX.png`` 的帧序号；要求从 00 开始连续编号。"""
        if not self._sprite_dir.is_dir():
            raise ValueError(
                f"动画 '{name}' 的帧目录不存在：{self._sprite_dir}"
            )
        pattern = re.compile(rf"^{re.escape(name)}_(\d+)\.png$")
        indices: list[int] = []
        for entry in self._sprite_dir.iterdir():
            matched = pattern.match(entry.name)
            if matched is not None and entry.is_file():
                indices.append(int(matched.group(1)))
        indices.sort()
        if not indices:
            raise ValueError(
                f"动画 '{name}' 在 {self._sprite_dir} 下没有任何帧文件"
                f"（期望 {name}_00.png 起连续编号）"
            )
        expected = list(range(indices[-1] + 1))
        if indices[0] != 0 or indices != expected:
            missing = sorted(set(expected) - set(indices))
            raise ValueError(
                f"动画 '{name}' 帧编号必须从 00 起连续：现有编号 {indices}，"
                f"缺失 {missing}"
            )
        return indices

    def _load_frames(self, name: str) -> list[QPixmap]:
        """按连续序号加载全部帧；缺失/编号不连续由 _probe_indices 抛 ValueError。"""
        frames: list[QPixmap] = []
        for index in self._probe_indices(name):
            path = self._sprite_dir / f"{name}_{index:02d}.png"
            key = str(path)
            pixmap = self._cache.get(key)
            if pixmap is None or pixmap.isNull():
                pixmap = QPixmap(key)
                if pixmap.isNull():
                    raise ValueError(f"帧文件无法解码：{path}")
                self._cache[key] = pixmap
            frames.append(pixmap)
        return frames

    def _on_tick(self) -> None:
        """定时器推帧：严格逐帧 +1（模 N 回绕）；单播到末帧即停并发完成信号。"""
        count = len(self._frames)
        if count == 0:
            self._timer.stop()
            return
        if not self._loop and self._index >= count - 1:
            self._timer.stop()  # 单播停在末帧
            self.animation_finished.emit(self._name)  # 恰好一次
            return
        self._index = (self._index + 1) % count  # 不做跳帧追赶
        self._emit_frame()

    def _emit_frame(self) -> None:
        """缩放（必要时镜像）当前帧并发射 frame_changed。"""
        if not self._frames:
            return
        index = min(self._index, len(self._frames) - 1)
        source = self._frames[index]
        frame = source.scaled(
            self._logical_size,
            self._logical_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._flipped:
            # PySide6 6.12 无 QTransform.mirrored；水平镜像等价于 -1 倍缩放变换
            frame = frame.transformed(
                QTransform.fromScale(-1.0, 1.0),
                Qt.TransformationMode.FastTransformation,  # 纯镜像无重采样
            )
        self.frame_changed.emit(frame)
