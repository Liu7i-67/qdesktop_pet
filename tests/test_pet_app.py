"""PetApp（托盘与菜单）测试 —— T13 + 关闭窗口退出的回归验证。

覆盖测试功能点：
- T13 托盘与菜单：
    * show_tray() 后 tray.isVisible() 为 True（offscreen 下 isVisible 反映 show 调用）、
      tooltip「咕咕嘎嘎」、气泡 showMessage「咕咕嘎嘎来啦！」（spy 捕获）；
    * context_menu() 恰含 3 个 action：「暂停走动」「置顶显示」「退出」，
      前两个 checkable、置顶显示默认勾选、暂停走动默认不勾选；
    * 触发暂停走动 → controller.set_walking_paused 收到 True/False；
    * 触发置顶显示 → window.apply_always_on_top 收到对应值；
    * 每个动作触发前 controller.wake() 被先调用（共享调用日志断言顺序）；
    * 触发退出 → QApplication.aboutToQuit 发射。
- P1-1 回归：PetApp.__init__ 把 window.closed 连接到 QApplication.quit
  （在真实事件循环中触发 closed 后观测 aboutToQuit）。

QApplication 策略（任务约定的选择）：复用 conftest 的 session 级 ``qapp`` 夹具，
不新建独立 QApplication。aboutToQuit 的观测采用「qapp + 短暂真实事件循环」：
QTimer 触发目标动作 → ``qapp.exec()`` 进入循环 → 动作调用 QApplication.quit()
→ 循环以 rc=0 退出，期间 aboutToQuit 被 spy 捕获；另设看门狗定时器（用完即
stop，不残留）防止实现缺失时挂死。探针实测同一 QApplication 可多次顺序 exec
且每次 aboutToQuit 恰发射一次，对后续用例无污染。

假窗口 / 假控制器在本文件内定义（不改 conftest）；PetApp 使用真实实现
``from app.pet_app import PetApp``。
"""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from app.pet_app import PetApp

TRAY_TOOLTIP_EXPECTED = "咕咕嘎嘎"
BALLOON_TITLE_EXPECTED = "咕咕嘎嘎"
BALLOON_MESSAGE_EXPECTED = "咕咕嘎嘎来啦！"
TEXT_PAUSE = "暂停走动"
TEXT_TOPMOST = "置顶显示"
TEXT_QUIT = "退出"


# ---------------------------------------------------------------------------
# 假对象（仅实现 PetApp 需要的鸭子类型接口；共享同一份调用日志以断言先后顺序）
# ---------------------------------------------------------------------------
class FakeController(QObject):
    """最小假控制器：记录 wake / set_walking_paused 调用。"""

    def __init__(self, calls):
        super().__init__()
        self.calls = calls        # 与 FakeWindow 共享的调用日志 [(名称, 参数...)]
        self.wake_count = 0
        self.paused = None

    def wake(self):
        self.wake_count += 1
        self.calls.append(("wake",))

    def set_walking_paused(self, paused):
        self.paused = bool(paused)
        self.calls.append(("set_walking_paused", bool(paused)))

    def start(self):
        self.calls.append(("start",))


class FakeWindow(QObject):
    """最小假窗口：带 closed 信号与 apply_always_on_top。"""

    closed = Signal()

    def __init__(self, calls):
        super().__init__()
        self.calls = calls
        self.always_on_top = None

    def apply_always_on_top(self, on):
        self.always_on_top = bool(on)
        self.calls.append(("apply_always_on_top", bool(on)))

    def emit_closed(self):
        self.closed.emit()


@pytest.fixture()
def make_pet_app(qapp, request):
    """构建真实 PetApp + 注入假窗口/假控制器，返回聚合对象并在结束时清理。"""
    made = []

    def _make():
        calls = []
        window = FakeWindow(calls)
        controller = FakeController(calls)
        pet_app = PetApp(window, controller)
        made.append((pet_app, window, controller))
        return SimpleNamespace(pet_app=pet_app, window=window, controller=controller, calls=calls)

    def _cleanup():
        for pet_app, window, controller in made:
            pet_app.tray.hide()
            pet_app.deleteLater()
            window.deleteLater()
            controller.deleteLater()

    request.addfinalizer(_cleanup)
    return _make


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def _find_action(menu, text):
    for action in menu.actions():
        if action.text() == text:
            return action
    raise AssertionError(f"菜单中找不到动作「{text}」，实际 {[a.text() for a in menu.actions()]}")


