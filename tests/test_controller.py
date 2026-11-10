"""PetController 状态机测试（真实 app.pet_controller.PetController + 注入 conftest 假对象）。

覆盖测试功能点：
- 起步贴底（T4 控制器层）：start() 后窗口贴 floor_y 并进入 WALK；
- T7  单击反应：clicked → quack（含 y 抛物线跳跃），结束后回 walk/idle；
- T8  双击反应：double_clicked → happy，结束后回 walk/idle；
- T9  松手回底：drag_released → FALL 落到所在屏底部，落地缓冲后继续踱步；
- T10 暂停走动：set_walking_paused(True) 后位置不动，且交互反应仍可用；
- T11 睡眠与唤醒：模拟 60s 闲置进入 sleep，hover/click/wake 退出。

定时器推进统一用 QTest.qWait / wait_until（事件循环等待，不 sleep 轮询）。
60s 闲置通过 monkeypatch 闲置阈值常量/属性，或直接调用控制器内部“进入睡眠”
入口来缩短（入口名按候选清单自适应探测，见 _trigger_sleep）。
"""

import sys

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtTest import QTest

import app.pet_controller as pet_controller_module
from app.pet_controller import PetController
from conftest import wait_until

POINT_TOL = 1.5


# ---------------------------------------------------------------------------
# 假对象/真实控制器装配
# ---------------------------------------------------------------------------
@pytest.fixture()
def controller(qapp, fake_window, fake_animator, request):
    """真实 PetController + 注入假窗口/假动画器，测试结束后清理。"""
    obj = PetController(fake_window, fake_animator)

    def _cleanup():
        stop = getattr(obj, "stop", None)
        if callable(stop):
            stop()
        obj.deleteLater()

    request.addfinalizer(_cleanup)
    return obj


def _start_and_wait_walking(controller, fake_window):
    """start() 并等待贴底 + 开始走动（move_to 被调用多次）。"""
    controller.start()
    snapped = wait_until(
        lambda: abs(fake_window.window_bottom()
                    - (fake_window.screen_rect().bottom() + 1)) <= 1,
        timeout_ms=2500,
    )
    assert snapped, (
        f"start() 后窗口底应贴 floor（{fake_window.screen_rect().bottom() + 1}），"
        f"实际 {fake_window.window_bottom()}（T4 控制器层）"
    )
    walking = wait_until(lambda: len(fake_window.move_to_calls) >= 3, timeout_ms=3000)
    assert walking, "start() 进入 WALK 后应持续调用 window.move_to 踱步"


# ---------------------------------------------------------------------------
# 起步贴底（T4 控制器层）
# ---------------------------------------------------------------------------
def test_start_places_window_at_floor_and_walks(qapp, fake_window, fake_animator, controller):
    """start() 后窗口应贴所在屏底部，并开始随机踱步（位置持续变化）。"""
    _start_and_wait_walking(controller, fake_window)

    x0 = fake_window.pos_f().x()
    moved = wait_until(lambda: fake_window.pos_f().x() != x0, timeout_ms=3000)
    assert moved, "WALK 状态下窗口 x 应随踱步变化"

    floor_bottom = fake_window.screen_rect().bottom() + 1
    assert abs(fake_window.window_bottom() - floor_bottom) <= 1, (
        f"踱步过程中窗口底应保持贴 floor（{floor_bottom}），实际 {fake_window.window_bottom()}"
    )


