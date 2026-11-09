"""PetWindow 测试（真实 app.pet_window.PetWindow + 真实 SpriteAnimator；T4 另用真实 PetController）。

覆盖测试功能点：
- T4  贴底：controller.start() 后窗口底 = 所在屏 availableGeometry().bottom()+1；
- T5  钳制：move_to 越界值被钳制在 screen_rect() 内，屏内值原样生效；
- T6  拖拽流程：press→move(>6px)→release 依次发 drag_started/drag_moved/drag_released；
      press→move(≤6px)→release 只发 clicked；另覆盖双击与悬停信号；
- T14 冒烟：main 模块可导入（不执行入口）。

事件模拟采用“直接调用处理器方法 + 手工构造事件对象”（兼容 PySide6 6.12 / Qt6：
QMouseEvent(type, QPointF 局部, QPointF 全局, button, buttons, modifiers)，
globalPosition() 为 QPointF），避免依赖 QTest.mouseMove 在 offscreen 下的不确定性。
"""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from app.pet_controller import PetController
from app.pet_window import PetWindow
from app.sprite_animator import SpriteAnimator
from conftest import wait_until

WINDOW_SIZE = 150  # 契约：窗口固定 150×150 逻辑像素
POINT_TOL = 2      # 拖拽信号坐标容差（px）


# ---------------------------------------------------------------------------
# 夹具与事件构造辅助
# ---------------------------------------------------------------------------
@pytest.fixture()
def make_window(qapp, sprites_dir, request):
    """构造 (PetWindow, SpriteAnimator) 对，测试结束后统一清理。"""
    made = []

    def _make(**animator_kwargs):
        animator = SpriteAnimator(sprites_dir, **animator_kwargs)
        window = PetWindow(animator)
        window.show()
        QTest.qWait(20)
        made.append((window, animator))
        return window, animator

    def _cleanup():
        for window, animator in made:
            window.close()
            animator.stop()
            window.deleteLater()
            animator.deleteLater()

    request.addfinalizer(_cleanup)
    return _make


def _mouse_event(event_type, local, global_pos, button, buttons):
    """Qt6 签名构造 QMouseEvent：local/global 均为 QPointF。"""
    return QMouseEvent(
        event_type,
        QPointF(local),
        QPointF(global_pos),
        button,
        buttons,
        Qt.NoModifier,
    )


def _send_press(window, local, global_pos):
    window.mousePressEvent(_mouse_event(
        QEvent.MouseButtonPress, local, global_pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))


def _send_move(window, local, global_pos):
    window.mouseMoveEvent(_mouse_event(
        QEvent.MouseMove, local, global_pos,
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))


def _send_release(window, local, global_pos):
    window.mouseReleaseEvent(_mouse_event(
        QEvent.MouseButtonRelease, local, global_pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))


def _send_double_click(window, local, global_pos):
    window.mouseDoubleClickEvent(_mouse_event(
        QEvent.MouseButtonDblClick, local, global_pos,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))


class _SignalRecorder:
    """按发射顺序记录 PetWindow 全部信号（列表即信号顺序）。"""

    def __init__(self, window):
        self.order = []
        self.drag_points = []     # drag_moved(QPoint) 参数
        self.release_points = []  # drag_released(QPoint) 参数
        window.clicked.connect(lambda: self.order.append("clicked"))
        window.double_clicked.connect(lambda: self.order.append("double_clicked"))
        window.drag_started.connect(lambda: self.order.append("drag_started"))
        window.drag_moved.connect(self._on_drag_moved)
        window.drag_released.connect(self._on_drag_released)
        window.hover_entered.connect(lambda: self.order.append("hover_entered"))
        window.hover_left.connect(lambda: self.order.append("hover_left"))

    def _on_drag_moved(self, point):
        self.order.append("drag_moved")
        self.drag_points.append(QPoint(point))

    def _on_drag_released(self, point):
        self.order.append("drag_released")
        self.release_points.append(QPoint(point))


def _assert_point_near(actual, expected, tol=POINT_TOL, what="点"):
    dx = abs(actual.x() - expected.x())
    dy = abs(actual.y() - expected.y())
    assert dx <= tol and dy <= tol, (
        f"{what}应为 {expected.x()},{expected.y()}（±{tol}px），实际 {actual.x()},{actual.y()}"
    )


