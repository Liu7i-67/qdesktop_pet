# -*- coding: utf-8 -*-
"""咕咕嘎嘎桌面宠物 - 精灵图预览拼图（WP1）。

把 sprites/ 全部帧按动画分行拼成带标注网格图 tools_out/preview.png，
每格标注「动画名_帧号」，供人工质检形象与动画。
运行：.venv/Scripts/python.exe tools/make_preview.py
"""
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITES_DIR = os.path.join(ROOT, "sprites")
OUT_PATH = os.path.join(ROOT, "tools_out", "preview.png")

ROW_ORDER = ["idle", "walk", "drag", "jump", "happy", "quack", "surprised", "sleep"]
CELL = 168          # 单元格（帧缩放 150 + 边距）
LABEL_H = 26
FRAME = 150
FONT_PATH = "C:/Windows/Fonts/msyh.ttc"


def _font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def main():
    groups = {}
    pat = re.compile(r"^(.+)_(\d{2})\.png$")
    for f in sorted(os.listdir(SPRITES_DIR)):
        m = pat.match(f)
        if not m:
            continue
        groups.setdefault(m.group(1), []).append((int(m.group(2)), f))
    if not groups:
        print("sprites/ 下没有帧文件，请先运行 generate_sprites.py")
        return

    names = [n for n in ROW_ORDER if n in groups]
    names += [n for n in sorted(groups) if n not in names]
    cols = max(len(v) for v in groups.values())
    rows = len(names)
    width = cols * CELL + 2 * 16
    height = rows * (CELL + LABEL_H) + 16 + 44
    sheet = Image.new("RGBA", (width, height), (245, 245, 248, 255))
    d = ImageDraw.Draw(sheet)
    title = _font(22)
    d.text((16, 8), "咕咕嘎嘎 sprites 预览  (320x320 RGBA / 站立基线 y=312 / 面朝右)",
           font=title, fill=(60, 55, 70, 255))
    label_font = _font(15)

    for r, name in enumerate(names):
        y0 = 44 + r * (CELL + LABEL_H)
        d.text((16, y0 + 2), name, font=label_font, fill=(90, 85, 100, 255))
        for c, (idx, fname) in enumerate(sorted(groups[name])):
            x0 = 16 + c * CELL
            cell_x, cell_y = x0, y0 + 22
            # 棋盘格底衬托透明区域
            for yy in range(0, CELL - 12, 14):
                for xx in range(0, CELL - 12, 14):
                    shade = (228, 228, 234, 255) if (xx // 14 + yy // 14) % 2 else (244, 244, 248, 255)
                    d.rectangle([cell_x + xx, cell_y + yy, cell_x + xx + 13, cell_y + yy + 13],
                                fill=shade)
            frame = Image.open(os.path.join(SPRITES_DIR, fname)).convert("RGBA")
            frame = frame.resize((FRAME, FRAME), Image.LANCZOS)
            sheet.alpha_composite(frame, (cell_x + 3, cell_y + 3))
            d.text((cell_x + 3, cell_y + FRAME + 4), f"{name}_{idx:02d}",
                   font=label_font, fill=(70, 65, 82, 255))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    sheet.convert("RGB").save(OUT_PATH)
    print(f"[ok] {len(sum(groups.values(), []))} 帧 -> {OUT_PATH}")


if __name__ == "__main__":
    main()