# ---------------------------------------------------------------------------
# T7 单击反应
# ---------------------------------------------------------------------------
def test_t7_click_triggers_quack_hop_then_returns(qapp, fake_window, fake_animator, controller):
    """T7：clicked 后当前动画=quack；期间窗口做 y 抛物线跳跃；结束后回 walk/idle。"""
    _start_and_wait_walking(controller, fake_window)
    y0 = fake_window.pos_f().y()

    fake_window.emit_click()
    reacted = wait_until(lambda: fake_animator.current_animation() == "quack", timeout_ms=900)
    assert reacted, (
        f"单击后当前动画应为 quack（T7），实际 {fake_animator.current_animation()!r}"
    )

    # 契约：跳由控制器做 y 抛物线 0→-60→0 —— 窗口应显著上移再回原位
    min_y = y0
    for _ in range(16):
        QTest.qWait(40)
        min_y = min(min_y, fake_window.pos_f().y())
    assert min_y <= y0 - 25, (
        f"单击应触发 y 抛物线跳跃：窗口应上移≥25px（峰值为 -60px），"
        f"实际 y0={y0}，min_y={min_y}"
    )

    returned = wait_until(
        lambda: fake_animator.current_animation() in ("walk", "walk_side", "idle"), timeout_ms=3500)
    assert returned, (
        f"quack 播完后应回到 walk/idle（T7），实际仍为 "
        f"{fake_animator.current_animation()!r}"
    )
    assert abs(fake_window.pos_f().y() - y0) <= POINT_TOL, (
        f"跳跃结束后窗口应回到原高度 y0={y0}，实际 {fake_window.pos_f().y()}"
    )


# ---------------------------------------------------------------------------
# T8 双击反应
# ---------------------------------------------------------------------------
def test_t8_double_click_triggers_happy_then_returns(qapp, fake_window, fake_animator, controller):
    """T8：double_clicked 后当前动画=happy，结束后回 walk/idle。"""
    _start_and_wait_walking(controller, fake_window)

    fake_window.emit_double_click()
    reacted = wait_until(lambda: fake_animator.current_animation() == "happy", timeout_ms=900)
    assert reacted, (
        f"双击后当前动画应为 happy（T8），实际 {fake_animator.current_animation()!r}"
    )

    returned = wait_until(
        lambda: fake_animator.current_animation() in ("walk", "walk_side", "idle"), timeout_ms=3500)
    assert returned, (
        f"happy 播完后应回到 walk/idle，实际仍为 {fake_animator.current_animation()!r}"
    )


# ---------------------------------------------------------------------------
# T9 松手回底
# ---------------------------------------------------------------------------
def test_t9_release_falls_back_to_floor(qapp, fake_window, fake_animator, controller):
    """T9：拖到屏幕中部松手 → FALL 下落，窗口底回到 floor_y，落地缓冲后继续踱步。"""
    _start_and_wait_walking(controller, fake_window)

    # 进入拖拽并移到屏幕中部（虚拟屏 1920×1040，floor_y=890）
    fake_window.emit_drag_started()
    fake_window.emit_drag_moved(600, 400)
    followed = wait_until(
        lambda: abs(fake_window.pos_f().x() - 600) <= POINT_TOL
        and abs(fake_window.pos_f().y() - 400) <= POINT_TOL,
        timeout_ms=1000,
    )
    assert followed, (
        f"DRAG 状态下窗口应跟随 drag_moved 移到 (600,400)，"
        f"实际 {fake_window.pos_f().x()},{fake_window.pos_f().y()}"
    )

    fake_window.emit_drag_released(600, 400)
    landed = wait_until(
        lambda: abs(fake_window.window_bottom()
                    - (fake_window.screen_rect().bottom() + 1)) <= 1,
        timeout_ms=5000,
    )
    assert landed, (
        f"松手后应下落回所在屏底部（窗口底={fake_window.screen_rect().bottom() + 1}），"
        f"实际窗口底 {fake_window.window_bottom()}（T9）"
    )

    resumed = wait_until(
        lambda: fake_animator.current_animation() in ("walk", "walk_side", "idle"), timeout_ms=3500)
    assert resumed, (
        f"落地缓冲后应继续踱步（walk/idle），实际 {fake_animator.current_animation()!r}（T9）"
    )


