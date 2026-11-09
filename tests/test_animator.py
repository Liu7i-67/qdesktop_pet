"""SpriteAnimator 单元测试（真实类 app.sprite_animator.SpriteAnimator + conftest.sprites_dir）。

覆盖测试功能点：
- T1  帧推进：play("walk") 后按 fps 推进，frame_changed 依次发射、尺寸=150；
- T2  单播完成：play("jump", loop=False) 播完发 animation_finished("jump") 且停末帧；
      另覆盖“重复 play 重置”与“loop 循环回绕”；
- T3  翻转：flipped=True 时 pixmap 与原图水平镜像；
- 附加契约：fps 覆盖、默认 fps 表、帧缺失报 ValueError、stop 停止发帧。

所有等待统一使用 QTest.qWait（经 conftest.wait_until），不 sleep 轮询。
"""

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest

from app.sprite_animator import SpriteAnimator
from conftest import CONTRACT_FRAME_COUNTS, FRAME_MARKER_PALETTE, wait_until

# 150×150 逻辑尺寸下，底部序号色带内部的采样点（原 64×64 帧的 y≈61 行）
MARKER_SAMPLE = (75, 143)
# 帧内容：上半左红右蓝（供 T3），底部色带（供帧序解码）——以下采样点均避开区域边界
MIRROR_SAMPLES_X = (10, 40, 110, 140)
MIRROR_SAMPLES_Y = (15, 45, 75)
COLOR_TOL = 20  # 平滑缩放后纯色区域内部允许的最大通道偏差


@pytest.fixture()
def make_animator(qapp, sprites_dir, request):
    """构造绑定 sprites_dir 的 SpriteAnimator，测试结束后统一清理。"""
    made = []

    def _make(**kwargs):
        animator = SpriteAnimator(sprites_dir, **kwargs)
        made.append(animator)
        return animator

    def _cleanup():
        for animator in made:
            animator.stop()
            animator.deleteLater()

    request.addfinalizer(_cleanup)
    return _make


class _FrameRecorder:
    """记录 frame_changed / animation_finished 发射历史。"""

    def __init__(self, animator):
        self.pixmaps = []
        self.finished = []
        animator.frame_changed.connect(self._on_frame)
        animator.animation_finished.connect(self.finished.append)

    def _on_frame(self, pixmap):
        # 持有副本，避免实现层复用同一 QPixmap 导致历史被覆盖
        self.pixmaps.append(QPixmap(pixmap))

    def indices(self):
        return [self._decode(pm)[0] for pm in self.pixmaps]

    def clear(self):
        self.pixmaps.clear()
        self.finished.clear()

    @staticmethod
    def _decode(pixmap):
        """把底部色带采样像素按最近邻色解码为帧序号，返回 (序号, 最大通道偏差)。"""
        image = pixmap.toImage()
        color = image.pixelColor(*MARKER_SAMPLE)
        best_index, best_diff = 0, 10 ** 9
        for i, (r, g, b) in enumerate(FRAME_MARKER_PALETTE):
            diff = max(abs(color.red() - r), abs(color.green() - g), abs(color.blue() - b))
            if diff < best_diff:
                best_index, best_diff = i, diff
        return best_index, best_diff


# ---------------------------------------------------------------------------
# T1 帧推进
# ---------------------------------------------------------------------------
def test_t1_walk_frames_advance_in_order_and_wrap(make_animator):
    """T1：walk 按帧序 0,1,2,... 依次发射；持续播放应回绕（7 之后回到 0）。"""
    animator = make_animator()
    recorder = _FrameRecorder(animator)
    animator.play("walk", loop=True, fps=20.0)
    QTest.qWait(850)  # 20fps → 50ms/帧，预期约 16 帧 ≥ 2 个整循环

    indices = recorder.indices()
    assert len(indices) >= 10, (
        f"20fps 播放 850ms 应至少发射 10 帧，实际 {len(indices)} 帧——"
        "QTimer 帧推进未按 fps 工作"
    )
    assert indices[0] == 0, f"播放应从第 0 帧开始，实际首帧序号 {indices[0]}（完整序列 {indices}）"
    for prev, nxt in zip(indices, indices[1:]):
        assert (nxt - prev) % CONTRACT_FRAME_COUNTS["walk"] == 1, (
            f"帧应严格按序号递增推进（mod 8），出现跳变：…{prev} → {nxt}（完整序列 {indices}）"
        )
    wrapped = any(prev == 7 and nxt == 0 for prev, nxt in zip(indices, indices[1:]))
    assert wrapped, f"loop 播放超过一个循环后应回绕到第 0 帧（序列 {indices}）"