def _run_until_quit(qapp, trigger, timeout_ms=4000):
    """进入短暂真实事件循环，在循环内触发 trigger，观测 aboutToQuit。

    返回 (aboutToQuit 发射次数, exec 返回码)。
    rc=0 表示目标动作调用了 QApplication.quit()；
    rc=2 表示超时看门狗兜底退出（目标动作未生效）。两个定时器均在
    finally 中 stop，不会向后续用例残留事件。
    """
    spy = _QuitSpy(qapp)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: qapp.exit(2))
    trigger_timer = QTimer()
    trigger_timer.setSingleShot(True)
    trigger_timer.timeout.connect(trigger)
    try:
        trigger_timer.start(30)
        watchdog.start(timeout_ms)
        rc = qapp.exec()
    finally:
        trigger_timer.stop()
        watchdog.stop()
        spy.disconnect()
    return spy.count, rc


class _QuitSpy:
    """aboutToQuit 计数器（可精确断连，不污染 session 级 QApplication）。"""

    def __init__(self, qapp):
        self.count = 0
        self._qapp = qapp
        qapp.aboutToQuit.connect(self._record)

    def _record(self):
        self.count += 1

    def disconnect(self):
        try:
            self._qapp.aboutToQuit.disconnect(self._record)
        except (RuntimeError, TypeError):
            pass


# ---------------------------------------------------------------------------
# T13：托盘
# ---------------------------------------------------------------------------
def test_t13_tray_visible_tooltip_and_balloon(qapp, make_pet_app, monkeypatch):
    """T13：show_tray() 后托盘对象可见；tooltip=「咕咕嘎嘎」；气泡=「咕咕嘎嘎来啦！」。"""
    bundle = make_pet_app()
    pet_app = bundle.pet_app

    # 气泡文本经类级 showMessage spy 捕获（不弹真气泡，offscreen 也无托盘可弹）
    captured = []
    original_show_message = QSystemTrayIcon.showMessage

    def spy_show_message(self, title, message, *args, **kwargs):
        captured.append((title, message))
        return original_show_message(self, title, message, *args, **kwargs)

    monkeypatch.setattr(QSystemTrayIcon, "showMessage", spy_show_message)

    pet_app.show_tray()

    assert pet_app.tray.isVisible(), (
        "show_tray() 后托盘对象应可见（offscreen 下 isVisible 反映 show 调用，T13）"
    )
    assert pet_app.tray.toolTip() == TRAY_TOOLTIP_EXPECTED, (
        f"托盘 tooltip 应为「{TRAY_TOOLTIP_EXPECTED}」，实际 {pet_app.tray.toolTip()!r}（T13）"
    )
    assert captured == [(BALLOON_TITLE_EXPECTED, BALLOON_MESSAGE_EXPECTED)], (
        f"show_tray() 应弹出气泡「{BALLOON_TITLE_EXPECTED}，{BALLOON_MESSAGE_EXPECTED}」，"
        f"实际 {captured}（需求 F10）"
    )


# ---------------------------------------------------------------------------
# T13：菜单结构
# ---------------------------------------------------------------------------
def test_t13_context_menu_structure(qapp, make_pet_app):
    """T13：菜单恰含 3 个动作，文本/可勾选性/默认勾选态符合契约。"""
    menu = make_pet_app().pet_app.context_menu()

    actions = menu.actions()
    texts = [a.text() for a in actions]
    assert len(actions) == 3, f"菜单应恰含 3 个动作，实际 {len(actions)} 个：{texts}"
    assert texts == [TEXT_PAUSE, TEXT_TOPMOST, TEXT_QUIT], (
        f"菜单动作文本应为 {[TEXT_PAUSE, TEXT_TOPMOST, TEXT_QUIT]}，实际 {texts}（T13）"
    )

    pause, topmost, quit_action = actions
    assert pause.isCheckable(), "「暂停走动」应为可勾选（需求 F9）"
    assert topmost.isCheckable(), "「置顶显示」应为可勾选（需求 F9）"
    assert not quit_action.isCheckable(), "「退出」不应为可勾选"
    assert topmost.isChecked(), "「置顶显示」默认应勾选（默认置顶）"
    assert not pause.isChecked(), "「暂停走动」默认不应勾选"