# ---------------------------------------------------------------------------
# T10 暂停走动
# ---------------------------------------------------------------------------
def test_t10_pause_freezes_position(qapp, fake_window, fake_animator, controller):
    """T10：set_walking_paused(True) 后 2s 内位置不变，且切到 IDLE。"""
    _start_and_wait_walking(controller, fake_window)

    controller.set_walking_paused(True)
    idled = wait_until(lambda: fake_animator.current_animation() == "idle", timeout_ms=1200)
    assert idled, (
        f"暂停走动应保持 IDLE（播放 idle），实际 {fake_animator.current_animation()!r}（T10）"
    )

    pos0 = QPointF(fake_window.pos_f())
    QTest.qWait(2000)
    pos1 = fake_window.pos_f()
    assert pos1 == pos0, (
        f"暂停走动后 2s 内位置应不变（T10）：暂停前 {pos0.x()},{pos0.y()} → "
        f"暂停后 {pos1.x()},{pos1.y()}"
    )


def test_t10_paused_interaction_still_works(qapp, fake_window, fake_animator, controller):
    """契约补充：暂停走动时交互反应仍可用（点击仍触发 quack，结束后回 IDLE）。"""
    _start_and_wait_walking(controller, fake_window)
    controller.set_walking_paused(True)
    wait_until(lambda: fake_animator.current_animation() == "idle", timeout_ms=1200)

    fake_window.emit_click()
    reacted = wait_until(lambda: fake_animator.current_animation() == "quack", timeout_ms=900)
    assert reacted, (
        f"暂停走动时单击仍应触发 quack 反应，实际 {fake_animator.current_animation()!r}"
    )

    back = wait_until(lambda: fake_animator.current_animation() == "idle", timeout_ms=3500)
    assert back, (
        f"暂停状态下 quack 播完后应回 IDLE，实际 {fake_animator.current_animation()!r}"
    )


# ---------------------------------------------------------------------------
# T11 睡眠与唤醒
# ---------------------------------------------------------------------------
# 闲置阈值候选名（模块常量 / 控制器属性），按需求文档语义自适应探测
_IDLE_ATTR_CANDIDATES = ("idle_seconds", "idle_secs", "idle_time", "_idle_seconds")
_SLEEP_CONST_CANDIDATES = (
    "SLEEP_AFTER_SECONDS", "SLEEP_AFTER_IDLE_SECONDS", "SLEEP_IDLE_SECONDS",
    "SLEEP_THRESHOLD_SECONDS", "IDLE_SLEEP_SECONDS", "IDLE_TO_SLEEP_SECONDS",
    "IDLE_SECONDS_BEFORE_SLEEP",
)
# 内部“进入睡眠”入口与行为 tick 候选名
_SLEEP_METHOD_CANDIDATES = (
    "_enter_sleep", "_enter_sleep_state", "_go_to_sleep", "_start_sleep",
    "_maybe_sleep", "_check_sleep", "_try_sleep",
)
_TICK_METHOD_CANDIDATES = (
    "_on_tick", "_tick", "_on_timer", "_on_timeout", "_update", "_step", "_behavior_tick",
)


def _is_asleep(fake_animator):
    return fake_animator.current_animation() == "sleep"


def _try_force_idle_state(controller):
    """若控制器暴露可写的 state 属性，尝试置为 IDLE（便于闲置计时进入睡眠）。"""
    for attr in ("state", "_state"):
        current = getattr(controller, attr, None)
        if isinstance(current, str):
            try:
                setattr(controller, attr, "IDLE")
                return True
            except Exception:
                pass
        elif current is not None:
            member = getattr(type(current), "IDLE", None)
            if member is not None:
                try:
                    setattr(controller, attr, member)
                    return True
                except Exception:
                    pass
    return False


def _try_call_tick(controller):
    """尝试手动调用控制器的行为 tick（若实现暴露）。"""
    for name in _TICK_METHOD_CANDIDATES:
        method = getattr(controller, name, None)
        if callable(method):
            try:
                method()
                return name
            except Exception:
                continue
    return None


