# -*- coding: utf-8 -*-
"""绑定版精灵渲染：骨骼驱动步态/挥鳍/点头 + 表情贴图变体 + 形态键张喙。

按动画契约渲染 40 帧 320x320 RGBA 到 sprites3d/（覆盖）：
- idle: 呼吸 + 眨眼（帧 3，blink 贴图）
- walk: 正面企鹅步（腿交替 + 侧滚 + 鳍翼摆）
- walk_side: 侧视图行走（腿大幅交替 + 两拍起伏 + 前倾）——左向由运行时镜像
- drag: 双鳍上举扑腾 + 倾斜摇摆
- jump: 蹲-腾空-落地压扁-回弹（整体缩放以脚底为轴）
- happy: 眯眼（happy 贴图）+ 鳍翼上举挥舞 + 左右摇摆
- quack: beak_open 形态键张喙 + 气泡由后处理合成
- surprised: 抬头张望 + 颤动
- sleep: 闭眼（blink 贴图）+ 歪头 + Zzz 后处理

运行：
  blender.exe --background --factory-startup --python-exit-code 1 \
      --python tools/blender/07_render_sprites_rigged.py
"""
import math
import os

import bpy
from mathutils import Vector

ROOT = r"E:\qbb\github\qdesktop_pet"
BLEND = os.path.join(ROOT, "model", "gugugaga_rigged.blend")
MODEL_DIR = os.path.join(ROOT, "model")
OUT = os.path.join(ROOT, "sprites3d")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
mesh = bpy.data.objects["node_0"]
arm = bpy.data.objects["Armature"]
nt = mesh.data.materials[0].node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
sock = bsdf.inputs["Base Color"]
tex_node, seen = None, set()
while sock.is_linked and sock.links[0].from_node not in seen:
    node = sock.links[0].from_node
    seen.add(node)
    if node.type == "TEX_IMAGE":
        tex_node = node
        break
    linked = [i for i in node.inputs if i.is_linked]
    sock = linked[0] if linked else None
assert tex_node is not None, "未找到基础色贴图节点"
hsv = next(n for n in nt.nodes if n.type == "HUE_SAT")
sk = mesh.data.shape_keys.key_blocks["beak_open"]

base_img = tex_node.image
var_imgs = {}
for tag in ("blink", "happy"):
    p = os.path.join(MODEL_DIR, f"face_{tag}.png")
    if os.path.exists(p):
        im = bpy.data.images.load(p, check_existing=True)
        im.colorspace_settings.name = "sRGB"
        var_imgs[tag] = im

# ---------------- 渲染设置（契约帧） ----------------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 40
scene.cycles.use_denoising = True
scene.render.resolution_x = 320
scene.render.resolution_y = 320
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True

FRAME_H = 1.1844
CAM_Z = 0.975 * FRAME_H - FRAME_H / 2.0

for o in list(scene.collection.objects):
    if o.type == "CAMERA":
        bpy.data.objects.remove(o, do_unlink=True)
