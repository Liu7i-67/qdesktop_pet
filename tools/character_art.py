# -*- coding: utf-8 -*-
"""咕咕嘎嘎桌面宠物 - 参数化角色绘制器（WP1）。

draw_frame(pose: dict) -> PIL.Image.Image（320x320 RGBA，面朝右，站立脚底基线 y=312）
内部以 1280x1280（4x）超采样绘制再 LANCZOS 缩小，保证描边与曲线平滑；
剪影膨胀生成贴纸式连续描边。调色板与部件几何集中在顶部常量区便于调参。
"""
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ================= 画布 / 布局常量（单位：320 空间像素） =================
SS = 4                                  # 超采样倍率（320*4=1280）
OUT = 320
SZ = OUT * SS
BASELINE = 312.0                        # 站立帧脚底基线
CX = 160.0                              # 角色中轴

HOOD_C, HOOD_R = (160.0, 102.0), (83.0, 78.0)     # 兜帽大穹顶
DRAPE_R = (16.0, 40.0)                  # 兜帽侧垂布（拥抱头部到肩）
FACE_C, FACE_R = (160.0, 173.0), (60.0, 49.0)     # 女孩脸
BODY_C, BODY_R = (160.0, 246.0), (68.0, 48.0)     # 企鹅连体服身体
BELLY_C, BELLY_R = (160.0, 254.0), (43.0, 33.0)   # 白肚皮
EYE_L, EYE_R = (137.0, 186.0), (183.0, 186.0)     # 真眼中心
EYE_RAD = (16.0, 18.0)
FAKE_L, FAKE_R = (120.0, 67.0), (200.0, 67.0)     # 兜帽假眼睛（大而圆、分列喙两侧上方）
FAKE_RAD, FAKE_TILT = (20.0, 15.5), 10.0
BEAK_TOP, BEAK_TIP, BEAK_HW = 85.0, 120.0, 31.0   # 兜帽黄喙（顶/尖/半宽）
MOUTH_C = (160.0, 207.5)
BLUSH_L, BLUSH_R, BLUSH_RAD = (118.0, 206.0), (202.0, 206.0), (11.0, 6.5)
COLLAR_C = (160.0, 231.0)               # 黑项圈带
RING_C = (160.0, 245.0)                 # 银色 O 环
SHOULDER_L, SHOULDER_R = (106.0, 222.0), (214.0, 222.0)
FLIPPER_LEN, FLIPPER_W = 52.0, 22.0
FOOT_LX, FOOT_RX, FOOT_CY = 134.0, 189.0, 298.5   # 橙色蹼足
NECK_PIVOT = (160.0, 196.0)             # 头部倾斜枢轴
SPIN_C = (160.0, 250.0)                 # 整体旋转中心
OUTLINE_K = 19                          # 剪影膨胀核（奇数，SS 像素，19/4≈2.3px 描边）

# ================= 调色板 =================
OUTLINE_C = (30, 25, 36, 255)     # 贴纸深描边
DARK = (54, 50, 66, 255)          # 兜帽/连体服主色（黑企鹅布）
DARK_HI = (88, 84, 104, 255)      # 布面高光
DARK_LO = (40, 37, 50, 255)       # 布面阴影
HAIR = (44, 33, 40, 255)          # 深黑褐头发
HAIR_HI = (70, 54, 62, 255)       # 发丝高光
SKIN = (255, 232, 217, 255)       # 皮肤
SKIN_LO = (247, 206, 188, 255)    # 皮肤阴影
BELLY = (253, 250, 243, 255)      # 白肚皮
BELLY_LO = (232, 224, 214, 255)
IRIS = (126, 154, 188, 255)       # 灰蓝虹膜
IRIS_LO = (74, 96, 126, 255)
IRIS_HI = (192, 210, 229, 255)
PUPIL = (37, 43, 56, 255)
EYE_WHITE = (250, 252, 254, 255)
BLUSH_C = (255, 138, 160, 255)    # 腮红
MOUTH_C2 = (156, 62, 72, 255)     # 口腔
TONGUE = (240, 136, 150, 255)
BEAK = (255, 201, 60, 255)        # 兜帽黄喙
BEAK_LO = (246, 182, 48, 255)
FOOT = (255, 158, 44, 255)        # 橙色蹼足
FOOT_LO = (238, 126, 26, 255)
RING = (203, 208, 218, 255)       # 银 O 环
RING_LO = (140, 147, 160, 255)
WHITE = (255, 255, 255, 255)
INK = (56, 50, 66, 255)           # 气泡文字
ZZZ_C = (92, 106, 148, 255)       # Zzz
PIN = (24, 20, 28, 255)           # 黑色十字发夹
FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
_FONT_CACHE = {}


