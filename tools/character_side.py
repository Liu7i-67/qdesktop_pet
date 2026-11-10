# -*- coding: utf-8 -*-
"""咕咕嘎嘎桌面宠物 - 侧面视图角色绘制器（v2 形象还原改造）。

draw_side_frame(pose) -> PIL.Image.Image（320x320 RGBA，面朝右，站立脚底基线 y=312）。
与 tools/character_art.py 正面绘制器共用 4x 超采样、贴纸剪影描边管线、调色板
与 pose 规范化/仿射变换；侧面特有几何（兜帽侧影、侧喙、单只假眼/真眼、
脑后发梢、侧白肚、小企鹅尾、双脚步态）在本模块实现。

pose 新增键（其余键语义与正面一致）：
- ``foot_dx_f`` / ``foot_dx_b``：前/后脚水平位移（px，+x 朝前）；
- ``flipper_angle_s``：侧面那只鳍翼的摆角（缺省沿用 ``flipper_angle_l``）。
"""
import math

from PIL import Image, ImageDraw, ImageFilter

from character_art import (
    SS, OUT, SZ, BASELINE, OUTLINE_K, OUTLINE_C,
    _norm, _transform, _pt, _e, _poly, _line, _rtri, _rell, _bbox, _C,
    DARK, DARK_HI, DARK_LO, HAIR, HAIR_HI, SKIN, SKIN_LO,
    BELLY, BELLY_LO, IRIS, IRIS_LO, IRIS_HI, PUPIL, EYE_WHITE,
    BLUSH_C, MOUTH_C2, TONGUE, BEAK, BEAK_HI, BEAK_LO,
    FOOT, FOOT_LO, RING, RING_LO, PIN,
)

# ================= 侧面布局常量（单位：320 空间像素，面朝右 = +x 前方） =================
S_HOOD_C, S_HOOD_R = (148.0, 106.0), (76.0, 74.0)   # 兜帽穹顶（侧影，与前视头顶齐高）
S_BEAK_BAR = (192.0, 105.0, 240.0, 123.0)           # 侧喙上条（圆角矩形 x0,y0,x1,y1）
S_BEAK_LOW = ((192.0, 112.0), (240.0, 114.0), (230.0, 140.0), (192.0, 140.0))
S_BEAK_CAP = (212.0, 134.0, 19.0, 8.0)              # 侧喙底帽（cx,cy,rx,ry）
S_FAKE_C, S_FAKE_R = (180.0, 84.0), (13.5, 11.0)    # 兜帽假眼（侧面只见一只）
S_FACE_C, S_FACE_R = (174.0, 176.0), (26.0, 36.0)   # 脸（兜帽开口内前下部）
S_RIM_C, S_RIM_R = (202.0, 172.0), (9.0, 32.0)      # 兜帽前缘包边（包住脸前缘）
S_EYE_C, S_EYE_R = (186.0, 172.0), (11.0, 12.5)     # 侧视单眼（窄椭圆）
S_BLUSH_C, S_BLUSH_R = (180.0, 190.0), (8.0, 5.0)
S_MOUTH_C = (182.0, 199.0)
S_HOOD_SKIRT = (128.0, 186.0, 34.0, 30.0)           # 兜帽下摆（填实脸后空间，垂到肩背）
S_BACK_HAIR = ((108.0, 230.0, 12.0, 13.0), (122.0, 236.0, 9.0, 8.0))
S_BACK_HAIR_POLY = ((104.0, 180.0), (136.0, 182.0), (128.0, 244.0), (106.0, 242.0))
S_HAIR_HI_LINES = (((110.0, 216.0), (107.0, 238.0)), ((118.0, 212.0), (115.0, 232.0)))
S_PIN_C = (162.0, 140.0)                # 十字发夹（右侧面恰为夹子一侧）
S_BODY_C, S_BODY_R = (160.0, 252.0), (56.0, 46.0)   # 侧影身体
S_BELLY_C, S_BELLY_R = (180.0, 258.0), (26.0, 32.0) # 侧白肚（前腹）
S_COLLAR = (180.0, 220.0)               # 项圈带（侧影短带）
S_RING_C = (184.0, 231.0)               # O 环
S_CARAB_C, S_CARAB_R = (186.0, 246.0), (6.0, 10.0)  # 登山扣
S_FLIPPER_S = (156.0, 234.0)            # 鳍翼根（侧面一只）
S_FLIPPER_LEN, S_FLIPPER_W = 46.0, 19.0
S_TAIL_TRI = ((116.0, 278.0), (88.0, 266.0), (86.0, 240.0))   # 小企鹅尾（后上方）
S_FOOT_F, S_FOOT_B, S_FOOT_CY = 188.0, 150.0, 298.5   # 前脚/后脚 x 与脚底中心 y


