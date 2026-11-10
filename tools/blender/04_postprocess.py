# -*- coding: utf-8 -*-
"""精灵帧后处理：quack 帧合成「咕咕嘎嘎!」气泡、sleep 帧合成 Zzz，
并生成 sprites3d 预览拼图 + 基线检查。

直接复用 tools/character_art.py 的绘制函数（SS=1 即 320 坐标系一次成型）。
运行：.venv/Scripts/python.exe tools/blender/04_postprocess.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from PIL import Image, ImageDraw

import character_art as ca

ca.SS = 1                       # 直接在 320 坐标系绘制
ca._FONT_CACHE.clear()

SRC = os.path.join(ROOT, "sprites3d")
OUT_SHEET = os.path.join(ROOT, "tools_out", "preview_3d.png")


def overlay(path, kind):
    img = Image.open(path).convert("RGBA")
    d = ImageDraw.Draw(img)
    if kind == "bubble":
        ca._draw_bubble(d, {"bubble": "咕咕嘎嘎!"})
    elif kind == "zzz":
        ca._draw_zzz(d)
    img.save(path)


def main():
    pat = re.compile(r"^(.+)_\d{2}\.png$")
    groups = {}
    for f in sorted(os.listdir(SRC)):
        m = pat.match(f)
        if m:
            groups.setdefault(m.group(1), []).append(f)

    n_overlaid = 0
    for f in groups.get("quack", []):
        overlay(os.path.join(SRC, f), "bubble")
        n_overlaid += 1
    for f in groups.get("sleep", []):
        overlay(os.path.join(SRC, f), "zzz")
        n_overlaid += 1
    print(f"[ok] overlays: {n_overlaid} 帧（quack 气泡 + sleep Zzz）")

    # 基线检查：每帧 alpha 实体最下缘应 ≈ 312±3（透明底判定）
    bad = []
    for f in sorted(groups.get("idle", []))[:1] + sorted(groups.get("walk_side", []))[:1]:
        img = Image.open(os.path.join(SRC, f)).convert("RGBA")
        solid = img.getchannel("A").point(lambda a: 255 if a > 127 else 0)
        bbox = solid.getbbox()
        base = (bbox[3] - 1) if bbox else -1
        print(f"[check] {f}: baseline y={base} (target 312±3)")
        if abs(base - 312) > 3:
            bad.append((f, base))
    if bad:
        print("[WARN] 基线超差：", bad)

    # 预览拼图
    ROW_ORDER = ["idle", "walk", "walk_side", "drag", "jump", "happy", "quack",
                 "surprised", "sleep"]
    names = [n for n in ROW_ORDER if n in groups] + [n for n in sorted(groups) if n not in ROW_ORDER]
    CELL, LABEL_H, FRAME = 168, 24, 150
    cols = max(len(v) for v in groups.values())
    sheet = Image.new("RGBA", (cols * CELL + 32, len(names) * (CELL + LABEL_H) + 60),
                      (245, 245, 248, 255))
    d = ImageDraw.Draw(sheet)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
    except Exception:
        font = ImageFont.load_default()
    for r, name in enumerate(names):
        y0 = 44 + r * (CELL + LABEL_H)
        d.text((16, y0 + 2), name, font=font, fill=(90, 85, 100, 255))
        for c, f in enumerate(sorted(groups[name])):
            x0 = 16 + c * CELL
            fr = Image.open(os.path.join(SRC, f)).convert("RGBA").resize((FRAME, FRAME), Image.LANCZOS)
            sheet.alpha_composite(fr, (x0 + 3, y0 + 22))
            d.text((x0 + 3, y0 + FRAME + 24), f[:-4], font=font, fill=(70, 65, 82, 255))
    sheet.convert("RGB").save(OUT_SHEET)
    print(f"[ok] sheet -> {OUT_SHEET}")


if __name__ == "__main__":
    main()