def draw_frame(pose=None) -> Image.Image:
    """按 pose 关键帧绘制一帧 320x320 RGBA 精灵图。缺省键使用合理默认值。"""
    p = _norm(pose)
    char = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    mask = Image.new("L", (SZ, SZ), 0)
    _draw_body(ImageDraw.Draw(char), p, False)
    _draw_body(ImageDraw.Draw(mask), p, True)
    head = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    hmask = Image.new("L", (SZ, SZ), 0)
    _draw_head(head, p, False)
    _draw_head(hmask, p, True)
    if abs(p["head_tilt"]) > 0.05:
        head = head.rotate(p["head_tilt"], Image.BICUBIC, center=_pt(NECK_PIVOT))
        hmask = hmask.rotate(p["head_tilt"], Image.BILINEAR, center=_pt(NECK_PIVOT))
    char.alpha_composite(head)
    mask.paste(hmask, (0, 0), hmask)
    if p["bubble"]:
        _draw_bubble(ImageDraw.Draw(char), p)
    if p["zzz"]:
        _draw_zzz(ImageDraw.Draw(char))
    char, mask = _transform(char, mask, p)
    out = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    rim = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    rim.paste(OUTLINE_C, (0, 0), mask.filter(ImageFilter.MaxFilter(OUTLINE_K)))
    out.alpha_composite(rim)
    out.alpha_composite(char)
    return out.resize((OUT, OUT), Image.LANCZOS)


# ---------------- pose 规范化 ----------------
def _norm(pose):
    p = dict(pose or {})

    def _f(key, default):
        v = p.get(key, default)
        return default if v is None else v

    p["body_dx"] = float(_f("body_dx", 0.0))
    p["body_dy"] = float(_f("body_dy", 0.0))
    p["squash"] = min(1.35, max(0.55, float(_f("squash", 1.0))))
    p["foot_phase"] = float(_f("foot_phase", 0.0)) % 1.0
    p["foot_l_y"] = _f("foot_l_y", None)
    p["foot_r_y"] = _f("foot_r_y", None)
    if p["foot_l_y"] is None:
        p["foot_l_y"] = max(0.0, math.sin(2 * math.pi * p["foot_phase"])) * 9.5
    if p["foot_r_y"] is None:
        p["foot_r_y"] = max(0.0, math.sin(2 * math.pi * p["foot_phase"] + math.pi)) * 9.5
    p["flipper_angle_l"] = float(_f("flipper_angle_l", 0.0))
    p["flipper_angle_r"] = float(_f("flipper_angle_r", 0.0))
    p["head_tilt"] = float(_f("head_tilt", 0.0))
    p["eye"] = str(_f("eye", "open"))
    p["mouth"] = str(_f("mouth", "smile_open"))
    p["beak_open"] = min(1.0, max(0.0, float(_f("beak_open", 0.0))))
    p["blush"] = min(1.0, max(0.0, float(_f("blush", 0.55))))
    p["rotate"] = float(_f("rotate", 0.0))
    p["zzz"] = bool(_f("zzz", False))
    p["bubble"] = _f("bubble", None)
    return p