def test_t1_frame_pixmap_size_is_logical_size(make_animator):
    """T1：frame_changed 发射的 pixmap 应已缩放到 logical_size（默认 150）。"""
    animator = make_animator()
    recorder = _FrameRecorder(animator)
    animator.play("idle", loop=True, fps=10.0)
    QTest.qWait(500)

    assert recorder.pixmaps, "play 后应发射 frame_changed"
    for i, pixmap in enumerate(recorder.pixmaps):
        assert (pixmap.width(), pixmap.height()) == (150, 150), (
            f"第 {i} 帧尺寸应为 150×150（logical_size），"
            f"实际 {pixmap.width()}×{pixmap.height()}"
        )


# ---------------------------------------------------------------------------
# T2 单播完成 / 重播重置
# ---------------------------------------------------------------------------
def test_t2_one_shot_finishes_with_signal_and_last_frame(make_animator):
    """T2：jump 单播播完应发 animation_finished("jump")，停在第 5 帧（末帧）且不再发帧。"""
    animator = make_animator()
    recorder = _FrameRecorder(animator)
    animator.play("jump", loop=False)  # 契约默认 12fps × 6 帧 = 500ms
    QTest.qWait(1400)

    assert recorder.finished == ["jump"], (
        f"单播播完应恰好发射一次 animation_finished('jump')，实际 {recorder.finished}"
    )
    assert recorder.pixmaps, "单播过程中应发射过 frame_changed"
    last_index, last_diff = recorder._decode(recorder.pixmaps[-1])
    assert last_index == 5, (
        f"单播应停在末帧（第 5 帧），实际停在 {last_index}（偏差 {last_diff}）"
    )
    assert last_diff <= COLOR_TOL, (
        f"末帧色带颜色偏差 {last_diff} 超过容差 {COLOR_TOL}，帧内容与序号不符"
    )
    assert len(recorder.pixmaps) >= 4, (
        f"jump 共 6 帧，至少应观察到 4 帧，实际 {len(recorder.pixmaps)}"
    )
    stable = len(recorder.pixmaps)
    QTest.qWait(250)
    assert len(recorder.pixmaps) == stable, "单播结束后不应继续发射 frame_changed（应停末帧）"


def test_t2_replay_restarts_from_first_frame(make_animator):
    """T2 附加：对同一动画重复 play 应从第 0 帧重新开始（重置进度）。"""
    animator = make_animator()
    recorder = _FrameRecorder(animator)
    animator.play("walk", loop=True, fps=20.0)
    QTest.qWait(300)
    assert len(recorder.pixmaps) >= 3, "第一次播放应先推进若干帧"

    recorder.clear()
    animator.play("walk", loop=True, fps=20.0)  # 重复 play：重置
    QTest.qWait(150)
    indices = recorder.indices()
    assert indices, "重复 play 后应重新开始发射帧"
    assert indices[0] == 0, (
        f"重复 play 应重置到第 0 帧，实际重播后首帧序号 {indices[0]}（序列 {indices}）"
    )