def _trigger_sleep(controller, fake_animator, monkeypatch):
    """自适应触发“进入睡眠”，返回所用策略名；全部失败则 pytest.fail 并给出对齐建议。

    优先级（对应任务约定）：
    1) monkeypatch 控制器暴露的闲置秒数属性（如 idle_seconds）→ 拉满闲置时长；
    2) monkeypatch 模块级闲置阈值常量（如 SLEEP_AFTER_SECONDS）→ 缩短为 0.2s；
    3) 直接调用控制器内部“进入睡眠”入口（如 _enter_sleep）。
    """
    tried = []
    module = sys.modules.get("app.pet_controller", pet_controller_module)

    # 策略 1：实例闲置秒数属性
    for attr in _IDLE_ATTR_CANDIDATES:
        if hasattr(controller, attr):
            tried.append(f"属性 {attr}")
            try:
                monkeypatch.setattr(controller, attr, 3600.0, raising=False)
            except Exception:
                continue
            _try_force_idle_state(controller)
            _try_call_tick(controller)
            if wait_until(lambda: _is_asleep(fake_animator), timeout_ms=1500):
                return f"实例属性 {attr}"

    # 策略 2：模块级闲置阈值常量
    for const in _SLEEP_CONST_CANDIDATES:
        if hasattr(module, const):
            tried.append(f"常量 {const}")
            try:
                monkeypatch.setattr(module, const, 0.2)
            except Exception:
                continue
            _try_force_idle_state(controller)
            _try_call_tick(controller)
            if wait_until(lambda: _is_asleep(fake_animator), timeout_ms=2500):
                return f"模块常量 {const}"
            for _ in range(5):  # 再手动推几拍 tick
                _try_call_tick(controller)
                QTest.qWait(60)
                if _is_asleep(fake_animator):
                    return f"模块常量 {const}+手动tick"

    # 策略 3：直接调用内部进入睡眠入口
    for name in _SLEEP_METHOD_CANDIDATES:
        method = getattr(controller, name, None)
        if callable(method):
            tried.append(f"方法 {name}()")
            try:
                method()
            except Exception:
                continue
            if wait_until(lambda: _is_asleep(fake_animator), timeout_ms=1200):
                return f"内部入口 {name}()"

    pytest.fail(
        "T11 无法触发进入睡眠：未找到约定的闲置阈值常量/属性或内部进入睡眠入口。"
        f"已尝试：{', '.join(tried) if tried else '无'}。"
        "请与 WP3 对齐契约：建议模块常量 SLEEP_AFTER_SECONDS（单位秒）+ 内部入口 "
        "_enter_sleep()，或控制器暴露 idle_seconds 属性。"
    )


def test_t11_sleep_on_idle_and_wake_on_interaction(qapp, fake_window, fake_animator,
                                                   controller, monkeypatch):
    """T11：闲置达到阈值进入 sleep；hover / click / wake() 均可唤醒。"""
    _start_and_wait_walking(controller, fake_window)

    # —— 进入睡眠 ——
    strategy = _trigger_sleep(controller, fake_animator, monkeypatch)
    assert _is_asleep(fake_animator), (
        f"触发睡眠后当前动画应为 sleep（策略：{strategy}），"
        f"实际 {fake_animator.current_animation()!r}（T11）"
    )

    # —— hover 唤醒 ——
    fake_window.emit_hover_entered()
    woke = wait_until(lambda: not _is_asleep(fake_animator), timeout_ms=1200)
    assert woke, (
        f"hover 事件应唤醒睡眠并触发反应（T11），实际仍为 "
        f"{fake_animator.current_animation()!r}"
    )
    wait_until(lambda: fake_animator.current_animation() in ("walk", "walk_side", "idle"),
               timeout_ms=3500)

    # —— click 唤醒（再次入睡后）——
    _trigger_sleep(controller, fake_animator, monkeypatch)
    assert _is_asleep(fake_animator), "第二次触发后应再次处于睡眠"
    fake_window.emit_click()
    woke = wait_until(lambda: not _is_asleep(fake_animator), timeout_ms=1200)
    assert woke, (
        f"click 事件应唤醒睡眠（T11），实际仍为 {fake_animator.current_animation()!r}"
    )
    wait_until(lambda: fake_animator.current_animation() in ("walk", "walk_side", "idle"),
               timeout_ms=3500)

    # —— 公共 wake() 唤醒（第三次入睡后）——
    _trigger_sleep(controller, fake_animator, monkeypatch)
    assert _is_asleep(fake_animator), "第三次触发后应处于睡眠"
    controller.wake()
    woke = wait_until(lambda: not _is_asleep(fake_animator), timeout_ms=1200)
    assert woke, (
        f"控制器公共接口 wake() 应退出睡眠（契约），实际仍为 "
        f"{fake_animator.current_animation()!r}"
    )