def _transform(char, mask, p):
    """squash（绕脚底基线，脚底不动）-> rotate（整体）-> body_dx/dy 平移。"""
    s = p["squash"]
    if abs(s - 1.0) > 1e-3:
        k = 1.0 / math.sqrt(s)
        coeff = (1 / k, 0, CX * SS * (1 - 1 / k),
                 0, 1 / s, BASELINE * SS * (1 - 1 / s))
        char = char.transform((SZ, SZ), Image.AFFINE, coeff, resample=Image.BILINEAR)
        mask = mask.transform((SZ, SZ), Image.AFFINE, coeff, resample=Image.NEAREST)
    if abs(p["rotate"]) > 0.05:
        char = char.rotate(p["rotate"], Image.BICUBIC, center=_pt(SPIN_C))
        mask = mask.rotate(p["rotate"], Image.BILINEAR, center=_pt(SPIN_C))
    dx, dy = int(round(p["body_dx"] * SS)), int(round(p["body_dy"] * SS))
    if dx or dy:
        c2 = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
        c2.alpha_composite(char, (dx, dy))
        m2 = Image.new("L", (SZ, SZ), 0)
        m2.paste(mask, (dx, dy))
        char, mask = c2, m2
    return char, mask


# ---------------- 基础绘制助手（全部自动 *SS） ----------------
def _pt(xy):
    return (xy[0] * SS, xy[1] * SS)


def _e(d, cx, cy, rx, ry, **kw):
    d.ellipse([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS], **kw)


def _bbox(cx, cy, rx, ry, pad=0.0):
    return [(cx - rx - pad) * SS, (cy - ry - pad) * SS, (cx + rx + pad) * SS, (cy + ry + pad) * SS]


def _poly(d, pts, **kw):
    d.polygon([(x * SS, y * SS) for x, y in pts], **kw)


def _line(d, pts, w, **kw):
    d.line([(x * SS, y * SS) for x, y in pts], width=max(1, int(w * SS)), joint="curve", **kw)


def _rell(d, cx, cy, rx, ry, ang, n=48, **kw):
    a = math.radians(ang)
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append((cx + x * math.cos(a) - y * math.sin(a),
                    cy + x * math.sin(a) + y * math.cos(a)))
    _poly(d, pts, **kw)


def _rtri(d, p1, p2, p3, r, **kw):
    """圆角三角形：三边多边形 + 三顶点圆。"""
    _poly(d, [p1, p2, p3], **kw)
    for x, y in (p1, p2, p3):
        _e(d, x, y, r, r, **kw)


def _C(solid):
    return (lambda key: 255) if solid else (lambda key: globals()[key])


# ---------------- 身体（脚/身/项圈/鳍翼） ----------------
def _draw_body(d, p, solid):
    C = _C(solid)
    _foot(d, FOOT_LX, p["foot_l_y"], C, solid)
    _foot(d, FOOT_RX, p["foot_r_y"], C, solid)
    _e(d, BODY_C[0], BODY_C[1], BODY_R[0], BODY_R[1], fill=C("DARK"))          # 连体服
    if not solid:
        _e(d, BELLY_C[0], BELLY_C[1], BELLY_R[0], BELLY_R[1], fill=C("BELLY"))  # 白肚皮
        d.pieslice(_bbox(BELLY_C[0], BELLY_C[1] + 4, BELLY_R[0] - 6, BELLY_R[1] - 7),
                   30, 150, fill=C("BELLY_LO"))
        _e(d, CX, 224.0, 25, 8, fill=C("SKIN"))                                 # 脖颈
        _e(d, COLLAR_C[0], COLLAR_C[1], 32, 7.5, fill=C("DARK_LO"),
           outline=C("OUTLINE_C"), width=int(1.4 * SS))                         # 项圈
        d.arc(_bbox(COLLAR_C[0], COLLAR_C[1], 29, 5.5), 200, 340,
              fill=C("DARK_HI"), width=int(2 * SS))
        _e(d, RING_C[0], RING_C[1], 9.0, 9.0, outline=C("RING"), width=int(3.4 * SS))
        d.arc(_bbox(RING_C[0], RING_C[1], 9.0, 9.0), 30, 150,
              fill=C("RING_LO"), width=int(3 * SS))
    _flipper(d, SHOULDER_L[0], SHOULDER_L[1], p["flipper_angle_l"], -1, C, solid)
    _flipper(d, SHOULDER_R[0], SHOULDER_R[1], p["flipper_angle_r"], 1, C, solid)