# ---------------------------------------------------------------------------
# T13：暂停走动联动
# ---------------------------------------------------------------------------
def test_t13_pause_action_wires_controller_wake_first(qapp, make_pet_app):
    """T13：触发暂停走动 → wake 先行、set_walking_paused 收到 True/False。"""
    bundle = make_pet_app()
    pause = _find_action(bundle.pet_app.context_menu(), TEXT_PAUSE)

    pause.trigger()   # 默认未勾选 → 触发后勾选 → True
    pause.trigger()   # 再次触发 → 取消勾选 → False

    assert bundle.calls == [
        ("wake",), ("set_walking_paused", True),
        ("wake",), ("set_walking_paused", False),
    ], (
        f"两次触发应各先调 wake() 再调 set_walking_paused(True/False)，"
        f"实际调用日志 {bundle.calls}"
    )
    assert bundle.controller.paused is False, "最终应回到未暂停状态"


# ---------------------------------------------------------------------------
# T13：置顶显示联动
# ---------------------------------------------------------------------------
def test_t13_topmost_action_wires_window_wake_first(qapp, make_pet_app):
    """T13：触发置顶显示 → wake 先行、apply_always_on_top 收到对应值。"""
    bundle = make_pet_app()
    topmost = _find_action(bundle.pet_app.context_menu(), TEXT_TOPMOST)

    topmost.trigger()   # 默认勾选 → 触发后取消 → False
    topmost.trigger()   # 再次触发 → 重新勾选 → True

    assert bundle.calls == [
        ("wake",), ("apply_always_on_top", False),
        ("wake",), ("apply_always_on_top", True),
    ], (
        f"两次触发应各先调 wake() 再调 apply_always_on_top(False/True)，"
        f"实际调用日志 {bundle.calls}"
    )
    assert bundle.window.always_on_top is True, "最终应回到置顶开启"


# ---------------------------------------------------------------------------
# T13：退出动作 → aboutToQuit
# ---------------------------------------------------------------------------
def test_t13_quit_action_emits_about_to_quit_wake_first(qapp, make_pet_app):
    """T13：真实事件循环中触发退出 → wake 先行、QApplication.quit 使 aboutToQuit 发射。"""
    bundle = make_pet_app()
    quit_action = _find_action(bundle.pet_app.context_menu(), TEXT_QUIT)

    count, rc = _run_until_quit(qapp, quit_action.trigger)

    assert rc == 0, (
        f"退出动作应调用 QApplication.quit() 使事件循环以 0 退出，实际 rc={rc}"
        "（rc=2 说明超时看门狗兜底，退出路径未生效）"
    )
    assert count >= 1, f"触发退出后应观测到 QApplication.aboutToQuit 发射，实际 {count} 次"
    assert bundle.calls and bundle.calls[0] == ("wake",), (
        f"退出前应先调用 controller.wake()，实际调用日志 {bundle.calls}"
    )


# ---------------------------------------------------------------------------
# P1-1 回归：closed → quit
# ---------------------------------------------------------------------------
def test_regression_window_closed_signal_quits_app(qapp, make_pet_app):
    """P1-1 回归：PetApp.__init__ 应把 window.closed 连接到 QApplication.quit。

    在真实事件循环中发射 closed，若连接缺失则循环不会退出（看门狗 rc=2 兜底）。
    """
    bundle = make_pet_app()

    count, rc = _run_until_quit(qapp, bundle.window.emit_closed)

    assert rc == 0, (
        f"关闭唯一窗口（closed 信号）应调用 QApplication.quit() 使事件循环退出，"
        f"实际 rc={rc}——PetApp.__init__ 未把 closed 连接到 QApplication.quit（P1-1）"
    )
    assert count >= 1, (
        f"触发 closed 后应观测到 QApplication.aboutToQuit 发射，实际 {count} 次（P1-1 回归）"
    )
