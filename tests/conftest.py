"""pytest 公共夹具（WP5 测试基建）。

职责：
- 在 import PySide6 之前强制 offscreen 平台（QT_QPA_PLATFORM）；
- session 级 ``qapp``：QApplication 单例（带清理）；
- ``sprites_dir``：用 Pillow 在 tmp_path 生成假精灵帧目录（各动画帧数按契约表）；
- ``fake_window`` / ``fake_animator``：按需求文档第 4 节契约用 QObject+Signal
  实现的最小假对象，供 PetController 测试注入。

说明：tests/ 目录不放 __init__.py，pytest 会把 tests/ 加入 sys.path，
因此用例可用 ``from conftest import ...`` 复用本模块的常量与工具函数。
"""

import os

# 必须先于任何 PySide6 导入设置，否则窗口/托盘测试在无显示环境下无法运行
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))  # 保证 `import main`、`from app...` 可用

import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# 需求文档第 4 节《动画资产契约》常量（帧数 / 默认 fps，含 v2 修订 walk_side）
# ---------------------------------------------------------------------------
CONTRACT_FRAME_COUNTS = {
    "idle": 4,
    "walk": 8,
    "walk_side": 8,
    "jump": 6,
    "drag": 2,
    "quack": 4,
    "happy": 4,
    "surprised": 2,
    "sleep": 2,
}

CONTRACT_DEFAULT_FPS = {
    "idle": 3.0,
    "walk": 10.0,
    "walk_side": 10.0,
    "jump": 12.0,
    "drag": 6.0,
    "quack": 8.0,
    "happy": 6.0,
    "surprised": 6.0,
    "sleep": 2.0,
}