def _flipper(d, sx, sy, ang, side, C, solid):
    """鳍翼：绕肩旋转的长椭圆，ang=0 下垂，正值向外展开；带描边缝线。"""
    a = math.radians(ang)
    dx, dy = side * math.sin(a), math.cos(a)
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
        poly(FLIPPER_LEN + 4.5, FLIPPER_W + 4.5, fill=C("OUTLINE_C"))
    poly(FLIPPER_LEN, FLIPPER_W, fill=C("DARK"))


def _foot(d, fx, lift, C, solid):
    y = FOOT_CY - lift
    _e(d, fx - 3, y, 16, 11, fill=C("FOOT"))                         # 脚掌
    if not solid:
        d.pieslice(_bbox(fx - 3, y, 16, 11), 20, 160, fill=C("FOOT_LO"))
    for tx, ty in ((10.5, -7), (14.5, 0), (10.5, 6)):                # 三趾（朝前/右）
        _e(d, fx + tx, y + ty, 6.0, 6.0, fill=C("FOOT"))


# ---------------- 头部（兜帽/假眼/喙/脸/发） ----------------
def _draw_head(img, p, solid):
    d = ImageDraw.Draw(img)
    C = _C(solid)
    _e(d, HOOD_C[0], HOOD_C[1], HOOD_R[0], HOOD_R[1], fill=C("DARK"))          # 穹顶
    _e(d, HOOD_C[0] - 62, 175, DRAPE_R[0], DRAPE_R[1], fill=C("DARK"))         # 左侧垂布
    _e(d, HOOD_C[0] + 62, 175, DRAPE_R[0], DRAPE_R[1], fill=C("DARK"))         # 右侧垂布
    if not solid:
        d.arc(_bbox(HOOD_C[0], HOOD_C[1], HOOD_R[0] - 7, HOOD_R[1] - 7),
              150, 262, fill=C("DARK_HI"), width=int(8 * SS))                  # 顶部高光
        d.arc(_bbox(HOOD_C[0], HOOD_C[1], HOOD_R[0] - 4, HOOD_R[1] - 4),
              30, 150, fill=C("DARK_LO"), width=int(5 * SS))                   # 帽檐阴影
        _fake_eyes(d, C)
        _beak(d, p, C)
    _e(d, FACE_C[0], FACE_C[1], FACE_R[0], FACE_R[1], fill=C("SKIN"))          # 脸
    if not solid:
        _face(img, d, p, C)
    _hair(d, C, solid)
    if not solid:
        _line(d, [(104, 150), (99, 212)], 2.2, fill=C("HAIR_HI"))              # 发丝高光
        _line(d, [(216, 150), (221, 212)], 2.2, fill=C("HAIR_HI"))
        _pin(d)


def _fake_eyes(d, C):
    for (cx, cy), tilt in ((FAKE_L, -FAKE_TILT), (FAKE_R, FAKE_TILT)):
        _rell(d, cx, cy, FAKE_RAD[0] + 2.5, FAKE_RAD[1] + 2.5, tilt, fill=C("OUTLINE_C"))
        _rell(d, cx, cy, FAKE_RAD[0], FAKE_RAD[1], tilt, fill=C("WHITE"))
        px = cx + (5.0 if cx < CX else -5.0)                                   # 瞳仁内偏下望喙
        _e(d, px, cy + 5.5, 5.8, 5.8, fill=C("PUPIL"))
        _e(d, px - 1.9, cy + 3.6, 1.7, 1.7, fill=C("WHITE"))


