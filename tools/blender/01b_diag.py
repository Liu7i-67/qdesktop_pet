# -*- coding: utf-8 -*-
"""诊断：网格为何不可见。打印可见性/材质节点状态，用 Workbench FLAT 白底渲染剪影。"""
import math
import os

import bpy

ROOT = r"E:\qbb\github\qdesktop_pet"
BLEND = os.path.join(ROOT, "model", "gugugaga.blend")
OUT = os.path.join(ROOT, "tools_out")

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
mesh = bpy.data.objects["node_0"]

print("DIAG hide_render:", mesh.hide_render, "| hide_viewport:", mesh.hide_viewport)
print("DIAG collections:", [c.name for c in mesh.users_collection])
print("DIAG matrix_world.translation:", tuple(round(v, 3) for v in mesh.matrix_world.translation))
print("DIAG scale:", tuple(round(v, 3) for v in mesh.matrix_world.to_scale()))
print("DIAG polys:", len(mesh.data.polygons), "| verts:", len(mesh.data.vertices))
mat = mesh.data.materials[0] if mesh.data.materials else None
if mat and mat.use_nodes:
    print("DIAG material nodes:", [(n.type, n.name) for n in mat.node_tree.nodes])
    print("DIAG links:", [(l.from_node.type, l.from_socket.name, "->", l.to_node.type, l.to_socket.name)
                         for l in mat.node_tree.links])
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            bc = n.inputs["Base Color"]
            print("DIAG principled base_color linked:", bc.is_linked,
                  "value:", tuple(round(v, 3) for v in bc.default_value))
if mat and not mat.use_nodes:
    print("DIAG material use_nodes=False, diffuse:", tuple(round(v, 3) for v in mat.diffuse_color))

# Workbench FLAT + 白底 + 正交相机：只看几何剪影是否存在
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "FLAT"
scene.display.shading.color_type = "TEXTURE"
scene.display.render_aa = "FXAA"
scene.world = bpy.data.worlds.new("DiagWorld")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)

cam_data = bpy.data.cameras.new("DiagCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 1.3
cam = bpy.data.objects.new("DiagCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (0.0, -3.0, 0.55)
cam.rotation_euler = (math.radians(90), 0.0, 0.0)

scene.render.resolution_x = 360
scene.render.resolution_y = 360
scene.render.filepath = os.path.join(OUT, "model_diag_workbench.png")
bpy.ops.render.render(write_still=True)
print("DIAG_DONE")