def draw_side_frame(pose=None) -> Image.Image:
    """按 pose 关键帧绘制一帧右向侧面 320x320 RGBA 精灵图。"""
    p = _side_norm(pose)
    char = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    mask = Image.new("L", (SZ, SZ), 0)
    _draw_side(ImageDraw.Draw(char), p, False)
    _draw_side(ImageDraw.Draw(mask), p, True)
    char, mask = _transform(char, mask, p)
    out = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    rim = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    rim.paste(OUTLINE_C, (0, 0), mask.filter(ImageFilter.MaxFilter(OUTLINE_K)))
    out.alpha_composite(rim)
    out.alpha_composite(char)
    return out.resize((OUT, OUT), Image.LANCZOS)


def _side_norm(pose):
    """复用正面 pose 规范化，补侧面扩展键。"""
    p = _norm(pose)
    pose = pose or {}
    p["foot_dx_f"] = float(pose.get("foot_dx_f") or 0.0)
    p["foot_dx_b"] = float(pose.get("foot_dx_b") or 0.0)
    p["flipper_angle_s"] = float(pose.get("flipper_angle_s",
                                          p["flipper_angle_l"]))
    return p


def _draw_side(d, p, solid):
    C = _C(solid)
    _side_foot(d, S_FOOT_B + p["foot_dx_b"], p["foot_r_y"], C, solid)   # 后脚（远侧）
    _rtri(d, *S_TAIL_TRI, 7.0, fill=C("DARK"))                          # 企鹅小尾
    _e(d, S_BODY_C[0], S_BODY_C[1], S_BODY_R[0], S_BODY_R[1], fill=C("DARK"))
    if not solid:
        _e(d, S_BELLY_C[0], S_BELLY_C[1], S_BELLY_R[0], S_BELLY_R[1],
           fill=C("BELLY"))                                             # 侧白肚
        d.pieslice(_bbox(S_BELLY_C[0] + 3, S_BELLY_C[1] + 4,
                         S_BELLY_R[0] - 6, S_BELLY_R[1] - 7), 30, 150,
                   fill=C("BELLY_LO"))
        _e(d, *S_COLLAR, 17, 6.0, fill=C("DARK_LO"),
           outline=C("OUTLINE_C"), width=int(1.4 * SS))                 # 项圈带
        d.arc(_bbox(S_COLLAR[0], S_COLLAR[1], 14, 4.2), 200, 340,
              fill=C("DARK_HI"), width=int(2 * SS))
        _e(d, S_CARAB_C[0], S_CARAB_C[1], S_CARAB_R[0] + 1.4, S_CARAB_R[1] + 1.4,
           outline=C("OUTLINE_C"), width=int(2.6 * SS))
        _e(d, S_CARAB_C[0], S_CARAB_C[1], S_CARAB_R[0], S_CARAB_R[1],
           outline=C("RING"), width=int(3.0 * SS))                      # 登山扣
        d.arc(_bbox(S_CARAB_C[0], S_CARAB_C[1], S_CARAB_R[0], S_CARAB_R[1]),
              20, 160, fill=C("RING_LO"), width=int(2.6 * SS))
        _e(d, S_RING_C[0], S_RING_C[1], 6.0, 6.0,
           outline=C("OUTLINE_C"), width=int(2.4 * SS))
        _e(d, S_RING_C[0], S_RING_C[1], 6.0, 6.0,
           outline=C("RING"), width=int(3.0 * SS))                      # O 环
    _side_flipper(d, p["flipper_angle_s"], C, solid)
    _side_foot(d, S_FOOT_F + p["foot_dx_f"], p["foot_l_y"], C, solid)   # 前脚（近侧）
    _side_head(d, p, C, solid)


def _side_flipper(d, ang, C, solid):
    """侧面唯一可见的鳍翼：绕肩旋转的长椭圆（复用正面几何逻辑）。"""
    a = math.radians(ang)
    sx, sy = S_FLIPPER_S
    dx, dy = math.sin(a), math.cos(a)
    px, py = -dy, dx

    def poly(L, W, **kw):
        cx, cy = sx + dx * L / 2, sy + dy * L / 2
        pts = []
        for i in range(40):
            t = 2 * math.pi * i / 40
            u, v = L / 2 * math.cos(t), W / 2 * math.sin(t)
            pts.append((cx + dx * u + px * v, cy + dy * u + py * v))
        _poly(d, pts, **kw)

    if not solid:
        poly(S_FLIPPER_LEN + 4.5, S_FLIPPER_W + 4.5, fill=C("OUTLINE_C"))
    poly(S_FLIPPER_LEN, S_FLIPPER_W, fill=C("DARK"))


