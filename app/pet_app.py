"""PetApp —— 托盘图标与全局菜单的组装层（WP4）。

PetApp 是纯组装层：持有 PetWindow / PetController 的引用（鸭子类型，
本模块不 import 控制器/窗口模块），职责：

- 创建系统托盘图标（tooltip「咕咕嘎嘎」，显示气泡「咕咕嘎嘎来啦！」）；
- 构建窗口右键与托盘共用的同一份 QMenu：
    1. 暂停走动（checkable）→ controller.set_walking_paused(checked)
    2. 置顶显示（checkable，默认开）→ pet_window.apply_always_on_top(checked)
    3. 退出 → QApplication.quit()
- 任何菜单交互 / 托盘激活都先 controller.wake()，把睡觉的鸭子点醒；
- 应用退出（aboutToQuit）时隐藏托盘完成清理。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app.resources import asset_path

TRAY_TOOLTIP = "咕咕嘎嘎"
TRAY_BALLOON_TITLE = "咕咕嘎嘎"
TRAY_BALLOON_MESSAGE = "咕咕嘎嘎来啦！"

MENU_TEXT_PAUSE = "暂停走动"
MENU_TEXT_TOPMOST = "置顶显示"
MENU_TEXT_QUIT = "退出"


class PetApp(QObject):
    """组装 PetWindow + PetController，提供托盘常驻与全局右键菜单。"""

    def __init__(
        self,
        pet_window: Any,
        controller: Any,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._window = pet_window
        self._controller = controller

        # ---- 共享菜单：窗口右键与托盘同一份 ----
        self._menu = QMenu()
        self.pause_action = QAction(MENU_TEXT_PAUSE, self._menu)
        self.pause_action.setCheckable(True)
        self.pause_action.setObjectName("action_pause_walk")
        self.pause_action.triggered.connect(self._on_pause_triggered)

        self.topmost_action = QAction(MENU_TEXT_TOPMOST, self._menu)
        self.topmost_action.setCheckable(True)
        self.topmost_action.setChecked(True)  # 默认置顶
        self.topmost_action.setObjectName("action_topmost")
        self.topmost_action.triggered.connect(self._on_topmost_triggered)

        self.quit_action = QAction(MENU_TEXT_QUIT, self._menu)
        self.quit_action.setObjectName("action_quit")
        self.quit_action.triggered.connect(self._on_quit_triggered)

        for act in (self.pause_action, self.topmost_action, self.quit_action):
            self._menu.addAction(act)

        # ---- 系统托盘 ----
        self._tray = QSystemTrayIcon(QIcon(asset_path("tray.png")))
        self._tray.setToolTip(TRAY_TOOLTIP)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.messageClicked.connect(self._wake)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cleanup)

        # ---- 关闭唯一窗口 → 应用整体退出（WP2 增量契约，鸭子类型兼容） ----
        # 旧假对象 / 未实现该信号的窗口没有 closed 属性，跳过连接不报错。
        closed = getattr(pet_window, "closed", None)
        if closed is not None and hasattr(closed, "connect"):
            closed.connect(QApplication.quit)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    @property
    def tray(self) -> QSystemTrayIcon:
        """托盘图标对象（便于测试 / 外部检查）。"""
        return self._tray

    def context_menu(self) -> QMenu:
        """返回窗口右键与托盘共用的 QMenu。"""
        return self._menu

    def show_tray(self) -> None:
        """显示托盘图标并弹出欢迎气泡。"""
        self._tray.show()
        self._tray.showMessage(TRAY_BALLOON_TITLE, TRAY_BALLOON_MESSAGE)

    def bind_window_menu(self) -> None:
        """把共享菜单接到宠物窗口右键。

        若窗口对象本身提供 ``setContextMenu(QMenu)`` 方法（WP2 自定义），
        直接交给它；否则退回在窗口上安装事件过滤器，拦截
        ``QEvent.ContextMenu`` 弹出共享菜单（QWidget 标准途径）。
        """
        setter = getattr(self._window, "setContextMenu", None)
        if callable(setter):
            setter(self._menu)
            return
        self._window.installEventFilter(self)

    # ------------------------------------------------------------------
    # 事件过滤：窗口右键 → 弹出共享菜单
    # ------------------------------------------------------------------
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._window and event.type() == QEvent.Type.ContextMenu:
            self._wake()
            self._menu.popup(event.globalPos())
            return True
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # 菜单 / 托盘行为
    # ------------------------------------------------------------------
    def _wake(self) -> None:
        """任意交互先唤醒（睡觉的鸭子被点醒）。"""
        self._controller.wake()

    def _on_pause_triggered(self) -> None:
        self._wake()
        self._controller.set_walking_paused(self.pause_action.isChecked())

    def _on_topmost_triggered(self) -> None:
        self._wake()
        self._window.apply_always_on_top(self.topmost_action.isChecked())

    def _on_quit_triggered(self) -> None:
        self._wake()
        QApplication.quit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # 右键(Context)由 setContextMenu 自动弹菜单；其余激活仅唤醒。
        self._wake()

    def _cleanup(self) -> None:
        self._tray.hide()
        self._menu.close()