# ---------------------------------------------------------------------------
# T4 贴底
# ---------------------------------------------------------------------------
def test_t4_start_snaps_window_to_screen_bottom(qapp, sprites_dir, request):
    """T4：controller.start() 后窗口底 = 所在屏 availableGeometry().bottom()+1，且开始踱步。"""
    animator = SpriteAnimator(sprites_dir)
    window = PetWindow(animator)
    window.show()
    QTest.qWait(20)
    controller = PetController(window, animator)
    controller.start()

    def _cleanup():
        stop = getattr(controller, "stop", None)
        if callable(stop):
            stop()
        window.close()
        animator.stop()
        controller.deleteLater()
        window.deleteLater()
        animator.deleteLater()

    request.addfinalizer(_cleanup)

    available = QApplication.primaryScreen().availableGeometry()

    # floor_y / screen_rect 契约
    assert window.screen_rect() == available, (
        f"screen_rect() 应返回所在屏 availableGeometry()，实际 {window.screen_rect()}"
    )
    assert window.floor_y() == available.bottom() + 1 - window.height(), (
        f"floor_y() 应为 availableGeometry().bottom()+1-窗口高"
        f"（{available.bottom() + 1 - window.height()}），实际 {window.floor_y()}"
    )

    snapped = wait_until(
        lambda: abs((window.y() + window.height()) - (available.bottom() + 1)) <= 1,
        timeout_ms=2500,
    )
    assert snapped, (
        f"start() 后窗口底应为 {available.bottom() + 1}（屏幕底部+1），"
        f"实际 {window.y() + window.height()}（T4）"
    )

    # 踱步开始：水平位置应发生变化
    x0 = window.x()
    moved = wait_until(lambda: window.x() != x0, timeout_ms=3000)
    assert moved, "start() 进入 WALK 后窗口应开始水平踱步"

    QTest.qWait(300)
    assert abs((window.y() + window.height()) - (available.bottom() + 1)) <= 1, (
        "踱步过程中窗口应保持贴底（y 不离地）"
    )


# ---------------------------------------------------------------------------
# T5 钳制
# ---------------------------------------------------------------------------
def test_t5_move_to_clamps_into_screen_rect(qapp, make_window):
    """T5：move_to 越界值被钳制在 screen_rect() 内；屏内合法值原样生效。"""
    window, _animator = make_window()
    rect = window.screen_rect()

    # 左上越界 → 钳制到屏幕左上角，且整窗仍在屏内
    window.move_to(-500, -500)
    pos = window.pos_f()
    assert pos.x() >= rect.left() - 1 and pos.y() >= rect.top() - 1, (
        f"move_to(-500,-500) 应钳制到 screen_rect 左上角，实际 {pos.x()},{pos.y()}（T5）"
    )
    assert pos.x() + window.width() <= rect.right() + 2, "钳制后窗口不得超出屏幕右缘"
    assert pos.y() + window.height() <= rect.bottom() + 2, "钳制后窗口不得超出屏幕下缘"

    # 右下越界 → 钳制到右下角，窗口底贴 screen_rect.bottom()+1
    window.move_to(10 ** 6, 10 ** 6)
    pos = window.pos_f()
    assert pos.x() + window.width() <= rect.right() + 2, "move_to(超大x) 应钳制窗口在屏内"
    bottom = pos.y() + window.height()
    assert abs(bottom - (rect.bottom() + 1)) <= 1, (
        f"move_to(超大y) 后窗口底应贴 screen_rect.bottom()+1={rect.bottom() + 1}，实际 {bottom}"
    )

    # 屏内合法值应原样生效
    window.move_to(300, 200)
    pos = window.pos_f()
    assert abs(pos.x() - 300) <= 0.6 and abs(pos.y() - 200) <= 0.6, (
        f"屏内 move_to(300,200) 应原样生效，实际 {pos.x()},{pos.y()}（T5）"
    )


