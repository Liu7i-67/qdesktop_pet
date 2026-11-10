# -*- coding: utf-8 -*-
"""精灵帧渲染管线：按 app 动画契约渲染 40 帧 320x320 RGBA 到 sprites3d/。

静态网格（无骨骼）驱动方式 = 相机视角（正面/右侧）+ 整体变换（位移/旋转/缩放），
缩放与位移以脚底 z=0 为基准（趴地不飘）。quack 气泡与 sleep Zzz 由
tools/blender/04_postprocess.py 以 PIL 合成（与原绘制版同位置同风格）。

运行：
  blender.exe --background --factory-startup --python-exit-code 1 \
      --python tools/blender/03_render_sprites.py
产出：sprites3d/{anim}_{i:02d}.png（未合成气泡/Zzz，除 quack/sleep 后处理补齐）
"""
import math
import os

import bpy
from mathutils import Vector

ROOT = r"E:\qbb\github\qdesktop_pet"
BLEND = os.path.join(ROOT, "model", "gugugaga.blend")
OUT = os.path.join(ROOT, "sprites3d")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
mesh = bpy.data.objects["node_0"]

# ---------------- 调色：降明度/提饱和，贴近原素材炭黑色调 ----------------
# 注意：Blender HSV 在线性空间计算；0.40 线性 ≈ sRGB 0.66，与 2D 试验 strong 档一致
mat = mesh.data.materials[0]
nt = mat.node_tree
hsv = nt.nodes.new("ShaderNodeHueSaturation")
hsv.inputs["Saturation"].default_value = 1.25
hsv.inputs["Value"].default_value = 0.40
base_link = next((l for l in nt.links
                  if l.to_node.type == "BSDF_PRINCIPLED"
                  and l.to_socket.name == "Base Color"), None)
if base_link is not None:
    src_socket = base_link.from_socket
    nt.links.new(src_socket, hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], base_link.to_socket)

# ---------------- 渲染设置：320 透明底 ----------------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 40
scene.cycles.use_denoising = True
scene.render.resolution_x = 320
scene.render.resolution_y = 320
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True

# 取现有相机/灯光（02 脚本建立），帧高按契约重排：
# 脚底基线 y=312px、头顶 14px → 正交帧高 f=1.1844m，相机 z=0.5625
FRAME_H = 1.1844
CAM_Z = 0.975 * FRAME_H - FRAME_H / 2.0


def clear_cameras():
    for o in list(scene.collection.objects):
        if o.type == "CAMERA":
            bpy.data.objects.remove(o, do_unlink=True)


clear_cameras()
cam_data = bpy.data.cameras.new("SpriteCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = FRAME_H
cam = bpy.data.objects.new("SpriteCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def set_cam(view):
    """view: 'front'（面朝镜头 -Y）| 'side'（右向侧面，角色朝画面右）。"""
    if view == "front":
        cam.location = (0.0, -3.0, CAM_Z)
        cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    else:  # 相机在 -X 看 +X（欧拉 90,0,-90），屏幕右 = 角色面部方向 → 面朝右
        cam.location = (-3.0, 0.0, CAM_Z)
        cam.rotation_euler = (math.radians(90), 0.0, math.radians(-90))


def pose(state, frame_i):
    """按 (state, 帧号) 返回 (dz, rot_deg(x,y,z), scale(x,y,z))。"""
    p = 2 * math.pi * frame_i / 8.0
    if state == "idle":
        n = 4
        return ([0.0, 0.03, 0.015, 0.0][frame_i % n], (0, 0, 0), (1, 1, 1))
    if state == "walk":
        bob = [0.0, -0.03, -0.045, -0.03, 0.0, -0.03, -0.045, -0.03][frame_i % 8]
        roll = 4.0 * math.sin(p)          # 左右摇摆（企鹅步）
        return (bob, (0.0, 0.0, roll), (1, 1, 1))
    if state == "walk_side":
        bob = -0.035 * abs(math.sin(p))   # 两拍起伏
        lean = 1.6 * math.sin(p)
        return (bob, (lean, 0.0, 0.0), (1, 1, 1))
    if state == "drag":
        rock = 7.0 * (1.0 if frame_i % 2 == 0 else -1.0)
        return (0.10, (-8.0, 0.0, rock), (1, 1, 1))
    if state == "jump":
        specs = {
            0: (0.0, 0.0, (1.07, 1.07, 0.86)),    # 蹲
            1: (0.10, 0.0, (0.97, 0.97, 1.06)),   # 起跳
            2: (0.13, 0.0, (0.99, 0.99, 1.02)),   # 最高（头顶留 6% 边距，对齐原版）
            3: (0.09, 0.0, (1.0, 1.0, 1.0)),      # 下落
            4: (0.0, 0.0, (1.08, 1.08, 0.84)),    # 落地压扁
            5: (0.01, 0.0, (1.02, 1.02, 0.96)),   # 回弹
        }
        dz, _, sc = specs[frame_i % 6]
        return (dz, (0.0, 0.0, 0.0), sc)
    if state == "happy":
        rock = [10.0, -10.0, 10.0, 4.0][frame_i % 4]
        dz = [-0.03, -0.03, -0.02, 0.0][frame_i % 4]
        return (dz, (0.0, 0.0, rock), (1, 1, 1))
    if state == "quack":
        # 原契约：跳跃由控制器窗口抛物线完成，帧内只做小幅呼吸/张喙起伏
        dz = [0.0, 0.015, 0.028, 0.008][frame_i % 4]
        return (dz, (0.0, 0.0, 0.0), (1, 1, 1))
    if state == "surprised":
        rock = [-3.0, 3.0][frame_i % 2]
        return (0.0, (0.0, 0.0, rock), (1, 1, 1))
    if state == "sleep":
        tilt = [5.0, 6.5][frame_i % 2]
        dz = [0.0, -0.02][frame_i % 2]
        return (dz, (0.0, 0.0, tilt), (1, 1, 1))
    raise ValueError(state)


CONTRACT = {
    "idle": ("front", 4),
    "walk": ("front", 8),
    "walk_side": ("side", 8),
    "drag": ("front", 2),
    "jump": ("front", 6),
    "happy": ("front", 4),
    "quack": ("front", 4),
    "surprised": ("front", 2),
    "sleep": ("front", 2),
}

for state, (view, count) in CONTRACT.items():
    set_cam(view)
    for i in range(count):
        dz, rot, sc = pose(state, i)
        mesh.location = (0.0, 0.0, dz)
        mesh.rotation_mode = "XYZ"
        mesh.rotation_euler = tuple(math.radians(a) for a in rot)
        mesh.scale = sc
        scene.render.filepath = os.path.join(OUT, f"{state}_{i:02d}.png")
        bpy.ops.render.render(write_still=True)
    print("RENDERED", state, count)

# 还原中性姿态再保存项目
mesh.location = (0.0, 0.0, 0.0)
mesh.scale = (1.0, 1.0, 1.0)
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print("SPRITES_DONE")
