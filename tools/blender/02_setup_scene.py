# -*- coding: utf-8 -*-
"""场景搭建 v1：修材质（金属度/色彩空间）→ 摆正朝向 → 居中落地 → 灯光 → 预览渲染。

运行：
  blender.exe --background --factory-startup --python-exit-code 1 \
      --python tools/blender/02_setup_scene.py
产出：
  - model/gugugaga.blend                摆正后的主项目
  - tools_out/model_setup_front.png     正面预览（透明底 RGBA）
  - tools_out/model_setup_side.png      右侧预览
  - tools_out/model_setup_persp.png     45° 透视预览
"""
import math
import os

import bpy
from mathutils import Vector

ROOT = r"E:\qbb\github\qdesktop_pet"
BLEND_IN = os.path.join(ROOT, "model", "gugugaga.blend")
BLEND_OUT = os.path.join(ROOT, "model", "gugugaga.blend")
OUT = os.path.join(ROOT, "tools_out")

bpy.ops.wm.open_mainfile(filepath=BLEND_IN)
scene = bpy.context.scene
mesh = bpy.data.objects["node_0"]

# ---------------- 1. 修材质：金属度置 0（镜面隐形元凶）、ORM/法线 Non-Color ----------------
mat = mesh.data.materials[0]
nt = mat.node_tree
for n in nt.nodes:
    if n.type == "TEX_IMAGE" and n.image:
        name = (n.image.name or "").lower()
        cs = n.image.colorspace_settings
        if "metallic" in name or "roughness" in name or "_orm" in name:
            cs.name = "Non-Color"
        if "normal" in name:
            cs.name = "Non-Color"
        # 主色贴图保持 sRGB
for link in list(nt.links):
    if link.to_node.type == "BSDF_PRINCIPLED" and link.to_socket.name == "Metallic":
        nt.links.remove(link)
for n in nt.nodes:
    if n.type == "BSDF_PRINCIPLED":
        n.inputs["Metallic"].default_value = 0.0
        # AI 生成贴图的粗糙度通道若过白/过黑，钳到柔和玩具质感区间
        rough = n.inputs["Roughness"]
        if rough.is_linked:
            n.inputs["Roughness"].default_value = 0.55  # 供混合参考；保持链接由贴图驱动
        else:
            n.inputs["Roughness"].default_value = 0.55

# ---------------- 2. 摆正：绕 X +90°（躺姿 → 站姿，面向 -Y） ----------------
mesh.rotation_mode = "XYZ"
mesh.rotation_euler = (math.radians(90.0), 0.0, 0.0)
bpy.context.view_layer.update()

# ---------------- 3. 居中落地：x/y 居中，min z = 0；应用变换 ----------------
depsgraph = bpy.context.evaluated_depsgraph_get()
oe = mesh.evaluated_get(depsgraph)
mn = Vector((1e9, 1e9, 1e9))
mx = Vector((-1e9, -1e9, -1e9))
for corner in oe.bound_box:
    wc = oe.matrix_world @ Vector(corner)
    mn = Vector(map(min, mn, wc))
    mx = Vector(map(max, mx, wc))
c = (mn + mx) * 0.5
mesh.location.x += -c.x
mesh.location.y += -c.y
mesh.location.z += -mn.z
bpy.ops.object.select_all(action="DESELECT")
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.context.view_layer.update()

depsgraph = bpy.context.evaluated_depsgraph_get()
oe = mesh.evaluated_get(depsgraph)
mn = Vector((1e9, 1e9, 1e9))
mx = Vector((-1e9, -1e9, -1e9))
for corner in oe.bound_box:
    wc = oe.matrix_world @ Vector(corner)
    mn = Vector(map(min, mn, wc))
    mx = Vector(map(max, mx, wc))
dims = mx - mn
print("SETUP dims after normalize:", [round(v, 4) for v in dims],
      "min:", [round(v, 4) for v in mn], "max:", [round(v, 4) for v in mx])

# ---------------- 4. 渲染设置：透明底 + 三点灯 ----------------
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.92, 1.0)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.35


def clear_cameras_lights():
    for o in list(scene.collection.objects):
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o, do_unlink=True)


clear_cameras_lights()

cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

key = bpy.data.lights.new("Key", type="AREA")
key.energy = 400.0
key.size = 1.5
key_obj = bpy.data.objects.new("Key", key)
scene.collection.objects.link(key_obj)
key_obj.location = (1.2, -1.6, 1.8)
key_obj.rotation_euler = (math.radians(55), 0.0, math.radians(35))

fill = bpy.data.lights.new("Fill", type="AREA")
fill.energy = 150.0
fill.size = 2.0
fill_obj = bpy.data.objects.new("Fill", fill)
scene.collection.objects.link(fill_obj)
fill_obj.location = (-1.6, -1.2, 1.0)
fill_obj.rotation_euler = (math.radians(75), 0.0, math.radians(-50))

rim = bpy.data.lights.new("Rim", type="AREA")
rim.energy = 300.0
rim.size = 1.2
rim_obj = bpy.data.objects.new("Rim", rim)
scene.collection.objects.link(rim_obj)
rim_obj.location = (0.0, 1.8, 1.5)
rim_obj.rotation_euler = (math.radians(105), 0.0, 0.0)


def shoot(filepath, location, target=(0.0, 0.0, dims.z * 0.5)):
    d = (Vector(target) - Vector(location)).normalized()
    cam.location = location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_end = 100.0
    scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)
    print("SAVED", filepath)


shoot(os.path.join(OUT, "model_setup_front.png"), (0.0, -2.2, 0.55))
shoot(os.path.join(OUT, "model_setup_side.png"), (2.2, 0.0, 0.55))
shoot(os.path.join(OUT, "model_setup_persp.png"), (1.3, -1.6, 1.1))

bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print("SETUP_DONE")