# ---------------------------------------------------------------------------
# T6 拖拽流程 / 单击 / 双击 / 悬停
# ---------------------------------------------------------------------------
def test_t6_drag_flow_signal_order_and_args(qapp, make_window):
    """T6：press→move>6px→release 依次发 drag_started/drag_moved/drag_released，
    drag_moved 参数为“窗口左上角全局坐标”（全局光标位置-按下锚点）。"""
    window, _animator = make_window()
    recorder = _SignalRecorder(window)

    window.move_to(100, 100)
    base = window.pos()                      # QPoint(100,100)
    anchor = QPoint(75, 75)                  # 按下锚点（窗口局部坐标）
    press_global = base + anchor             # (175,175)

    _send_press(window, anchor, press_global)
    assert recorder.order == [], "仅按下未移动时不应发射任何信号"

    # 第一次移动：水平 40px > 6px 阈值 → 触发拖拽（drag_started 一次 + drag_moved）
    g1 = press_global + QPoint(40, 10)
    _send_move(window, anchor, g1)           # 拖拽期间光标相对窗口局部坐标恒为锚点
    expected_topleft1 = g1 - anchor          # 新的窗口左上角全局坐标
    assert recorder.order == ["drag_started", "drag_moved"], (
        f"移动 >6px 应依次发射 drag_started、drag_moved，实际 {recorder.order}（T6）"
    )
    _assert_point_near(recorder.drag_points[0], expected_topleft1,
                       what="drag_moved 参数（窗口左上角全局坐标）")

    # 第二次移动：继续发 drag_moved，且 drag_started 不再重复
    g2 = g1 + QPoint(10, 0)
    _send_move(window, anchor, g2)
    assert recorder.order == ["drag_started", "drag_moved", "drag_moved"], (
        f"继续移动应再发 drag_moved 且 drag_started 只发一次，实际 {recorder.order}（T6）"
    )
    _assert_point_near(recorder.drag_points[1], g2 - anchor,
                       what="第二次 drag_moved 参数")

    # 松手：drag_released，参数同语义（窗口左上角全局坐标）
    _send_release(window, anchor, g2)
    assert recorder.order == ["drag_started", "drag_moved", "drag_moved", "drag_released"], (
        f"松手后完整序列应为 started→moved→moved→released，实际 {recorder.order}（T6）"
    )
    _assert_point_near(recorder.release_points[0], g2 - anchor,
                       what="drag_released 参数（窗口左上角全局坐标）")
    assert "clicked" not in recorder.order, "拖拽流程不应误发 clicked"


def test_t6_short_press_emits_clicked_only(qapp, make_window):
    """T6：press→move≤6px→release 只发 clicked，不发任何拖拽信号。"""
    window, _animator = make_window()
    recorder = _SignalRecorder(window)

    window.move_to(100, 100)
    base = window.pos()
    anchor = QPoint(75, 75)
    press_global = base + anchor

    _send_press(window, anchor, press_global)
    _send_move(window, anchor, press_global + QPoint(3, 0))   # 仅 3px < 6px 阈值
    assert recorder.order == [], "移动 ≤6px 时不应触发拖拽信号"

    _send_release(window, anchor, press_global + QPoint(3, 0))
    assert recorder.order == ["clicked"], (
        f"位移不足阈值时松手应只发 clicked，实际 {recorder.order}（T6）"
    )


def test_t6_press_release_without_move_emits_clicked(qapp, make_window):
    """T6 补充：原地按下即松手（无移动）应只发 clicked。"""
    window, _animator = make_window()
    recorder = _SignalRecorder(window)

    window.move_to(120, 120)
    anchor = QPoint(75, 75)
    press_global = window.pos() + anchor
    _send_press(window, anchor, press_global)
    _send_release(window, anchor, press_global)
    assert recorder.order == ["clicked"], (
        f"原地单击应只发 clicked，实际 {recorder.order}"
    )


def test_t6_double_click_emits_double_clicked(qapp, make_window):
    """契约补充：mouseDoubleClickEvent 应发射 double_clicked。"""
    window, _animator = make_window()
    recorder = _SignalRecorder(window)

    window.move_to(120, 120)
    anchor = QPoint(75, 75)
    _send_double_click(window, anchor, window.pos() + anchor)
    assert recorder.order == ["double_clicked"], (
        f"双击应发 double_clicked，实际 {recorder.order}"
    )