# ---------------------------------------------------------------------------
# v2 形象还原改造：行走使用左/右侧视图（walk_side 帧朝右 + 运行时镜像出左视图）
# ---------------------------------------------------------------------------
def _last_walk_side_call(fake_animator):
    """返回最近一次 walk_side 播放记录 (name, loop, fps, flipped)，无则 None。"""
    for call in reversed(fake_animator.play_calls):
        if call[0] == "walk_side":
            return call
    return None


def test_v2_walk_uses_side_view_and_flips_with_direction(qapp, fake_window,
                                                         fake_animator, controller):
    """行走应播放侧视图 walk_side：向右行进用右视图，向左行进镜像为左视图。"""
    _start_and_wait_walking(controller, fake_window)

    sided = wait_until(lambda: fake_animator.play_count("walk_side") >= 1, timeout_ms=2000)
    assert sided, (
        f"行走应优先播放侧视图 walk_side，最近播放记录 {fake_animator.play_calls[-3:]}"
    )

    # 白盒定向验证：分别朝右/朝左各推一拍，walk_side 的 flipped 应跟随行进方向
    controller._x = 500.0
    controller._walk_target_x = 1200.0            # 目标在右侧 → 右视图（不镜像）
    controller._tick_walk(0.016)
    call = _last_walk_side_call(fake_animator)
    assert call is not None and call[3] is False, (
        f"向右行进应以右视图播放 walk_side（flipped=False），实际 {call}"
    )

    controller._walk_target_x = 200.0             # 目标在左侧 → 镜像为左视图
    controller._tick_walk(0.016)
    call = _last_walk_side_call(fake_animator)
    assert call is not None and call[3] is True, (
        f"向左行进应镜像为左视图（flipped=True），实际 {call}"
    )

    # 停顿走动 → 回正面 idle（交互/停顿时角色面向镜头）
    controller.set_walking_paused(True)
    idled = wait_until(lambda: fake_animator.current_animation() == "idle", timeout_ms=1200)
    assert idled, f"停顿走动后应回正面 idle，实际 {fake_animator.current_animation()!r}"


def test_v2_walk_side_missing_frames_falls_back_to_front_walk(qapp, fake_window):
    """旧素材缺 walk_side 帧时：animator 抛 ValueError → 回退正面 walk，不崩溃且不反复重试。"""
    from conftest import FakeAnimator

    class NoSideAnimator(FakeAnimator):
        """模拟缺少 walk_side 帧的旧素材包。"""

        def play(self, name, loop=True, fps=None, flipped=False):
            if name == "walk_side":
                raise ValueError("动画 'walk_side' 没有任何帧文件")
            super().play(name, loop=loop, fps=fps, flipped=flipped)

    anim = NoSideAnimator()
    ctl = PetController(fake_window, anim)
    try:
        ctl.start()
        walked = wait_until(lambda: anim.current_animation() == "walk", timeout_ms=1500)
        assert walked, f"缺侧视帧时应回退正面 walk，实际 {anim.current_animation()!r}"
        QTest.qWait(500)
        assert anim.current_animation() in ("walk", "idle"), (
            f"回退后应持续可用（walk/idle），实际 {anim.current_animation()!r}"
        )
        assert all(call[0] != "walk_side" for call in anim.play_calls[1:]), (
            "首次探测失败后不应反复尝试 walk_side（应记住回退）"
        )
    finally:
        stop = getattr(ctl, "stop", None)
        if callable(stop):
            stop()
        ctl.deleteLater()
        anim.stop()
        anim.deleteLater()