# 帧序号标记色：第 i 帧的底部色带使用 FRAME_MARKER_PALETTE[i]，
# 用例按“最近邻色”把像素解码回帧序号（各颜色相互距离足够大）。
FRAME_MARKER_PALETTE = [
    (229, 57, 53),    # 0 红
    (30, 136, 229),   # 1 蓝
    (67, 160, 71),    # 2 绿
    (251, 192, 45),   # 3 黄
    (142, 36, 170),   # 4 紫
    (0, 151, 167),    # 5 青
    (255, 112, 67),   # 6 橙
    (84, 110, 122),   # 7 蓝灰
]


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def wait_until(predicate, timeout_ms=3000, step_ms=40):
    """在事件循环中等待条件成立（统一 QTest.qWait，不使用 time.sleep 轮询）。

    返回 True 表示条件成立；超时后返回最后一次 predicate() 的值。
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return predicate()
        QTest.qWait(step_ms)


# ---------------------------------------------------------------------------
# QApplication 单例
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def qapp():
    """session 级 QApplication 单例；会话结束时关闭残留顶层窗口并排空事件。"""
    app = QApplication.instance() or QApplication([])
    yield app
    for widget in list(QApplication.topLevelWidgets()):
        widget.close()
    app.processEvents()


# ---------------------------------------------------------------------------
# 假精灵帧目录（64×64 RGBA）
# ---------------------------------------------------------------------------
@pytest.fixture()
def sprites_dir(tmp_path):
    """生成假精灵帧目录并返回路径字符串。

    帧内容设计（64×64，便于断言）：
    - 左半纯红、右半纯蓝：水平非对称，供 T3 镜像断言逐点比对；
    - 底部 16px 色带 = FRAME_MARKER_PALETTE[i]：供帧序/回绕/末帧断言解码帧号。
    帧数严格按契约表：idle 4 / walk 8 / jump 6 / drag 2 / quack 4 /
    happy 4 / surprised 2 / sleep 2。
    """
    root = tmp_path / "sprites"
    root.mkdir()
    for anim, count in CONTRACT_FRAME_COUNTS.items():
        for i in range(count):
            img = Image.new("RGBA", (64, 64), (245, 245, 245, 255))
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 0, 31, 63], fill=(220, 40, 40, 255))   # 左半红
            draw.rectangle([32, 0, 63, 63], fill=(40, 80, 220, 255))  # 右半蓝
            r, g, b = FRAME_MARKER_PALETTE[i % len(FRAME_MARKER_PALETTE)]
            draw.rectangle([0, 48, 63, 63], fill=(r, g, b, 255))      # 底部序号色带
            img.save(str(root / f"{anim}_{i:02d}.png"))
    return str(root)


# ---------------------------------------------------------------------------
# 契约假对象：FakeAnimator / FakeWindow
# ---------------------------------------------------------------------------
class FakeAnimator(QObject):
    """按契约模拟 SpriteAnimator（app/sprite_animator.py）。

    - 记录每次 play/stop 调用（play_calls / stop_calls）；
    - 非循环动画按契约时长（帧数/fps）自动补发 animation_finished，
      与真实 SpriteAnimator 的对外行为一致；auto_finish=False 可关闭。
    """

    frame_changed = Signal(QPixmap)
    animation_finished = Signal(str)

    def __init__(self):
        super().__init__()
        self.play_calls = []  # [(name, loop, fps, flipped)]
        self.stop_calls = 0
        self.auto_finish = True
        self._current = ""
        self._finish_timer = QTimer(self)
        self._finish_timer.setSingleShot(True)
        self._finish_timer.timeout.connect(self._emit_finished)

    @staticmethod
    def duration_ms(name, fps=None):
        """按契约帧数/fps 计算动画时长（毫秒）。"""
        frames = CONTRACT_FRAME_COUNTS.get(name, 1)
        rate = float(fps) if fps else CONTRACT_DEFAULT_FPS.get(name, 6.0)
        return frames / rate * 1000.0

    def play(self, name, loop=True, fps=None, flipped=False):
        self.play_calls.append((name, bool(loop), fps, bool(flipped)))
        self._current = str(name)
        self._finish_timer.stop()
        if self.auto_finish and not loop:
            self._finish_timer.start(int(round(self.duration_ms(name, fps))))

    def _emit_finished(self):
        self.animation_finished.emit(self._current)

    def current_animation(self):
        return self._current

    def stop(self):
        self.stop_calls += 1
        self._finish_timer.stop()

    def play_count(self, name):
        return sum(1 for call in self.play_calls if call[0] == name)


class FakeWindow(QObject):
    """按契约模拟 PetWindow（app/pet_window.py）。

    - 虚拟主屏工作区 1920×1040（QRect），窗口固定 150×150；
    - move_to 按契约钳制在 screen_rect 内；
    - 提供 emit_* 辅助方法模拟用户交互（发射真实 Qt 信号）。
    """

    clicked = Signal()
    double_clicked = Signal()
    drag_started = Signal()
    drag_moved = Signal(QPoint)      # 窗口左上角全局坐标
    drag_released = Signal(QPoint)
    hover_entered = Signal()
    hover_left = Signal()

    SIZE = 150

    def __init__(self):
        super().__init__()
        self._screen = QRect(0, 0, 1920, 1040)
        self._pos = QPointF(400.0, 400.0)
        self._flipped = False
        self.move_to_calls = []   # [(x, y)]
        self.flips = []           # set_flipped 历史
        self.always_on_top = None

    # ---- 契约接口 ----
    def screen_rect(self):
        return QRect(self._screen)

    def floor_y(self):
        return int(self._screen.bottom() + 1 - self.SIZE)

    def move_to(self, x, y):
        r = self._screen
        cx = min(max(float(x), float(r.left())), float(r.right() + 1 - self.SIZE))
        cy = min(max(float(y), float(r.top())), float(r.bottom() + 1 - self.SIZE))
        self._pos = QPointF(cx, cy)
        self.move_to_calls.append((cx, cy))

    def pos_f(self):
        return QPointF(self._pos)

    def set_flipped(self, flipped):
        self._flipped = bool(flipped)
        self.flips.append(bool(flipped))

    def apply_always_on_top(self, on):
        self.always_on_top = bool(on)

    # ---- 兼容辅助：控制器若按 QWidget 习惯调用这些方法时不至于崩溃 ----
    def width(self):
        return self.SIZE

    def height(self):
        return self.SIZE

    def pos(self):
        return self._pos.toPoint()

    # ---- 测试辅助：窗口底部全局 y（= pos.y + 高）----
    def window_bottom(self):
        return self._pos.y() + self.SIZE

    def is_flipped(self):
        return self._flipped

    # ---- 测试辅助：模拟交互信号 ----
    def emit_click(self):
        self.clicked.emit()

    def emit_double_click(self):
        self.double_clicked.emit()

    def emit_hover_entered(self):
        self.hover_entered.emit()

    def emit_hover_left(self):
        self.hover_left.emit()

    def emit_drag_started(self):
        self.drag_started.emit()

    def emit_drag_moved(self, x, y):
        self.drag_moved.emit(QPoint(int(x), int(y)))

    def emit_drag_released(self, x, y):
        self.drag_released.emit(QPoint(int(x), int(y)))


@pytest.fixture()
def fake_animator():
    obj = FakeAnimator()
    yield obj
    obj.stop()
    obj.deleteLater()


@pytest.fixture()
def fake_window():
    obj = FakeWindow()
    yield obj
    obj.deleteLater()
