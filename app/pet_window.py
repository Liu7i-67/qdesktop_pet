"""PetWindow —— 透明置顶宠物窗口（WP2）。

严格实现需求文档第 4 节契约：

- 150×150 固定窗口；flags = FramelessWindowHint | Tool | WindowStaysOnTopHint；
  启用 WA_TranslucentBackground（逐像素透明）；
- 内部 QLabel（几何填满窗口、ScaledContents 关闭）承接 pixmap，
  ``__init__`` 中将 ``animator.frame_changed`` 直连 ``QLabel.setPixmap``；
- 鼠标交互：按下记录全局点与窗口内锚点；光标全局位移 >6px 判为拖拽
  （首次发 drag_started，此后每次发 drag_moved(新窗口左上角=光标全局-锚点)）；
  松手时发生过拖拽则发 drag_released(当前左上角) 并清状态，否则发 clicked；
  双击发 double_clicked；进入/离开窗口发 hover_entered / hover_left；
- 右键：经 ``contextMenuEvent`` 弹出 ``setContextMenu`` 注入的共享菜单
  （与托盘同一份，见 app/pet_app.py），不参与单击/拖拽判定；
- 几何工具：move_to(float 逻辑坐标，钳制在 screen_rect() 内)、pos_f()、
  floor_y()、screen_rect()（screenAt 失败回退主屏）；
- apply_always_on_top(on)：setWindowFlag 后原位 re-show；
- set_flipped(flipped)：记录朝向并以当前动画名/loop/fps 重发 play；
- 增量扩展（P1 修复）：显式开启 WA_QuitOnClose（Tool 型窗口会被 Qt 清掉
  该属性，导致关窗后进程/托盘残留），并在关闭被接受时发 closed 信号，
  供组装层联动退出托盘（需求 F10：关闭唯一窗口即退出）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QLineF, QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QCloseEvent, QContextMenuEvent, QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QWidget

if TYPE_CHECKING:  # 仅为类型标注；运行期鸭子类型，避免组件间循环依赖
    from app.sprite_animator import SpriteAnimator

__all__ = ["PetWindow"]

WINDOW_SIZE = 150        # 契约：窗口固定 150×150 逻辑像素
DRAG_THRESHOLD_PX = 6.0  # 契约：光标全局位移 >6px 判为拖拽


class PetWindow(QWidget):
    """无边框透明置顶窗：把鼠标事件翻译为契约信号，提供屏幕几何工具。"""

    clicked = Signal()
    double_clicked = Signal()
    drag_started = Signal()
    drag_moved = Signal(QPoint)      # 窗口左上角全局坐标
    drag_released = Signal(QPoint)   # 窗口左上角全局坐标
    hover_entered = Signal()
    hover_left = Signal()
    closed = Signal()  # 增量扩展（契约外）：窗口关闭被接受时发射，供组装层退出联动

    def __init__(self, animator: "SpriteAnimator") -> None:
        super().__init__()
        self._animator = animator
        self._flipped = False
        self._context_menu: QMenu | None = None

        # 拖拽状态：None 表示当前未按住左键
        self._press_global: QPoint | None = None
        self._anchor: QPoint | None = None
        self._dragging = False
        self._drag_topleft: QPoint | None = None  # 最近一次计算的窗口左上角

        self.setObjectName("petWindow")
        self.setWindowTitle("咕咕嘎嘎")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        # P1 修复：设置 flags 之后显式开启 WA_QuitOnClose——Qt 会因 Tool 类型
        # 将其清为 False，导致 Alt+F4/close() 后窗口消失但进程与托盘残留
        # （需求 F10：关闭唯一窗口即退出）
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(WINDOW_SIZE, WINDOW_SIZE)

        # 内部 QLabel：几何填满、ScaledContents 关，只负责显示当前帧
        self._label = QLabel(self)
        self._label.setObjectName("petSpriteLabel")
        self._label.setGeometry(self.rect())
        self._label.setScaledContents(False)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 鼠标事件穿透到窗口本身，保证 press/move/release/hover 全在窗口层判定
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # 契约：pixmap 由 animator.frame_changed 直连 QLabel.setPixmap
        animator.frame_changed.connect(self._label.setPixmap)

    # ------------------------------------------------------------------
    # 契约接口
    # ------------------------------------------------------------------
    def set_flipped(self, flipped: bool) -> None:
        """记录朝向，并以当前动画名/loop/fps 重发 play（画面连续切换朝向）。"""
        self._flipped = bool(flipped)
        name = self._animator.current_animation()
        if not name:
            return  # 尚无当前动画：仅记录朝向，等下一次 play 时生效
        loop = bool(getattr(self._animator, "current_loop", True))
        fps = getattr(self._animator, "current_fps", None)
        self._animator.play(name, loop=loop, fps=fps, flipped=self._flipped)

    def move_to(self, x: float, y: float) -> None:
        """按逻辑坐标移动窗口；先钳制在 screen_rect() 内再 move(int)。"""
        cx, cy = float(x), float(y)
        rect = self.screen_rect()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            left, top = float(rect.left()), float(rect.top())
            right = float(rect.right()) + 1.0 - float(self.width())
            bottom = float(rect.bottom()) + 1.0 - float(self.height())
            if right < left:
                right = left  # 屏幕比窗口还小的退化情形：贴左上
            if bottom < top:
                bottom = top
            cx = min(max(cx, left), right)
            cy = min(max(cy, top), bottom)
        self.move(int(round(cx)), int(round(cy)))

    def pos_f(self) -> QPointF:
        """窗口左上角逻辑坐标（QPointF）。"""
        return QPointF(float(self.x()), float(self.y()))

    def floor_y(self) -> int:
        """贴底时窗口左上角 y：所在屏 availableGeometry().bottom()+1-窗口高。"""
        return int(self.screen_rect().bottom() + 1 - self.height())

    def screen_rect(self) -> QRect:
        """窗口中心所在屏的 availableGeometry()；screenAt 失败回退主屏。"""
        app = QApplication.instance()
        screen = None
        if app is not None:
            center = self.mapToGlobal(self.rect().center())
            screen = QApplication.screenAt(center)
            if screen is None:
                screen = app.primaryScreen()
        if screen is None:
            return QRect()  # 无 QApplication/屏幕（极端环境）：返回空矩形
        return QRect(screen.availableGeometry())

    def apply_always_on_top(self, on: bool) -> None:
        """开关置顶；setWindowFlag 会重建原生窗口，需原位 re-show。"""
        pos = self.pos()
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(on))
        if was_visible:
            self.show()
        if self.pos() != pos:  # 原位恢复
            self.move(pos)

    def setContextMenu(self, menu: QMenu) -> None:
        """注入窗口右键共享菜单（pet_app.bind_window_menu 会优先调用）。"""
        self._context_menu = menu

    # ------------------------------------------------------------------
    # 鼠标事件 → 契约信号
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        button = event.button()
        if button == Qt.MouseButton.RightButton:
            event.accept()  # 右键交由 contextMenuEvent 弹共享菜单，不做拖拽锚点
            return
        if button == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._anchor = event.position().toPoint()  # 窗口内锚点，防拖拽跳变
            self._dragging = False
            self._drag_topleft = None
            event.accept()
            return
        event.accept()  # 其他按键：吞掉，不产生交互行为

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_global is None or self._anchor is None:
            event.accept()  # 未按左键（悬停移动）：无行为
            return
        global_pos = event.globalPosition()
        if not self._dragging:
            displacement = QLineF(QPointF(self._press_global), global_pos).length()
            if displacement <= DRAG_THRESHOLD_PX:
                event.accept()  # 位移未过阈值：保持按下状态，等待后续移动/松手
                return
            self._dragging = True
            self.drag_started.emit()  # 进入拖拽：只发一次
        self._drag_topleft = global_pos.toPoint() - self._anchor
        self.drag_moved.emit(QPoint(self._drag_topleft))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._press_global is None:
            event.accept()  # 右键/无按下状态的释放：无行为
            return
        if self._dragging:
            topleft = self._drag_topleft if self._drag_topleft is not None else self.pos()
            self.drag_released.emit(QPoint(topleft))
        else:
            self.clicked.emit()
        self._clear_press_state()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._clear_press_state()  # 双击自带按下/释放序列，避免残留拖拽状态
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        event.accept()

    def enterEvent(self, event: QEnterEvent) -> None:
        self.hover_entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self.hover_left.emit()
        super().leaveEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """右键（平台可能在按下或释放时合成该事件）：弹出共享菜单。"""
        if self._context_menu is not None:
            self._context_menu.popup(event.globalPos())
            event.accept()
        else:
            super().contextMenuEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """窗口关闭：接受时发 closed，供组装层联动退出（F10 关窗即退出）。

        注意：QWidget.closeEvent 默认实现会 accept()；组装层如需拒绝关闭
        （例如弹确认框），应在其覆写中先 ``event.ignore()`` 且不再调用
        ``super().closeEvent(event)``，closed 即不会发射。
        """
        super().closeEvent(event)
        if event.isAccepted():  # PySide6 的 QEvent 判定方法（C++ QEvent::isAccepted）
            self.closed.emit()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _clear_press_state(self) -> None:
        self._press_global = None
        self._anchor = None
        self._dragging = False
        self._drag_topleft = None

    def resizeEvent(self, event) -> None:  # noqa: ANN001 (QWidget 事件签名)
        super().resizeEvent(event)
        self._label.setGeometry(self.rect())  # QLabel 几何始终填满窗口