def _side_foot(d, fx, lift, C, solid):
    """侧面蹼足：长椭圆脚掌 + 前缘三趾（朝 +x）。"""
    y = S_FOOT_CY - lift
    _e(d, fx, y, 14.0, 11.0, fill=C("FOOT"))                          # 脚掌
    if not solid:
        d.pieslice(_bbox(fx, y, 14.0, 11.0), 20, 160, fill=C("FOOT_LO"))
    for tx, ty in ((12.0, -3.5), (14.0, 2.0), (10.0, 6.0)):           # 前缘三趾
        _e(d, fx + tx, y + ty, 5.0, 5.0, fill=C("FOOT"))


def _side_head(d, p, C, solid):
    _e(d, S_HOOD_C[0], S_HOOD_C[1], S_HOOD_R[0], S_HOOD_R[1], fill=C("DARK"))   # 穹顶
    _e(d, *S_HOOD_SKIRT, fill=C("DARK"))                                    # 下摆（入剪影）
    _side_beak(d, C, solid)                                                 # 侧喙（伸出剪影，须入蒙版）
    if not solid:
        d.arc(_bbox(S_HOOD_C[0], S_HOOD_C[1], S_HOOD_R[0] - 7, S_HOOD_R[1] - 7),
              170, 262, fill=C("DARK_HI"), width=int(8 * SS))               # 顶部高光
        _side_fake_eye(d, C)                                                # 兜帽假眼（侧视一只）
    _poly(d, S_BACK_HAIR_POLY, fill=C("HAIR"))                              # 脑后发量（帽边下露梢）
    for hx, hy, hr_x, hr_y in S_BACK_HAIR:                                  # 发梢圆瓣
        _e(d, hx, hy, hr_x, hr_y, fill=C("HAIR"))
    _e(d, S_FACE_C[0], S_FACE_C[1], S_FACE_R[0], S_FACE_R[1], fill=C("SKIN"))   # 脸
    if not solid:
        _side_face(d, p, C)
    _side_bangs(d, C)
    _e(d, S_RIM_C[0], S_RIM_C[1], S_RIM_R[0], S_RIM_R[1], fill=C("DARK"))   # 兜帽前缘包边
    if not solid:
        _side_pin(d)
        for p0, p1 in S_HAIR_HI_LINES:                                  # 发丝高光
            _line(d, [p0, p1], 2.2, fill=C("HAIR_HI"))


def _side_beak(d, C, solid):
    """侧喙：上圆角条 + 下斜块 + 底圆帽三段并集（根部藏进穹顶）。"""
    bx0, by0, bx1, by1 = S_BEAK_BAR
    cen = (sum(x for x, _ in S_BEAK_LOW) / len(S_BEAK_LOW),
           sum(y for _, y in S_BEAK_LOW) / len(S_BEAK_LOW))
    if not solid:
        d.rounded_rectangle([(bx0 - 2.5) * SS, (by0 - 2.5) * SS,
                             (bx1 + 2.5) * SS, (by1 + 2.5) * SS],
                            radius=8 * SS, fill=C("OUTLINE_C"))
        big = [(cen[0] + (x - cen[0]) * 1.10, cen[1] + (y - cen[1]) * 1.10)
               for x, y in S_BEAK_LOW]
        _poly(d, big, fill=C("OUTLINE_C"))
        _e(d, S_BEAK_CAP[0], S_BEAK_CAP[1] + 1, S_BEAK_CAP[2] + 2.5,
           S_BEAK_CAP[3] + 2.5, fill=C("OUTLINE_C"))
    d.rounded_rectangle([bx0 * SS, by0 * SS, bx1 * SS, by1 * SS],
                        radius=6.5 * SS, fill=C("BEAK"))                # 上条
    _poly(d, S_BEAK_LOW, fill=C("BEAK"))                                # 下斜块
    _e(d, S_BEAK_CAP[0], S_BEAK_CAP[1], S_BEAK_CAP[2], S_BEAK_CAP[3],
       fill=C("BEAK"))                                                  # 底圆帽
    if not solid:
        _poly(d, [(194.0, 118.0), (234.0, 118.0), (230.0, 131.0),
                  (194.0, 131.0)], fill=C("BEAK_LO"))                   # 喙下半渐变
        d.rounded_rectangle([(bx0 + 6) * SS, (by0 + 3) * SS,
                             (bx1 - 14) * SS, (by0 + 7.5) * SS],
                            radius=3 * SS, fill=C("BEAK_HI"))           # 顶面高光


