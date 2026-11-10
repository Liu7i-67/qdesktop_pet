# -*- coding: utf-8 -*-
"""渲染 3D 版托盘图标：头部特写 → 64x64 assets/tray.png。

运行：
  blender.exe --background --factory-startup --python-exit-code 1 \
      --python tools/blender/05_render_tray.py
"""
import math
import os

import bpy
from mathutils import Vector

ROOT = r"E:\qbb\github\qdesktop_pet"
BLEND = os.path.join(ROOT, "model", "gugugaga.blend")
OUT = os.path.join(ROOT, "tools_out", "tray_3d_256.png")

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene

# 头部占据 z≈0.42..1.10、x≈±0.33 → 正交特写（正面略偏上）
cam_data = bpy.data.cameras.new("TrayCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 0.82
cam = bpy.data.objects.new("TrayCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (0.0, -3.0, 0.72)
cam.rotation_euler = (math.radians(90), 0.0, 0.0)

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.render.resolution_x = 256
scene.render.resolution_y = 256
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("TRAY_RENDER_DONE", OUT)