# ---------------------------------------------------------------------------
# T3 翻转
# ---------------------------------------------------------------------------
def test_t3_flipped_is_horizontal_mirror_of_original(make_animator):
    """T3：flipped=True 的同帧 pixmap 应与原图水平镜像（逐采样点比对）。"""
    animator = make_animator()

    # 1) 原图：取 walk 第 0 帧（1fps 保证首个发射帧即第 0 帧）
    recorder = _FrameRecorder(animator)
    animator.play("walk", loop=True, fps=1.0, flipped=False)
    QTest.qWait(1300)
    original = next((pm for pm in recorder.pixmaps if recorder._decode(pm)[0] == 0), None)
    assert original is not None, "翻转前应收到 walk 第 0 帧"

    # 2) 翻转：重新 play（从第 0 帧开始），flipped=True
    animator.stop()
    recorder.clear()
    animator.play("walk", loop=True, fps=1.0, flipped=True)
    QTest.qWait(1300)
    flipped = next((pm for pm in recorder.pixmaps if recorder._decode(pm)[0] == 0), None)
    assert flipped is not None, "flipped=True 时应收到 walk 第 0 帧"
    assert (flipped.width(), flipped.height()) == (original.width(), original.height()), (
        "翻转后尺寸不应改变"
    )

    # 3) 逐点镜像比对：flipped(x=149-i, y) ≈ original(x=i, y)
    width = original.width()
    image_o = original.toImage()
    image_f = flipped.toImage()
    for x in MIRROR_SAMPLES_X:
        for y in MIRROR_SAMPLES_Y:
            c_o = image_o.pixelColor(x, y)
            c_f = image_f.pixelColor(width - 1 - x, y)
            diff = max(
                abs(c_o.red() - c_f.red()),
                abs(c_o.green() - c_f.green()),
                abs(c_o.blue() - c_f.blue()),
            )
            assert diff <= COLOR_TOL, (
                f"翻转帧 ({width - 1 - x},{y}) 与原图 ({x},{y}) 颜色差 {diff} "
                f"超过容差 {COLOR_TOL}：flipped 应为原图水平镜像（T3）"
            )


# ---------------------------------------------------------------------------
# fps 契约
# ---------------------------------------------------------------------------
def test_fps_override_takes_effect(make_animator):
    """fps 参数覆盖：idle 默认 3fps（600ms 至多 2 帧），显式 fps=40 应显著加速。"""
    animator = make_animator()
    recorder = _FrameRecorder(animator)
    animator.play("idle", loop=True, fps=40.0)  # 25ms/帧 → 600ms 约 24 帧
    QTest.qWait(600)
    count = len(recorder.pixmaps)
    assert 12 <= count <= 34, (
        f"fps=40 时 600ms 应约发射 24 帧（容差区间 12~34），实际 {count}——fps 覆盖未生效"
    )


def test_default_fps_table_is_applied(make_animator):
    """fps=None 时应使用契约默认 fps 表：walk=10fps、sleep=2fps。"""
    animator = make_animator()

    recorder = _FrameRecorder(animator)
    animator.play("walk", loop=True)  # 默认 10fps → 100ms/帧，650ms 约 7 帧
    QTest.qWait(650)
    walk_count = len(recorder.pixmaps)
    assert 4 <= walk_count <= 13, (
        f"walk 默认 10fps 时 650ms 应约 7 帧（容差区间 4~13），实际 {walk_count}"
    )

    animator.stop()
    recorder.clear()
    animator.play("sleep", loop=True)  # 默认 2fps → 500ms/帧，650ms 约 2 帧
    QTest.qWait(650)
    sleep_count = len(recorder.pixmaps)
    assert 1 <= sleep_count <= 3, (
        f"sleep 默认 2fps 时 650ms 应发射 1~3 帧，实际 {sleep_count}"
    )


# ---------------------------------------------------------------------------
# 帧缺失契约
# ---------------------------------------------------------------------------
def test_unknown_animation_raises_value_error(make_animator):
    """播放不存在的动画（目录中无对应帧文件）应抛 ValueError。"""
    animator = make_animator()
    with pytest.raises(ValueError):
        animator.play("no_such_animation")


def test_missing_frame_gap_raises_value_error(sprites_dir):
    """帧序号出现缺口（如缺 walk_02.png，编号不连续）应报 ValueError。"""
    from pathlib import Path

    gap = Path(sprites_dir) / "walk_02.png"
    gap.unlink()
    try:
        animator = SpriteAnimator(sprites_dir)  # 实现若在构造时探测则在此抛出
    except ValueError:
        return
    with pytest.raises(ValueError):
        animator.play("walk")  # 实现若在 play 时探测则在此抛出
    animator.stop()
    animator.deleteLater()


# ---------------------------------------------------------------------------
# stop 契约
# ---------------------------------------------------------------------------
def test_stop_halts_frame_emissions(make_animator):
    """stop() 后不应再发射 frame_changed。"""
    animator = make_animator()
    recorder = _FrameRecorder(animator)
    animator.play("walk", loop=True, fps=20.0)
    assert wait_until(lambda: len(recorder.pixmaps) >= 3, timeout_ms=1500), (
        "播放后应先有若干帧发射"
    )
    animator.stop()
    stable = len(recorder.pixmaps)
    QTest.qWait(250)
    assert len(recorder.pixmaps) == stable, "stop() 后不应继续发射帧"
