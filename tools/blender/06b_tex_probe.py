# -*- coding: utf-8 -*-
"""右眼 UV 定位探针：导出疑似右眼 UV 位置的贴图裁片，目视确认。"""
import os

import bpy
import numpy as np

ROOT = r"E:\qbb\github\qdesktop_pet"
TEX = os.path.join(ROOT, "model", "basecolor_extract.png")
OUT = os.path.join(ROOT, "tools_out")

img = bpy.data.images.load(TEX)
img.colorspace_settings.name = "Non-Color"
W, H = img.size
buf = np.empty(W * H * 4, dtype=np.float32)
img.pixels.foreach_get(buf)
topdown = buf.reshape(H, W, 4)[::-1]

# 候选：eyeL 裁片顶部出现的"半只眼"(2573,1687)；另存一张眼部邻域全景
CANDS = {"r_candidate": (2573, 1687, 420), "context": (2400, 2000, 900)}
for name, (cx, cy, r) in CANDS.items():
    crop = topdown[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
    ch, cw = crop.shape[:2]
    cimg = bpy.data.images.new(f"probe_{name}", cw, ch, alpha=True)
    cimg.colorspace_settings.name = "Non-Color"
    cimg.pixels.foreach_set(crop[::-1].reshape(-1).astype(np.float32))
    p = os.path.join(OUT, f"tex_probe_{name}.png")
    cimg.filepath_raw = p
    cimg.file_format = "PNG"
    cimg.save()
    print("PROBE_SAVED", p)
print("TEX_PROBE_DONE")