def _beak(d, p, C):
    g = p["beak_open"] * 10.0
    up = [(CX - BEAK_HW, BEAK_TOP - g * 0.45), (CX + BEAK_HW, BEAK_TOP - g * 0.45),
          (CX, BEAK_TIP - g * 0.45)]
    cen = (CX, (BEAK_TOP + BEAK_TIP) / 2)
    if g > 1.5:
        _poly(d, [(CX - 13, BEAK_TOP + 13), (CX + 13, BEAK_TOP + 13),
                  (CX, BEAK_TIP + g * 0.5)], fill=C("MOUTH_C2"))               # 口腔
        low = [(CX - 13, BEAK_TOP + 19 + g * 0.55), (CX + 13, BEAK_TOP + 19 + g * 0.55),
               (CX, BEAK_TIP + 8 + g * 0.8)]
        _rtri(d, low[0], low[1], low[2], 7.0, fill=C("OUTLINE_C"))
        _rtri(d, low[0], low[1], low[2], 5.0, fill=C("BEAK_LO"))
    up_o = [(cen[0] + (x - cen[0]) * 1.10, cen[1] + (y - cen[1]) * 1.10) for x, y in up]
    _rtri(d, up_o[0], up_o[1], up_o[2], 9.0, fill=C("OUTLINE_C"))
    _rtri(d, up[0], up[1], up[2], 8.0, fill=C("BEAK"))
    _poly(d, [(CX - 20, BEAK_TOP + 20 - g * 0.45), (CX + 20, BEAK_TOP + 20 - g * 0.45),
              (CX + 9, BEAK_TIP - 3 - g * 0.45), (CX - 9, BEAK_TIP - 3 - g * 0.45)],
          fill=C("BEAK_LO"))                                                   # 喙下半渐变


def _face(img, d, p, C):
    blush = Image.new("RGBA", (SZ, SZ), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush)
    a = int(235 * p["blush"])
    for bx in (BLUSH_L[0], BLUSH_R[0]):
        _e(bd, bx, BLUSH_L[1], BLUSH_RAD[0], BLUSH_RAD[1],
           fill=(BLUSH_C[0], BLUSH_C[1], BLUSH_C[2], a))
    fm = Image.new("L", (SZ, SZ), 0)
    _e(ImageDraw.Draw(fm), FACE_C[0], FACE_C[1], FACE_R[0] - 2, FACE_R[1] - 2, fill=255)
    blush.putalpha(ImageChops.multiply(blush.split()[3], fm))
    img.alpha_composite(blush)
    _eyes(d, p["eye"], C)
    _mouth(d, p["mouth"], C)


def _eyes(d, mode, C):
    for cx, cy in (EYE_L, EYE_R):
        rx, ry = EYE_RAD
        if mode == "happy":                                                    # 眯眼 ^^
            d.arc(_bbox(cx, cy, rx - 0.5, ry - 5.5), 180, 360,
                  fill=C("OUTLINE_C"), width=int(4.5 * SS))
            continue
        if mode == "closed":                                                   # 安睡下垂弧
            d.arc(_bbox(cx, cy + 2, rx - 2.5, ry - 5), 15, 165,
                  fill=C("OUTLINE_C"), width=int(3.5 * SS))
            continue
        if mode == "blink":                                                    # 眨眼
            _e(d, cx, cy, rx + 1, ry + 1, fill=C("SKIN"))
            d.arc(_bbox(cx, cy + 1, rx - 2, ry - 5), 10, 170,
                  fill=C("OUTLINE_C"), width=int(3.5 * SS))
            continue
        if mode == "surprised":                                                # 瞳孔缩小
            _e(d, cx, cy, rx + 1.5, ry + 2.5, fill=C("EYE_WHITE"))
            _e(d, cx, cy + 1, 8.5, 9.0, fill=C("IRIS"))
            _e(d, cx, cy + 2, 4.2, 4.6, fill=C("PUPIL"))
            _e(d, cx - 2.6, cy - 1.6, 2.4, 2.4, fill=C("WHITE"))
            _e(d, cx, cy, rx + 1.5, ry + 2.5, outline=C("OUTLINE_C"), width=int(1.8 * SS))
            continue
        _e(d, cx, cy, rx, ry, fill=C("IRIS"))                                  # 睁眼
        d.pieslice(_bbox(cx, cy, rx, ry), 25, 155, fill=C("IRIS_HI"))
        d.pieslice(_bbox(cx, cy, rx, ry), 180, 360, fill=C("IRIS_LO"))
        _e(d, cx, cy + 2.5, 5.5, 6.5, fill=C("PUPIL"))
        _e(d, cx - 5, cy - 5.5, 5, 5, fill=C("WHITE"))
        _e(d, cx + 5, cy + 6.5, 2.4, 2.4, fill=C("WHITE"))
        _e(d, cx, cy, rx, ry, outline=C("OUTLINE_C"), width=int(1.6 * SS))
        d.arc(_bbox(cx, cy, rx + 0.5, ry + 0.5), 195, 345,
              fill=C("OUTLINE_C"), width=int(3.4 * SS))                        # 上睫毛


