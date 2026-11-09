# -*- coding: utf-8 -*-
"""咕咕嘎嘎桌面宠物 - 动画关键帧表与批量导出（WP1）。

按需求文档第 4 节「动画资产契约」生成：
sprites/{anim}_{i:02d}.png（320x320 RGBA）与 assets/tray.png（64x64）。
运行：.venv/Scripts/python.exe tools/generate_sprites.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from character_art import draw_frame, draw_tray  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITES_DIR = os.path.join(ROOT, "sprites")
ASSETS_DIR = os.path.join(ROOT, "assets")

QUACK_TEXT = "咕咕嘎嘎!"

# 动画资产契约（需求文档第 4 节）：动画名 -> (帧数, fps, 循环)
CONTRACT = {
    "idle": (4, 3, True),
    "walk": (8, 10, True),
    "drag": (2, 6, True),
    "jump": (6, 12, False),
    "happy": (4, 6, False),
    "quack": (4, 8, False),
    "surprised": (2, 6, False),
    "sleep": (2, 2, True),
}


def _idle_frames():
    """呼吸起伏 + 其中 1 帧眨眼。"""
    return [
        dict(),
        dict(body_dy=-3, squash=0.995),
        dict(body_dy=-1.5, squash=0.998),
        dict(eye="blink", body_dy=-0.5),
    ]


def _walk_frames():
    """身体上下 + 左右脚交替（foot_phase 驱动）+ 鳍翼摆动 + 轻微摇摆。"""
    bob = (0, -2, -3, -2, 0, -2, -3, -2)
    frames = []
    for i in range(8):
        ph = i / 8.0
        swing = 9.0 * math.sin(2 * math.pi * ph)
        frames.append(dict(
            foot_phase=ph, body_dy=bob[i],
            flipper_angle_l=6 + swing, flipper_angle_r=6 - swing,
            rotate=2.2 * math.sin(2 * math.pi * ph),
        ))
    return frames


def _drag_frames():
    """惊慌：鳍翼上举、眼睛圆睁、腿悬空，左右小幅扑腾。"""
    base = dict(eye="surprised", mouth="open_wide", blush=0.25, beak_open=0.1)
    return [
        dict(base, flipper_angle_l=148, flipper_angle_r=160,
             foot_l_y=6, foot_r_y=1, rotate=-5),
        dict(base, flipper_angle_l=160, flipper_angle_r=148,
             foot_l_y=1, foot_r_y=6, rotate=5),
    ]


def _jump_frames():
    """下蹲 -> 腾空 -> 落地压扁缓冲 -> 回弹。"""
    return [
        dict(squash=0.86),                                              # 下蹲蓄力
        dict(body_dy=-16, squash=1.06, foot_l_y=7, foot_r_y=7,
             flipper_angle_l=38, flipper_angle_r=38, mouth="open_wide"),  # 起跳
        dict(body_dy=-32, squash=1.02, foot_l_y=12, foot_r_y=12,
             flipper_angle_l=58, flipper_angle_r=58, mouth="open_wide"),  # 腾空最高点
        dict(body_dy=-26, foot_l_y=9, foot_r_y=9,
             flipper_angle_l=44, flipper_angle_r=44),                     # 下落
        dict(squash=0.84, eye="blink", blush=0.85),                       # 落地压扁
        dict(squash=0.96, body_dy=-1, blush=0.6),                         # 回弹恢复
    ]


def _happy_frames():
    """眯眼 ^^ + 腮红加深 + 挥鳍翼。"""
    return [
        dict(eye="happy", blush=1.0, mouth="smile_open",
             flipper_angle_l=70, flipper_angle_r=18, body_dy=-2),
        dict(eye="happy", blush=1.0, mouth="smile_open",
             flipper_angle_l=18, flipper_angle_r=70, body_dy=0),
        dict(eye="happy", blush=1.0, mouth="smile_open",
             flipper_angle_l=70, flipper_angle_r=18, body_dy=-2),
        dict(eye="happy", blush=0.9, mouth="smile_small",
             flipper_angle_l=40, flipper_angle_r=40, body_dy=0),
    ]


def _quack_frames():
    """张喙 + 头顶气泡「咕咕嘎嘎!」。"""
    return [
        dict(beak_open=0.95, mouth="open_wide", bubble=QUACK_TEXT, body_dy=-2),
        dict(beak_open=0.35, mouth="smile_open", bubble=QUACK_TEXT, body_dy=0),
        dict(beak_open=0.95, mouth="open_wide", bubble=QUACK_TEXT, body_dy=-3),
        dict(beak_open=0.2, mouth="smile_open", bubble=QUACK_TEXT, body_dy=0),
    ]


def _surprised_frames():
    """惊讶定格：瞳孔缩小 + 微张嘴 + 轻微颤动。"""
    return [
        dict(eye="surprised", mouth="o", beak_open=0.15, blush=0.2,
             flipper_angle_l=22, flipper_angle_r=22, rotate=-2),
        dict(eye="surprised", mouth="o", beak_open=0.3, blush=0.2,
             flipper_angle_l=27, flipper_angle_r=27, rotate=2),
    ]


def _sleep_frames():
    """闭眼慢呼吸 + 旁侧 Zzz。"""
    return [
        dict(eye="closed", mouth="smile_small", zzz=True, head_tilt=5),
        dict(eye="closed", mouth="smile_small", zzz=True, head_tilt=6.5,
             body_dy=-2, squash=0.99),
    ]


ANIMATIONS = {
    "idle": _idle_frames,
    "walk": _walk_frames,
    "drag": _drag_frames,
    "jump": _jump_frames,
    "happy": _happy_frames,
    "quack": _quack_frames,
    "surprised": _surprised_frames,
    "sleep": _sleep_frames,
}


def main():
    for d in (SPRITES_DIR, ASSETS_DIR):
        os.makedirs(d, exist_ok=True)
    for name in list(CONTRACT):
        for old in _existing(SPRITES_DIR, name):
            os.remove(old)

    total = 0
    for name, builder in ANIMATIONS.items():
        frames = builder()
        want, fps, loop = CONTRACT[name]
        assert len(frames) == want, f"{name}: 帧数 {len(frames)} != 契约 {want}"
        for i, pose in enumerate(frames):
            out = os.path.join(SPRITES_DIR, f"{name}_{i:02d}.png")
            draw_frame(pose).save(out)
            total += 1
        print(f"[ok] {name:<10s} {want} 帧  fps={fps:<3g} loop={loop}")

    tray = os.path.join(ASSETS_DIR, "tray.png")
    draw_tray(64).save(tray)
    print(f"[ok] tray.png 64x64")
    print(f"共导出 {total} 帧 -> {SPRITES_DIR}")
    print(f"托盘图标 -> {tray}")


def _existing(sprite_dir, name):
    if not os.path.isdir(sprite_dir):
        return
    for f in os.listdir(sprite_dir):
        if f.startswith(name + "_") and f.endswith(".png"):
            yield os.path.join(sprite_dir, f)


if __name__ == "__main__":
    main()