cam_data = bpy.data.cameras.new("SpriteCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = FRAME_H
cam = bpy.data.objects.new("SpriteCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def set_cam(view):
    if view == "front":
        cam.location = (0.0, -3.0, CAM_Z)
        cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    else:
        cam.location = (-3.0, 0.0, CAM_Z)
        cam.rotation_euler = (math.radians(90), 0.0, math.radians(-90))


def reset():
    for pb in arm.pose.bones:
        pb.rotation_euler = (0.0, 0.0, 0.0)
    tex_node.image = base_img
    sk.value = 0.0
    mesh.location = (0.0, 0.0, 0.0)
    mesh.rotation_euler = (0.0, 0.0, 0.0)
    mesh.scale = (1.0, 1.0, 1.0)


def set_bones(**angles):
    """按骨骼名设置欧拉角（度）。flipper X 轴=抬起（L 正 R 负）。"""
    for name, (rx, ry, rz) in angles.items():
        if name in arm.pose.bones:
            arm.pose.bones[name].rotation_euler = tuple(
                math.radians(a) for a in (rx, ry, rz))


def render_frame(state, i):
    p = 2 * math.pi * i / 8.0
    reset()
    view = "front"
    if state == "idle":
        mesh.location.z = [0.0, 0.03, 0.015, 0.0][i % 4]
        if i % 4 == 3:
            tex_node.image = var_imgs["blink"]
    elif state == "walk":
        mesh.location.z = [0.0, -0.03, -0.045, -0.03, 0.0, -0.03, -0.045, -0.03][i % 8]
        mesh.rotation_euler = (0.0, 0.0, math.radians(5.0 * math.sin(p)))
        set_bones(**{"leg.L": (14 * math.sin(p), 0, 0),
                     "leg.R": (-14 * math.sin(p), 0, 0),
                     "flipper.L": (10 * math.sin(p), 0, 0),
                     "flipper.R": (-10 * math.sin(p), 0, 0)})
    elif state == "walk_side":
        view = "side"
        mesh.location.z = -0.035 * abs(math.sin(p))
        mesh.rotation_euler = (math.radians(1.6 * math.sin(p)), 0.0, 0.0)
        set_bones(**{"leg.L": (30 * math.sin(p), 0, 0),
                     "leg.R": (-30 * math.sin(p), 0, 0),
                     "flipper.L": (12 * math.sin(p), 0, 0),
                     "flipper.R": (-12 * math.sin(p), 0, 0)})
    elif state == "drag":
        rock = 7.0 if i % 2 == 0 else -7.0
        mesh.rotation_euler = (math.radians(-8.0), 0.0, math.radians(rock))
        mesh.location.z = 0.10
        set_bones(**{"flipper.L": (115.0, 0, 0), "flipper.R": (-115.0, 0, 0)})
    elif state == "jump":
        specs = {0: (0.0, (1.07, 1.07, 0.86)), 1: (0.10, (0.97, 0.97, 1.06)),
                 2: (0.13, (0.99, 0.99, 1.02)), 3: (0.09, (1.0, 1.0, 1.0)),
                 4: (0.0, (1.08, 1.08, 0.84)), 5: (0.01, (1.02, 1.02, 0.96))}
        dz, sc = specs[i % 6]
        mesh.location.z = dz
        mesh.scale = sc
        if i % 6 in (1, 2, 3):
            set_bones(**{"leg.L": (-35.0, 0, 0), "leg.R": (-35.0, 0, 0)})
    elif state == "happy":
        tex_node.image = var_imgs["happy"]
        rock = [10.0, -10.0, 10.0, 4.0][i % 4]
        mesh.location.z = [-0.03, -0.03, -0.02, 0.0][i % 4]
        mesh.rotation_euler = (0.0, 0.0, math.radians(rock))
        up = 70.0 if i % 2 == 0 else 25.0
        set_bones(**{"flipper.L": (up, 0, 0), "flipper.R": (-up, 0, 0)})
    elif state == "quack":
        mesh.location.z = [0.0, 0.015, 0.028, 0.008][i % 4]
        sk.value = [1.4, 0.5, 1.4, 0.3][i % 4]
    elif state == "surprised":
        rock = [-2.5, 2.5][i % 2]
        mesh.rotation_euler = (math.radians(-6.0), 0.0, math.radians(rock))
        set_bones(**{"head": (8.0, 0, 0)})
    elif state == "sleep":
        tex_node.image = var_imgs["blink"]
        tilt = [5.0, 6.5][i % 2]
        mesh.location.z = [0.0, -0.02][i % 2]
        mesh.rotation_euler = (0.0, 0.0, math.radians(tilt))
        set_bones(**{"head": (12.0, 0, tilt)})
    else:
        raise ValueError(state)
    set_cam(view)
    scene.render.filepath = os.path.join(OUT, f"{state}_{i:02d}.png")
    bpy.ops.render.render(write_still=True)


CONTRACT = {"idle": 4, "walk": 8, "walk_side": 8, "drag": 2, "jump": 6,
            "happy": 4, "quack": 4, "surprised": 2, "sleep": 2}
for state, count in CONTRACT.items():
    for i in range(count):
        render_frame(state, i)
    print("RENDERED", state, count)

reset()
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print("SPRITES_DONE")
