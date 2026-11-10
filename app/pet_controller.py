"""PetController —— 「咕咕嘎嘎」行为状态机与 AI 决策（WP3）。

职责（需求文档第 4 节契约）：
- 33ms QTimer 行为主循环：float 累计位置，int 取整后调 window.move_to；
- 状态机：``WALK / IDLE / DRAG / FALL / REACT / SLEEP``（self.state 取这些字符串）；
- WALK 随机踱步：目标 x 距屏边 20px、40~90px/s、到达或 2~6s 换目标、朝向=移动方向；
  行走播右向侧视图 walk_side（左向经水平镜像），停顿/交互回正面 idle，
  侧视帧缺失时自动回退正面 walk；
- 交互反应：hover→REACT_surprised(800ms 冷却)、click→REACT_quack（y 抛物线 0→-60→0
  约 500ms 与帧动画并行）、double_click→REACT_happy；
- DRAG 跟随 drag_moved；松手 FALL（重力 2000px/s²）落到所在屏底部，
  jump 末帧压扁缓冲 200ms 后回 WALK；
- IDLE 累计闲置 self.idle_seconds 达模块常量 SLEEP_AFTER_SECONDS 进入 SLEEP，
  任何窗口交互或 wake() 唤醒。

鸭子类型依赖注入：本模块不 import pet_window / sprite_animator / resources，
window / animator 仅按契约使用信号与方法（clicked/drag_*/hover_entered、
move_to/pos 相关几何、play/current 动画接口）。
"""
from __future__ import annotations

import random
import time

from PySide6.QtCore import QObject, QTimer

# ---------------------------------------------------------------------------
# 行为常量（模块级：测试可 monkeypatch SLEEP_AFTER_SECONDS 缩短闲置等待）
# ---------------------------------------------------------------------------
SLEEP_AFTER_SECONDS = 60.0        # IDLE 累计闲置达到该秒数 → 进入 SLEEP
TICK_MS = 33                      # 行为主循环周期
GRAVITY_PX_S2 = 2000.0            # FALL 重力加速度（px/s²）
WALK_SPEED_MIN_PX_S = 40.0        # 踱步速度随机区间
WALK_SPEED_MAX_PX_S = 90.0
WALK_MARGIN_PX = 20.0             # 随机目标 x 距屏幕左右的边距
WALK_RETARGET_MIN_S = 2.0         # 换目标的时间区间
WALK_RETARGET_MAX_S = 6.0
WALK_RETARGET_MIN_DIST = 80.0     # 新目标与当前 x 的最小距离
WALK_REST_ON_RETARGET = True      # 每次换目标后原地停顿片刻（F2「停顿」）
WALK_REACT_PROB_PER_S = 0.05      # 每秒约 5% 概率插播 quack/happy 反应
IDLE_REST_MIN_S = 1.0             # 原地停顿时长区间
IDLE_REST_MAX_S = 3.5
HOP_HEIGHT_PX = 60.0              # 单击 quack 的 y 抛物线峰值
HOP_DURATION_S = 0.5              # 抛物线总时长（约 500ms）
HOVER_COOLDOWN_S = 0.8            # 悬停惊讶反应冷却
LAND_HOLD_S = 0.2                 # 落地 jump 末帧压扁缓冲时长
FALL_SAFETY_S = 1.5               # 未收到 animation_finished 的落地兜底
REACT_SAFETY_S = 2.0              # 反应动画兜底时长
TICK_DT_MAX_S = 0.1               # 单拍 dt 上限（事件循环卡顿保护）
DEFAULT_WINDOW_SIZE = 150         # 窗口逻辑边长（契约固定 150×150）

# 状态 → 循环动画映射（FALL 用 drag 惊慌帧）。
# WALK 用右向侧视图 walk_side（左向由运行时镜像）；素材缺失时回退正面 walk。
_STATE_LOOP_ANIM = {
    "WALK": "walk_side",
    "IDLE": "idle",
    "DRAG": "drag",
    "FALL": "drag",
    "SLEEP": "sleep",
}
WALK_ANIM = "walk_side"           # 行走首选动画（右向侧视图帧）
WALK_ANIM_FALLBACK = "walk"       # 侧视帧缺失（旧素材）时的正面回退
# REACT 子类型 → 非循环动画
_REACT_ANIM = {"surprised": "surprised", "happy": "happy", "quack": "quack"}


