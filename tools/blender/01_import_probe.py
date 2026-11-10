# -*- coding: utf-8 -*-
"""导入混元 GLB → 探测朝向：一次渲染 3 个候选朝向缩略图，供人工判定摆正方向。

运行（ Blender 4.5 LTS ）：
  blender.exe --background --factory-startup --python-exit-code 1 \
      --python tools/blender/01_import_probe.py
产出：
  - model/gugugaga.blend            主项目（保持导入原样，仅建好场景）
  - tools_out/model_probe_r0.png    原始朝向
  - tools_out/model_probe_rx90.png  绕 X +90°（glTF 常见 Z-up 授权 → 摆正）
  - tools_out/model_probe_rxm90.png 绕 X -90°
  - tools_out/model_probe.json      包围盒等结构信息
"""
import json
import math
import os
import sys

import bpy

ROOT = r"E:\qbb\github\qdesktop_pet"
GLB = os.path.join(ROOT, "local", "302d41a69092d2684c247d1db96ea6e5.glb")
BLEND_DIR = os.path.join(ROOT, "model")
OUT_DIR = os.path.join(ROOT, "tools_out")
BLEND_PATH = os.path.join(BLEND_DIR, "gugugaga.blend")

os.makedirs(BLEND_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------- 场景：工厂空场景 + 导入 ----------------
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    print("PROBE_ERROR: no mesh imported")
    sys.exit(1)


def world_bbox(objs):
    import mathutils
    mn = mathutils.Vector((1e9, 1e9, 1e9))
    mx = mathutils.Vector((-1e9, -1e9, -1e9))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        oe = o.evaluated_get(depsgraph)
        for corner in oe.bound_box:
            wc = oe.matrix_world @ mathutils.Vector(corner)
            mn = mathutils.Vector(map(min, mn, wc))
            mx = mathutils.Vector(map(max, mx, wc))
    return mn, mx


def set_rotation(root, rot_euler):
    for o in bpy.context.scene.objects:
        o.rotation_euler = (0.0, 0.0, 0.0)
    root.rotation_mode = "XYZ"            # glTF 导入默认四元数，euler 会被忽略
    root.rotation_euler = rot_euler
    bpy.context.view_layer.update()


# 找根：取所有导入对象中"无父节点"的那个（混元输出一般是单层）
roots = [o for o in bpy.context.scene.objects if o.parent is None]
root = roots[0] if roots else meshes[0]

mn0, mx0 = world_bbox(meshes)
info = {
    "root": root.name,
    "meshes": [m.name for m in meshes],
    "verts": sum(len(m.data.vertices) for m in meshes),
    "dims_as_imported": [round(v, 4) for v in (mx0 - mn0)],
    "bbox_min": [round(v, 4) for v in mn0],
    "bbox_max": [round(v, 4) for v in mx0],
    "materials": [m.name for m in bpy.data.materials],
    "images": [i.name for i in bpy.data.images if i.name not in ("Render Result", "Viewer Node")],
}

# ---------------- 相机 / 灯光 / 渲染设置 ----------------
scene = bpy.context.scene
# 无头环境 EEVEE 无 GPU 光栅化上下文（渲染出空白），探测统一用 Cycles CPU
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 32
scene.cycles.use_denoising = False
scene.render.resolution_x = 360
scene.render.resolution_y = 360
scene.render.image_settings.file_format = "PNG"
scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.08, 0.08, 0.09, 1.0)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

sun_data = bpy.data.lights.new("Sun", type="SUN")
sun_data.energy = 3.0
sun = bpy.data.objects.new("Sun", sun_data)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0.0, math.radians(-30))


def shoot(tag, center, size, view_dir):
    """把相机对准 center，从 view_dir 方向距离 size*1.9 拍一张。"""
    import mathutils
    d = mathutils.Vector(view_dir).normalized()
    cam.location = center + d * (size * 1.9)
    look = d.to_track_quat("-Z", "Y")
    cam.rotation_euler = look.to_euler()
    scene.render.filepath = os.path.join(OUT_DIR, f"model_probe_{tag}.png")
    bpy.ops.render.render(write_still=True)


center = (mn0 + mx0) * 0.5
size = max(mx0 - mn0)
try:
    for tag, rot, view in (
        ("r0", (0.0, 0.0, 0.0), (0.0, -1.0, 0.35)),      # 原始朝向·正面
        ("r0_side", (0.0, 0.0, 0.0), (1.0, -0.3, 0.3)),  # 原始朝向·斜侧（判朝向）
        ("rx90", (math.radians(90), 0.0, 0.0), (0.0, -1.0, 0.35)),
        ("rxm90", (math.radians(-90), 0.0, 0.0), (0.0, -1.0, 0.35)),
    ):
        set_rotation(root, rot)
        mn, mx = world_bbox(meshes)
        c = (mn + mx) * 0.5
        s = max(mx - mn)
        shoot(tag, c, s, view)
        info[f"dims_{tag}"] = [round(v, 4) for v in (mx - mn)]
except Exception as exc:  # 兜底：Workbench（可显示纹理色，纯 CPU）
    print("CYCLES_FAILED:", exc)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.color_type = "TEXTURE"
    scene.display.shading.light = "STUDIO"
    for tag, rot in (("r0", (0.0, 0.0, 0.0)), ("r0_side", (0.0, 0.0, 0.0)),
                     ("rx90", (math.radians(90), 0.0, 0.0)),
                     ("rxm90", (math.radians(-90), 0.0, 0.0))):
        set_rotation(root, rot)
        mn, mx = world_bbox(meshes)
        c = (mn + mx) * 0.5
        s = max(mx - mn)
        if tag == "r0_side":
            scene.render.filepath = os.path.join(OUT_DIR, f"model_probe_{tag}.png")
            shoot(tag, c, s, (1.0, -0.3, 0.3))
        else:
            shoot(tag, c, s, (0.0, -1.0, 0.35))
        info[f"dims_{tag}"] = [round(v, 4) for v in (mx - mn)]

set_rotation(root, (0.0, 0.0, 0.0))  # 项目里保持原样，摆正由下一步脚本决定

with open(os.path.join(OUT_DIR, "model_probe.json"), "w", encoding="utf-8") as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
print("PROBE_DONE", json.dumps(info, ensure_ascii=False))
