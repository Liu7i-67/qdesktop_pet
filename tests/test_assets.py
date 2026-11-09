"""T12：真实精灵资产完整性校验（sprites/ 由 WP1 产出，320×320 RGBA）。

覆盖测试功能点：
- T12 资源完整：各动画帧数 ≥ 契约表；全部帧 320×320、RGBA；
  抽查 idle_00 脚底基线 y=312±2（按 alpha≥128 的最下缘判定，忽略半透明抗锯齿/阴影）。

说明：sprites/ 未生成时整模块 pytest.skip("sprites 未生成")；
T14 回归 = 整个测试套件在 offscreen 平台全部通过（main 导入冒烟见 test_window.py）。
"""

from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPRITES_DIR = PROJECT_ROOT / "sprites"

# 需求文档第 4 节《动画资产契约》
CONTRACT_FRAMES = {
    "idle": 4,
    "walk": 8,
    "jump": 6,
    "drag": 2,
    "quack": 4,
    "happy": 4,
    "surprised": 2,
    "sleep": 2,
}
CONTRACT_SIZE = (320, 320)
BASELINE_Y = 312      # 站立帧脚底基线
BASELINE_TOL = 2      # T12 允差 ±2px
ALPHA_SOLID = 127     # 判定“实体像素”的 alpha 下限（过滤半透明抗锯齿边与软阴影）


def _sprites_ready():
    return SPRITES_DIR.is_dir() and any(SPRITES_DIR.glob("*_*.png"))


if not _sprites_ready():
    pytest.skip("sprites 未生成", allow_module_level=True)


def _frames(anim):
    return sorted(SPRITES_DIR.glob(f"{anim}_*.png"))


def test_t12_all_animations_have_enough_frames():
    """每个动画的帧数应 ≥ 契约表，且存在起始帧 {anim}_00.png。"""
    for anim, need in CONTRACT_FRAMES.items():
        files = _frames(anim)
        assert len(files) >= need, (
            f"动画 {anim} 帧数不足：契约要求 ≥{need} 帧，实际 {len(files)} 帧 "
            f"（{[f.name for f in files]}）（T12）"
        )
        assert (SPRITES_DIR / f"{anim}_00.png").exists(), (
            f"动画 {anim} 缺少起始帧 {anim}_00.png（命名契约 {{anim}}_{{i:02d}}.png）"
        )


def test_t12_all_frames_are_320_rgba():
    """全部帧应为 320×320、RGBA PNG。"""
    problems = []
    for anim in CONTRACT_FRAMES:
        for path in _frames(anim):
            try:
                with Image.open(path) as image:
                    if image.size != CONTRACT_SIZE:
                        problems.append(f"{path.name}: 尺寸 {image.size[0]}×{image.size[1]} != 320×320")
                    if image.mode != "RGBA":
                        problems.append(f"{path.name}: 颜色模式 {image.mode} != RGBA")
            except OSError as exc:
                problems.append(f"{path.name}: 无法解析的 PNG（{exc}）")
    assert not problems, (
        "存在不符合资产契约的帧（T12，共 %d 处）：\n%s" % (len(problems), "\n".join(problems))
    )


def test_t12_idle_00_foot_baseline_near_312():
    """抽查 idle_00：alpha 最下缘（脚底基线）应为 y=312±2。

    以 alpha≥ALPHA_SOLID 的实体像素判定基线，避免半透明抗锯齿/软阴影干扰。
    """
    path = SPRITES_DIR / "idle_00.png"
    with Image.open(path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        solid = alpha.point(lambda a: 255 if a > ALPHA_SOLID else 0)
        bbox = solid.getbbox()  # (left, top, right, bottom)，bottom 为开区间

    assert bbox is not None, "idle_00 不含实体像素（alpha 最下缘不存在），无法校验脚底基线"
    base_y = bbox[3] - 1  # bbox 下缘为开区间，实体最下一行 = bbox[3]-1
    assert abs(base_y - BASELINE_Y) <= BASELINE_TOL, (
        f"idle_00 脚底基线（alpha 最下缘）y={base_y}，应为 {BASELINE_Y}±{BASELINE_TOL}（T12）"
    )