def _mouth(d, mode, C):
    cx, cy = MOUTH_C
    if mode == "smile_open":
        d.pieslice(_bbox(cx, cy, 12.5, 11.5, 1.6), 0, 180, fill=C("OUTLINE_C"))
        d.pieslice(_bbox(cx, cy, 11, 10, 0), 0, 180, fill=C("MOUTH_C2"))
        _poly(d, [(cx - 8.5, cy + 0.6), (cx + 8.5, cy + 0.6),
                  (cx + 6.5, cy + 3.8), (cx - 6.5, cy + 3.8)], fill=C("WHITE"))    # 牙齿
        d.pieslice(_bbox(cx, cy + 3.4, 6.8, 8.9), 0, 180, fill=C("TONGUE"))
    elif mode == "open_wide":
        _e(d, cx, cy + 3.5, 12, 11.5, fill=C("OUTLINE_C"))
        _e(d, cx, cy + 3.5, 10.5, 10, fill=C("MOUTH_C2"))
        _poly(d, [(cx - 7.5, cy - 4.4), (cx + 7.5, cy - 4.4),
                  (cx + 6, cy - 1.6), (cx - 6, cy - 1.6)], fill=C("WHITE"))        # 牙齿
        d.pieslice(_bbox(cx, cy + 7.5, 5.5, 6.8), 0, 180, fill=C("TONGUE"))
    elif mode == "o":
        _e(d, cx, cy + 2, 5.5, 6.5, fill=C("OUTLINE_C"))
        _e(d, cx, cy + 2, 4.3, 5.3, fill=C("MOUTH_C2"))
    else:                                                                      # smile_small
        d.arc(_bbox(cx, cy - 3, 8.5, 8.5), 20, 160, fill=C("OUTLINE_C"), width=int(2.6 * SS))


def _hair(d, C, solid):
    """侧发 + 齐刘海（盖住帽檐下沿与脸的上缘）。"""
    for lx, s in ((105, -1), (215, 1)):
        _e(d, lx, 150, 12.5, 20, fill=C("HAIR"))
        _e(d, lx - 3 * s, 184, 11, 22, fill=C("HAIR"))
        _e(d, lx - 5 * s, 216, 10, 18, fill=C("HAIR"))
        _e(d, lx - 7 * s, 234, 7, 7, fill=C("HAIR"))
    _e(d, CX, 143, 58, 22, fill=C("HAIR"))                                     # 刘海主体
    for bx, by in ((115, 157), (134, 160), (153, 157.5), (172, 160), (191, 157), (206, 152)):
        _e(d, bx, by, 9, 9, fill=C("HAIR"))                                    # 圆齿发梢
    if not solid:
        d.arc(_bbox(CX, 142, 49, 16), 195, 250, fill=C("HAIR_HI"), width=int(2.5 * SS))