class PetController(QObject):
    """行为状态机：窗口信号 → 状态转移 → animator.play / window.move_to。"""

    def __init__(self, window, animator) -> None:
        super().__init__()
        self._window = window
        self._animator = animator

        # ---- 状态机状态（契约：state 为状态字符串，idle_seconds 可被测试改写）----
        self.state = "IDLE"
        self.idle_seconds = 0.0        # IDLE 累计闲置秒数（任何交互清零）

        # ---- 运动量：float 累计，int 取整后调 move_to ----
        self._x = 0.0
        self._y = 0.0
        self._vy = 0.0                 # FALL 垂直速度
        self._facing_left = False      # 朝向（True=向左，play(flipped=True)）

        # ---- WALK 子状态 ----
        self._walk_target_x = None     # 当前目标 x（None=未定）
        self._walk_speed = 60.0        # px/s
        self._walk_deadline = 0.0      # 距下次强制换目标的秒数

        # ---- IDLE 子状态 ----
        self._idle_rest = None         # 本次停顿额定时长（paused 时 None）
        self._idle_mark = 0.0          # 进入 IDLE 时的 idle_seconds 基准

        # ---- REACT 子状态 ----
        self._react_kind = ""          # "surprised" / "happy" / "quack"
        self._react_t = 0.0
        self._hop_base_y = 0.0         # quack 抛物线基准 y

        # ---- FALL 子状态 ----
        self._fall_phase = ""          # "falling" / "landed"
        self._land_t = 0.0
        self._jump_done = False
        self._jump_done_t = 0.0

        self._paused = False
        self._started = False
        self._last_hover = -1e9        # 上次 hover 反应时刻（monotonic 秒）
        self._last_play = None         # (name, loop, flipped)，避免重复 play 打断帧推进
        self._walk_anim_ok = True      # walk_side 帧可用性（ValueError 探测后置 False）
        self._last_tick = 0.0

        # ---- 交互接线（契约：窗口信号 → 控制器槽）----
        window.hover_entered.connect(self._on_hover_entered)
        window.clicked.connect(self._on_clicked)
        window.double_clicked.connect(self._on_double_clicked)
        window.drag_started.connect(self._on_drag_started)
        window.drag_moved.connect(self._on_drag_moved)
        window.drag_released.connect(self._on_drag_released)
        animator.animation_finished.connect(self._on_animation_finished)

        # ---- 33ms 行为主循环 ----
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)

    # ------------------------------------------------------------------
    # 公开接口（契约）
    # ------------------------------------------------------------------
    def start(self) -> None:
        """初始位 (screen_rect 中心 - 半窗宽, floor_y)，播 walk 并启动主循环。"""
        size = self._win_size()
        rect = self._window.screen_rect()
        self._x = float(rect.center().x()) - size / 2.0
        self._y = float(self._window.floor_y())
        self._move()
        self.idle_seconds = 0.0
        self._walk_target_x = None
        self._pick_target()
        self._begin_walk()
        self._started = True
        self._last_tick = time.monotonic()
        self._timer.start(TICK_MS)

    def stop(self) -> None:
        """停止行为主循环（供退出清理）。"""
        self._timer.stop()
        self._started = False

    def set_walking_paused(self, paused: bool) -> None:
        """暂停/恢复走动：暂停时 WALK/IDLE 冻结为 IDLE 不移动，交互反应仍可用。"""
        self._paused = bool(paused)
        if self._paused:
            if self.state in ("WALK", "IDLE"):
                self._enter_idle()
        else:
            if self.state == "IDLE":
                self._begin_walk()

    def wake(self) -> None:
        """任意交互唤醒（供 app 层菜单等调用）：非拖拽/下落状态回 IDLE。"""
        if self.state in ("DRAG", "FALL"):
            self.idle_seconds = 0.0    # 物理过程不打断，仅重置闲置计时
            return
        if self.state == "SLEEP":
            self._wake_from_sleep()
            return
        self.idle_seconds = 0.0
        self._react_kind = ""
        self._react_t = 0.0
        self._y = float(self._window.floor_y())
        self._enter_idle()

    # ------------------------------------------------------------------
    # 窗口事件槽
    # ------------------------------------------------------------------
    def _on_hover_entered(self) -> None:
        self.idle_seconds = 0.0
        woke = False
        if self.state == "SLEEP":      # 睡眠中先唤醒
            self._wake_from_sleep()
            woke = True
        if self.state in ("DRAG", "FALL"):
            return
        now = time.monotonic()
        if not woke and (now - self._last_hover) < HOVER_COOLDOWN_S:
            return                     # 800ms 冷却
        self._last_hover = now
        self._begin_react("surprised")

    def _on_clicked(self) -> None:
        self.idle_seconds = 0.0
        self._begin_react("quack")     # SLEEP 中经由 _begin_react 先唤醒

    def _on_double_clicked(self) -> None:
        self.idle_seconds = 0.0
        self._begin_react("happy")

    def _on_drag_started(self) -> None:
        self.idle_seconds = 0.0
        self.state = "DRAG"
        self._react_kind = ""
        self._react_t = 0.0
        self._fall_phase = ""
        self._vy = 0.0
        self._play("drag", flipped=self._facing_left)

    def _on_drag_moved(self, pos) -> None:
        if self.state != "DRAG":
            return
        self.idle_seconds = 0.0
        self._x = float(pos.x())       # 契约：窗口左上角全局坐标，原样跟随
        self._y = float(pos.y())
        self._move()

    def _on_drag_released(self, pos) -> None:
        if self.state != "DRAG":
            return
        self.idle_seconds = 0.0
        self._x = float(pos.x())
        self._y = float(pos.y())
        self._vy = 0.0
        self._fall_phase = "falling"
        self._land_t = 0.0
        self._jump_done = False
        self._jump_done_t = 0.0
        self.state = "FALL"
        self._play("drag", flipped=self._facing_left)

    def _on_animation_finished(self, name: str) -> None:
        if self.state == "REACT" and name == self._react_kind:
            self._finish_react()
        elif (self.state == "FALL" and self._fall_phase == "landed"
              and name == "jump"):
            self._jump_done = True     # jump 末帧（压扁）已停在屏幕上

    # ------------------------------------------------------------------
    # 行为主循环
    # ------------------------------------------------------------------
    def _on_tick(self) -> None:
        """33ms 行为主循环（QTimer timeout；也可被测试手动调用）。"""
        if not self._started:
            return
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        if dt < 0.0:
            dt = 0.0
        elif dt > TICK_DT_MAX_S:
            dt = TICK_DT_MAX_S
        state = self.state
        if state == "WALK":
            self._tick_walk(dt)
        elif state == "IDLE":
            self._tick_idle(dt)
        elif state == "FALL":
            self._tick_fall(dt)
        elif state == "REACT":
            self._tick_react(dt)
        # DRAG 由 drag_moved 事件驱动；SLEEP 静止等待唤醒

    def _tick_walk(self, dt: float) -> None:
        """踱步：float 累计朝目标匀速移动，到达/超时换目标，小概率插播反应。"""
        if self._walk_target_x is None:
            self._pick_target()
        self._walk_deadline -= dt
        target = self._walk_target_x
        remaining = target - self._x
        step = self._walk_speed * dt
        arrived = abs(remaining) <= step
        if arrived and WALK_REST_ON_RETARGET:
            self._x = target
            self._enter_idle()         # 走到目标后原地停顿（F2 停顿）
            return
        if arrived:
            self._pick_target()
        else:
            self._x += step if remaining > 0 else -step
        # 每 tick 钳制在实时 screen_rect() 内（多显示器切换安全）
        rect = self._window.screen_rect()
        self._x = self._clamp(self._x, rect.left(),
                              rect.left() + rect.width() - self._win_size())
        self._facing_left = self._walk_target_x < self._x
        self._y = float(self._window.floor_y())
        self._move()
        self._play_walk()
        if not arrived and self._walk_deadline <= 0:
            self._pick_target()
        if random.random() < WALK_REACT_PROB_PER_S * dt:
            self._begin_react(random.choice(("quack", "happy")))

    def _tick_idle(self, dt: float) -> None:
        """闲置：累计 idle_seconds，达到阈值入睡；未暂停时停顿期满继续踱步。"""
        self.idle_seconds += dt
        if self.idle_seconds >= SLEEP_AFTER_SECONDS:
            self._enter_sleep()
            return
        if self._paused:
            return                     # 暂停走动：保持 IDLE 不动
        if self._idle_rest is None:    # 兼容外部直接改 state 的情形，懒初始化
            self._idle_mark = self.idle_seconds
            self._idle_rest = random.uniform(IDLE_REST_MIN_S, IDLE_REST_MAX_S)
        elif self.idle_seconds - self._idle_mark >= self._idle_rest:
            self._begin_walk()

    def _tick_fall(self, dt: float) -> None:
        """下落：重力 2000px/s²；触底后播 jump（末帧压扁）缓冲 200ms 再继续。"""
        if self._fall_phase == "falling":
            self._vy += GRAVITY_PX_S2 * dt
            self._y += self._vy * dt
            floor = float(self._window.floor_y())   # 实时取：拖到副屏落副屏底
            rect = self._window.screen_rect()
            self._x = self._clamp(self._x, rect.left(),
                                  rect.left() + rect.width() - self._win_size())
            self._y = self._clamp(self._y, float(rect.top()), floor)
            if self._y >= floor:
                self._y = floor
                self._fall_phase = "landed"
                self._land_t = 0.0
                self._jump_done = False
                self._jump_done_t = 0.0
                self._play("jump", loop=False)
            self._move()
        else:                          # landed：等 jump 播完（停末帧压扁）再缓冲
            self._land_t += dt
            if self._jump_done:
                self._jump_done_t += dt
            if ((self._jump_done and self._jump_done_t >= LAND_HOLD_S)
                    or self._land_t >= FALL_SAFETY_S):
                self._finish_landing()

    def _tick_react(self, dt: float) -> None:
        """反应：quack 带 y 抛物线 0→-60→0（约 500ms）；其余等动画播完。"""
        self._react_t += dt
        kind = self._react_kind
        if kind == "quack":
            t = min(self._react_t, HOP_DURATION_S)
            u = t / HOP_DURATION_S
            offset = -HOP_HEIGHT_PX * 4.0 * u * (1.0 - u)   # 峰值 -60
            self._y = self._hop_base_y + offset
            self._move()
            if self._react_t >= HOP_DURATION_S:
                self._finish_react()
        elif self._react_t >= REACT_SAFETY_S:
            self._finish_react()       # 兜底：正常由 animation_finished 结束

    # ------------------------------------------------------------------
    # 状态进入/退出辅助
    # ------------------------------------------------------------------
    def _begin_walk(self) -> None:
        """进入 WALK：沿用有效目标（失效则重选），朝向=移动方向播 walk。"""
        self.state = "WALK"
        self._react_kind = ""
        self._react_t = 0.0
        self._fall_phase = ""
        self._vy = 0.0
        self._idle_rest = None
        if self._walk_target_x is not None:
            rect = self._window.screen_rect()
            size = self._win_size()
            lo = rect.left() + WALK_MARGIN_PX
            hi = rect.left() + rect.width() - WALK_MARGIN_PX - size
            if not (lo - 1.0 <= self._walk_target_x <= hi + 1.0):
                self._walk_target_x = None   # 目标已不在当前屏内（换屏落地）
        if self._walk_target_x is None:
            self._pick_target()
        self._facing_left = self._walk_target_x < self._x
        self._play_walk()

    def _enter_idle(self) -> None:
        """进入 IDLE：paused 时无限停顿，否则停顿 1~3.5s 后继续踱步。"""
        self.state = "IDLE"
        self._react_kind = ""
        self._react_t = 0.0
        self._fall_phase = ""
        self._vy = 0.0
        self._walk_target_x = None
        self._idle_mark = self.idle_seconds
        self._idle_rest = (None if self._paused
                           else random.uniform(IDLE_REST_MIN_S, IDLE_REST_MAX_S))
        self._y = float(self._window.floor_y())
        self._play("idle", flipped=self._facing_left)

    def _enter_sleep(self) -> None:
        """进入 SLEEP：播 sleep 循环动画，静止等待任何窗口交互唤醒。"""
        self.state = "SLEEP"
        self.idle_seconds = 0.0
        self._react_kind = ""
        self._react_t = 0.0
        self._fall_phase = ""
        self._vy = 0.0
        self._walk_target_x = None
        self._idle_rest = None
        self._y = float(self._window.floor_y())
        self._play("sleep", flipped=self._facing_left)

    def _wake_from_sleep(self) -> None:
        """从 SLEEP 唤醒：先落回 IDLE（播放 idle），随后事件可再触发反应。"""
        self.idle_seconds = 0.0
        self._enter_idle()

    def _begin_react(self, kind: str) -> None:
        """进入 REACT；睡眠中先唤醒。拖拽/下落中的物理过程不插入反应。"""
        if self.state in ("DRAG", "FALL"):
            return
        if self.state == "SLEEP":
            self._wake_from_sleep()
        self.state = "REACT"
        self._react_kind = kind
        self._react_t = 0.0
        if kind == "quack":
            self._hop_base_y = float(self._window.floor_y())
        self._play(_REACT_ANIM[kind], loop=False, flipped=self._facing_left)

    def _finish_react(self) -> None:
        """反应结束：暂停中回 IDLE，否则回 WALK 继续踱步。"""
        if self.state != "REACT":
            return
        self._react_kind = ""
        self._react_t = 0.0
        self._y = float(self._window.floor_y())
        if self._paused:
            self._enter_idle()
        else:
            self._begin_walk()

    def _finish_landing(self) -> None:
        """落地缓冲结束：暂停中回 IDLE，否则回 WALK。"""
        if self.state != "FALL":
            return
        self._fall_phase = ""
        self._vy = 0.0
        self._y = float(self._window.floor_y())
        if self._paused:
            self._enter_idle()
        else:
            self._begin_walk()

    # ------------------------------------------------------------------
    # 底层工具
    # ------------------------------------------------------------------
    def _pick_target(self) -> None:
        """在 screen_rect() 内留 20px 边距随机选目标 x/速度/换目标时限。"""
        rect = self._window.screen_rect()
        size = self._win_size()
        lo = rect.left() + WALK_MARGIN_PX
        hi = rect.left() + rect.width() - WALK_MARGIN_PX - size
        if hi < lo:                    # 极窄屏兜底：居中
            lo = hi = float(rect.center().x()) - size / 2.0
        target = self._x
        for _ in range(12):            # 尽量避开原地，保证踱步可见
            target = random.uniform(lo, hi)
            if abs(target - self._x) >= WALK_RETARGET_MIN_DIST:
                break
        self._walk_target_x = target
        self._walk_speed = random.uniform(WALK_SPEED_MIN_PX_S, WALK_SPEED_MAX_PX_S)
        self._walk_deadline = random.uniform(WALK_RETARGET_MIN_S, WALK_RETARGET_MAX_S)

    def _play_walk(self) -> None:
        """播放行走动画：首选右向侧视图 walk_side（flipped=朝左时镜像出左视图）。

        侧视帧缺失（旧素材包）时探测到 ValueError 永久回退正面 walk。
        """
        name = WALK_ANIM if self._walk_anim_ok else WALK_ANIM_FALLBACK
        try:
            self._play(name, flipped=self._facing_left)
        except ValueError:
            self._walk_anim_ok = False
            self._play(WALK_ANIM_FALLBACK, flipped=self._facing_left)

    def _play(self, name: str, loop: bool = True, flipped: bool = False) -> None:
        """调 animator.play；循环动画与上次完全相同时跳过，避免打断帧推进。"""
        key = (name, bool(loop), bool(flipped))
        if loop and key == self._last_play:
            return
        self._last_play = key
        self._animator.play(name, loop=loop, flipped=flipped)

    def _move(self) -> None:
        """float 位置取整后下发窗口。"""
        self._window.move_to(int(round(self._x)), int(round(self._y)))

    def _win_size(self) -> int:
        """窗口逻辑边长（契约 150×150；窗口对象缺 width() 时用默认值）。"""
        getter = getattr(self._window, "width", None)
        try:
            value = int(getter()) if callable(getter) else 0
        except Exception:
            value = 0
        return value if value > 0 else DEFAULT_WINDOW_SIZE

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        if hi < lo:
            hi = lo
        return min(max(value, lo), hi)