def _side_fake_eye(d, C):
    cx, cy = S_FAKE_C
    _rell(d, cx, cy, S_FAKE_R[0] + 2.5, S_FAKE_R[1] + 2.5, -8.0, fill=C("OUTLINE_C"))
    _rell(d, cx, cy, S_FAKE_R[0], S_FAKE_R[1], -8.0, fill=C("WHITE"))
    _e(d, cx + 4.6, cy + 4.6, 4.6, 4.6, fill=C("PUPIL"))                # 瞳仁前下望
    _e(d, cx + 3.0, cy + 2.6, 1.5, 1.5, fill=C("WHITE"))


def _side_face(d, p, C):
    """侧脸细节：单眼 + 腮红 + 侧开口笑。"""
    bx, by = S_BLUSH_C
    _e(d, bx, by, S_BLUSH_R[0], S_BLUSH_R[1], fill=C("BLUSH_C"))
    _side_eye(d, p["eye"], C)
    cx, cy = S_MOUTH_C
    d.pieslice(_bbox(cx, cy, 8.0, 7.0, 1.4), 0, 180, fill=C("OUTLINE_C"))
    d.pieslice(_bbox(cx, cy, 6.6, 5.6, 0), 0, 180, fill=C("MOUTH_C2"))
    d.pieslice(_bbox(cx, cy + 2.2, 4.0, 4.6), 0, 180, fill=C("TONGUE"))


def _side_eye(d, mode, C):
    cx, cy = S_EYE_C
    rx, ry = S_EYE_R
    if mode in ("blink", "closed"):                                        # 眨眼/闭眼
        d.arc(_bbox(cx, cy + 1, rx - 1.5, ry - 3.5), 10, 170,
              fill=C("OUTLINE_C"), width=int(3.2 * SS))
        return
    if mode == "happy":                                                    # 眯眼 ^^
        d.arc(_bbox(cx, cy, rx - 0.5, ry - 4.0), 180, 360,
              fill=C("OUTLINE_C"), width=int(4.0 * SS))
        return
    _e(d, cx, cy, rx, ry, fill=C("EYE_WHITE"))                             # 睁眼
    _e(d, cx, cy + 0.5, rx - 0.5, ry - 0.5, fill=C("IRIS"))
    d.pieslice(_bbox(cx, cy - 2.0, rx - 0.8, ry - 3.0), 180, 360, fill=C("IRIS_LO"))
    d.pieslice(_bbox(cx, cy + 1.5, rx - 1.0, ry - 2.4), 40, 140, fill=C("IRIS_HI"))
    _e(d, cx, cy + 1.8, 4.4, 5.0, fill=C("PUPIL"))
    _e(d, cx - 3.6, cy - 4.6, 3.8, 3.8, fill=C("WHITE"))
    _e(d, cx + 3.8, cy + 5.2, 1.9, 1.9, fill=C("WHITE"))
    _e(d, cx, cy + 7.4, 4.8, 2.1, fill=C("IRIS_HI"))                       # 底缘反光
    _e(d, cx, cy, rx, ry, outline=C("OUTLINE_C"), width=int(1.6 * SS))
    d.arc(_bbox(cx, cy, rx + 0.5, ry + 0.5), 195, 345,
          fill=C("OUTLINE_C"), width=int(3.2 * SS))                        # 上睫毛


def _side_bangs(d, C):
    """侧刘海：斜盖脸顶的齿状发梢 + 与脑后垂发衔接。"""
    _poly(d, [(138.0, 120.0), (188.0, 122.0), (204.0, 134.0), (206.0, 148.0),
              (140.0, 148.0)], fill=C("HAIR"))                             # 斜刘海主体
    tips = ((148.0, 156.0), (163.0, 160.0), (178.0, 156.0), (193.0, 159.0), (204.0, 153.0))
    for bx, tip_y in tips:
        _poly(d, [(bx - 8.5, 144.0), (bx + 8.5, 144.0), (bx, tip_y)],
              fill=C("HAIR"))                                              # 尖发梢
        _e(d, bx, tip_y - 2.5, 3.8, 3.8, fill=C("HAIR"))


def _side_pin(d):
    """十字发夹（右侧面恰为原素材夹子一侧）。"""
    x, y = S_PIN_C
    _line(d, [(x - 9.0, y + 4.5), (x + 9.0, y - 4.5)], 3.8, fill=PIN)
    _line(d, [(x - 4.5, y - 7.5), (x + 4.5, y + 7.5)], 3.8, fill=PIN)
    for ex, ey in ((x - 9.0, y + 4.5), (x + 9.0, y - 4.5),
                   (x - 4.5, y - 7.5), (x + 4.5, y + 7.5)):
        _e(d, ex, ey, 1.8, 1.8, fill=PIN)


if __name__ == "__main__":
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    draw_side_frame().save(os.path.join(root, "tools_out", "dev_side.png"))
    print("saved: tools_out/dev_side.png")