def _pin(d):
    """左侧黑色十字发夹。"""
    x, y = 106.0, 162.0
    _line(d, [(x - 13, y + 6.5), (x + 13, y - 6.5)], 5.2, fill=PIN)
    _line(d, [(x - 6.5, y - 11), (x + 6.5, y + 11)], 5.2, fill=PIN)
    for ex, ey in ((x - 13, y + 6.5), (x + 13, y - 6.5), (x - 6.5, y - 11), (x + 6.5, y + 11)):
        _e(d, ex, ey, 2.6, 2.6, fill=PIN)
    _line(d, [(x - 10.5, y + 4.4), (x + 10.5, y - 6.4)], 1.3, fill=(155, 153, 168, 255))


# ---------------- 气泡 / Zzz（不参与剪影描边） ----------------
def _font(size):
    size = int(size)
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype(FONT_PATH, size)
        except Exception:
            _FONT_CACHE[size] = None
    return _FONT_CACHE[size]


def _draw_bubble(d, p):
    x0, y0, x1, y1 = 176.0, 10.0, 300.0, 62.0
    tail = [(206.0, 56.0), (186.0, 86.0), (230.0, 58.0)]
    tc = (sum(q[0] for q in tail) / 3, sum(q[1] for q in tail) / 3)
    _poly(d, [(x + (x - tc[0]) * 0.4, y + (y - tc[1]) * 0.4) for x, y in tail], fill=OUTLINE_C)
    d.rounded_rectangle([(x0 - 3) * SS, (y0 - 3) * SS, (x1 + 3) * SS, (y1 + 3) * SS],
                        radius=18 * SS, fill=OUTLINE_C)
    _poly(d, tail, fill=WHITE)
    d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=15 * SS, fill=WHITE)
    txt = str(p["bubble"])
    fs = min(19.0, (x1 - x0 - 20) / max(1, len(txt)) / 0.95) * SS              # 自适应字号
    font = _font(fs)
    if font is not None:
        w = font.getlength(txt)
        if w > (x1 - x0 - 16) * SS:                                            # 兜底再缩
            font = _font(max(24, fs * (x1 - x0 - 16) * SS / w))
        d.text(((x0 + x1) / 2 * SS, (y0 + y1) / 2 * SS + SS), txt,
               font=font, fill=INK, anchor="mm")
    else:                                                                      # 回退：手绘音符
        for nx in (x0 + 30, x0 + 72):
            _e(d, nx, y0 + 34, 5.5, 4.4, fill=INK)
            _line(d, [(nx + 4.5, y0 + 33), (nx + 4.5, y0 + 12)], 2.6, fill=INK)
            _line(d, [(nx + 4.5, y0 + 12), (nx + 13, y0 + 16.5)], 2.6, fill=INK)


def _draw_zzz(d):
    specs = ((230, 110, 64), (255, 82, 82), (284, 50, 100))                    # x, y, 字号(SS)
    if _font(64) is not None:
        for x, y, s in specs:
            d.text((x * SS, y * SS), "Z", font=_font(s), fill=ZZZ_C, anchor="mm",
                   stroke_width=max(1, s // 12), stroke_fill=WHITE)
    else:
        for x, y, s in specs:
            h = s / SS / 2.4
            w = h * 0.95
            lw = max(1.0, h / 3.0)
            _line(d, [(x - w, y - h), (x + w, y - h)], lw, fill=ZZZ_C)
            _line(d, [(x + w, y - h), (x - w, y + h)], lw, fill=ZZZ_C)
            _line(d, [(x - w, y + h), (x + w, y + h)], lw, fill=ZZZ_C)


# ---------------- 托盘图标：兜帽头部特写 ----------------
def draw_tray(size=64) -> Image.Image:
    img = draw_frame({"blush": 0.6})
    head = img.crop((int(74), int(16), int(246), int(206)))                    # 兜帽头部特写
    scale = (size - 6) / max(head.size)
    head = head.resize((max(1, int(head.width * scale)), max(1, int(head.height * scale))),
                       Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(head, ((size - head.width) // 2, (size - head.height) // 2))
    return out


if __name__ == "__main__":
    import os
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "tools_out"), exist_ok=True)
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "tools_out", "dev_single.png")
    draw_frame().save(dst)
    print("saved:", dst)