def test_hover_enter_leave_signals(qapp, make_window):
    """契约补充：enterEvent/leaveEvent 应分别发 hover_entered / hover_left。"""
    window, _animator = make_window()
    recorder = _SignalRecorder(window)

    anchor = QPointF(75, 75)
    window.enterEvent(QEnterEvent(anchor, anchor, QPointF(window.pos() + QPoint(75, 75))))
    window.leaveEvent(QEvent(QEvent.Leave))
    assert recorder.order == ["hover_entered", "hover_left"], (
        f"悬停进入/离开应依次发 hover_entered、hover_left，实际 {recorder.order}"
    )


# ---------------------------------------------------------------------------
# 窗口静态契约
# ---------------------------------------------------------------------------
def test_window_static_contract(qapp, make_window):
    """契约补充：150×150、无边框、Tool、StaysOnTop、半透明背景；置顶可开关。"""
    window, _animator = make_window()

    assert (window.width(), window.height()) == (WINDOW_SIZE, WINDOW_SIZE), (
        f"窗口应固定 {WINDOW_SIZE}×{WINDOW_SIZE} 逻辑像素，"
        f"实际 {window.width()}×{window.height()}"
    )

    flags = window.windowFlags()
    assert bool(flags & Qt.FramelessWindowHint), "应为无边框窗口（FramelessWindowHint）"
    assert bool(flags & Qt.Tool), "应为 Tool 窗口（不在任务栏显示）"
    assert bool(flags & Qt.WindowStaysOnTopHint), "默认应置顶（WindowStaysOnTopHint）"
    assert window.testAttribute(Qt.WA_TranslucentBackground), (
        "应启用 WA_TranslucentBackground（逐像素透明）"
    )

    window.apply_always_on_top(False)
    window.show()
    QTest.qWait(20)
    assert not (window.windowFlags() & Qt.WindowStaysOnTopHint), (
        "apply_always_on_top(False) 后应取消置顶"
    )
    window.apply_always_on_top(True)
    window.show()
    QTest.qWait(20)
    assert bool(window.windowFlags() & Qt.WindowStaysOnTopHint), (
        "apply_always_on_top(True) 后应恢复置顶"
    )


def test_frame_changed_updates_child_label_pixmap(qapp, make_window):
    """契约补充：animator.frame_changed 应直连窗口内 QLabel.setPixmap。"""
    window, animator = make_window()
    animator.play("idle", loop=True, fps=10.0)
    QTest.qWait(400)

    labels = window.findChildren(QLabel)
    assert labels, "契约要求 pixmap 由 frame_changed 直连 QLabel.setPixmap，窗口内应有 QLabel"
    assert any(
        label.pixmap() is not None and not label.pixmap().isNull()
        and label.pixmap().width() == 150
        for label in labels
    ), "悬停 QLabel 应已收到 150px 宽的精灵帧 pixmap"


def test_set_flipped_forwards_to_animator_keeping_animation(qapp, make_window, monkeypatch):
    """契约补充：set_flipped 应转发 animator.play 并保持当前动画名。"""
    window, animator = make_window()
    animator.play("walk", loop=True, fps=10.0)

    original_play = animator.play
    calls = []

    def spy_play(name, loop=True, fps=None, flipped=False):
        calls.append((name, bool(loop), fps, bool(flipped)))
        original_play(name, loop=loop, fps=fps, flipped=flipped)

    monkeypatch.setattr(animator, "play", spy_play)

    window.set_flipped(True)
    assert calls, "set_flipped(True) 应触发 animator.play"
    assert calls[-1][0] == "walk" and calls[-1][3] is True, (
        f"set_flipped(True) 应回放当前动画 walk 且 flipped=True，实际 {calls[-1]}"
    )

    window.set_flipped(False)
    assert calls[-1][0] == "walk" and calls[-1][3] is False, (
        f"set_flipped(False) 应恢复朝向且保持动画 walk，实际 {calls[-1]}"
    )


# ---------------------------------------------------------------------------
# T14 冒烟
# ---------------------------------------------------------------------------
def test_t14_main_module_importable():
    """T14 冒烟：main 模块可导入且不崩溃（只导入，不执行入口/事件循环）。"""
    import main  # noqa: F401  入口逻辑必须在 __main__ 守卫内，导入本身不得有副作用

    assert main is not None, "main 模块应可导入"
