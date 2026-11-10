# -*- coding: utf-8 -*-
"""程序化绑定：五官定位 → 骨架+自动权重 → 喙开合形态键 → 闭眼/眯眼贴图变体 → 测试渲染。

全部使用 Blender 自带 numpy（无 PIL 依赖）；贴图像素按原始 sRGB 编码（Non-Color）读写。
运行：
  blender.exe --background --factory-startup --python-exit-code 1 \
      --python tools/blender/06_rig_build.py
产出：
  - model/gugugaga_rigged.blend   绑定后的主项目
  - model/face_blink.png / face_happy.png   表情贴图变体
  - tools_out/rig_test_*.png      测试渲染（行走姿态/闭眼/张喙/开心）
"""
import json
import math
import os

import bpy
import numpy as np
from mathutils import Vector

ROOT = r"E:\qbb\github\qdesktop_pet"
BLEND_IN = os.path.join(ROOT, "model", "gugugaga.blend")
BLEND_OUT = os.path.join(ROOT, "model", "gugugaga_rigged.blend")
OUT = os.path.join(ROOT, "tools_out")
MODEL_DIR = os.path.join(ROOT, "model")
os.makedirs(MODEL_DIR, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND_IN)
scene = bpy.context.scene
mesh = bpy.data.objects["node_0"]
bpy.context.view_layer.objects.active = mesh

# =====================================================================
# 1. 定位基础色贴图节点（可能隔着 HSV 节点）
# =====================================================================
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
assert tex_node is not None and tex_node.image, "未找到基础色贴图节点"
base_img = tex_node.image
W, H = base_img.size
print("RIG base texture:", base_img.name, (W, H))

# =====================================================================
# 2. 贴图 → numpy（Non-Color 读原始 sRGB 编码值；屏幕行序=顶行在前）
# =====================================================================
tex_png = os.path.join(MODEL_DIR, "basecolor_extract.png")
base_img.filepath_raw = tex_png
base_img.file_format = "PNG"
base_img.save()

reader = bpy.data.images.load(tex_png)
reader.colorspace_settings.name = "Non-Color"
buf = np.empty(W * H * 4, dtype=np.float32)
reader.pixels.foreach_get(buf)
buf = buf.reshape(H, W, 4)[::-1]          # 翻成屏幕行序（row 0 = 顶）
tex = buf[..., :3]

n_loops = len(mesh.data.loops)
uvs = np.empty(n_loops * 2, dtype=np.float32)
mesh.data.uv_layers.active.data.foreach_get("uv", uvs)
uvs = uvs.reshape(-1, 2)
loop_vert = np.empty(n_loops, dtype=np.int32)
mesh.data.loops.foreach_get("vertex_index", loop_vert)

px = np.clip((uvs[:, 0] * W).astype(np.int64), 0, W - 1)
py = np.clip(((1.0 - uvs[:, 1]) * H).astype(np.int64), 0, H - 1)
loop_rgb = tex[py, px]

R, G, B = loop_rgb[:, 0], loop_rgb[:, 1], loop_rgb[:, 2]
cls = np.zeros(n_loops, dtype=np.int8)
cls[((R > 0.55) & (G > 0.45) & (B < 0.38) & (np.abs(R - G) < 0.18))] = 1   # 喙黄
cls[((R > 0.5) & (G > 0.28) & (G < R - 0.03) & (B < 0.30))] = 2            # 蹼足橙
# 虹膜：中亮蓝灰（排除偏蓝白高光 R>0.84 与深色瞳孔 R<0.45、皮肤 B<R）
cls[((B > 0.60) & (B - R > 0.07) & (R > 0.45) & (R < 0.84) &
     (G > 0.50) & (G < 0.90))] = 3

n_verts = len(mesh.data.vertices)
co = np.empty(n_verts * 3, dtype=np.float32)
mesh.data.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)

vert_cls = np.zeros(n_verts, dtype=np.int8)
for c in (1, 2, 3):
    sel = cls == c
    if sel.any():
        vert_cls[np.unique(loop_vert[sel])] = c

beak_idx = np.where(vert_cls == 1)[0]
if len(beak_idx):          # 喙锚点：限制在头顶前部（z>0.7），排除误检
    keep = co[beak_idx, 2] > 0.70
    beak_idx = beak_idx[keep]
beak_c = co[beak_idx].mean(axis=0) if len(beak_idx) else np.array([0.0, -0.25, 0.96])
print("RIG beak verts:", len(beak_idx), "centroid:", [round(float(v), 3) for v in beak_c])

feet = np.where(vert_cls == 2)[0]
feet = feet[co[feet, 2] < 0.30]            # 蹼足只在底部
legs = {}
for side, cond in (("L", co[feet, 0] < 0), ("R", co[feet, 0] >= 0)):
    pts = co[feet[cond]]
    if len(pts):
        legs[side] = pts.mean(axis=0)
        print(f"RIG leg{side}: centroid={[round(float(v), 3) for v in legs[side]]} n={len(pts)}")

flip_idx = np.where((np.abs(co[:, 0]) > 0.30) & (co[:, 2] < 0.55))[0]
flippers = {}
for side, cond in (("L", co[flip_idx, 0] < 0), ("R", co[flip_idx, 0] >= 0)):
    pts = co[flip_idx[cond]]
    if len(pts):
        flippers[side] = pts.mean(axis=0)
        print(f"RIG flipper{side}: centroid={[round(float(v), 3) for v in flippers[side]]} n={len(pts)}")

# 虹膜：喙锚点空间窗口（只框脸部眼区，排除帽檐带 z>0.8）+ 颜色 + 可见面法线
iris = np.where(vert_cls == 3)[0]
bx, by, bz = float(beak_c[0]), float(beak_c[1]), float(beak_c[2])
if len(iris):
    c2 = co[iris]
    win = ((np.abs(c2[:, 0] - bx) < 0.18) & (c2[:, 1] < by + 0.10) &
           (c2[:, 2] > bz - 0.36) & (c2[:, 2] < bz - 0.17))
    iris = iris[win]
    # 排除眼球背面/隐藏面：这些面的 UV 在别的岛，会污染密度峰值
    lnorm = np.empty(n_loops * 3, dtype=np.float32)
    mesh.data.loops.foreach_get("normal", lnorm)
    lnorm = lnorm.reshape(-1, 3)
    front_loops = np.where(lnorm[:, 1] < -0.25)[0]
    vis_verts = np.unique(loop_vert[front_loops])
    iris = np.intersect1d(iris, vis_verts)
print("RIG iris candidates after anchor+normal window:", len(iris))
eye_uv_px, eyes_c = {}, {}
if len(iris):
    uvs_v = uvs[loop_vert]
    for side, cond in (("L", co[iris, 0] < bx), ("R", co[iris, 0] >= bx)):
        vset = iris[cond]
        if not len(vset):
            continue
        pts = co[vset]
        eyes_c[side] = pts.mean(axis=0)
        uu = uvs_v[vset]
        # 密度峰值定位：虹膜 UV 点最密的格子即眼心（对 UV 岛拉伸/离群免疫）
        pts_px = np.stack([uu[:, 0] * W, (1.0 - uu[:, 1]) * H], axis=1)
        bin_size = 96
        lo = pts_px.min(axis=0)
        gw = int((pts_px[:, 0].max() - lo[0]) // bin_size) + 1
        gh = int((pts_px[:, 1].max() - lo[1]) // bin_size) + 1
        hist, _, _ = np.histogram2d(pts_px[:, 0], pts_px[:, 1],
                                    bins=[max(1, gw), max(1, gh)],
                                    range=[[lo[0], lo[0] + gw * bin_size],
                                           [lo[1], lo[1] + gh * bin_size]])
        i0, j0 = np.unravel_index(np.argmax(hist), hist.shape)
        bx0, by0 = lo[0] + (i0 + 0.5) * bin_size, lo[1] + (j0 + 0.5) * bin_size
        near = pts_px[(np.abs(pts_px[:, 0] - bx0) < bin_size) &
                      (np.abs(pts_px[:, 1] - by0) < bin_size)]
        c = near.mean(axis=0) if len(near) else np.array([bx0, by0])
        spread = near.std(axis=0) * 2.4 + 18.0
        ru = float(min(max(spread[0], 30.0), 170.0))
        rv = float(min(max(spread[1], 30.0), 170.0))
        eye_uv_px[side] = {"cu": float(c[0]), "cv": float(c[1]), "ru": ru, "rv": rv}
        print(f"RIG eye{side}: centroid={[round(float(v), 3) for v in eyes_c[side]]} n={len(vset)}",
              "uv px:", {k: round(v) for k, v in eye_uv_px[side].items()})

# =====================================================================
# 3. 骨架 + 自动权重
# =====================================================================
old = bpy.data.objects.get("Armature")
if old:
    bpy.data.objects.remove(old, do_unlink=True)
arm_data = bpy.data.armatures.new("Armature")
arm = bpy.data.objects.new("Armature", arm_data)
scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")


def add_bone(name, head, tail, parent=None):
    b = arm_data.edit_bones.new(name)
    b.head, b.tail = Vector(head), Vector(tail)
    if parent:
        b.parent = arm_data.edit_bones[parent]
    return b


add_bone("root", (0, 0, 0.10), (0, 0, 0.22))
add_bone("spine", (0, 0, 0.22), (0, 0, 0.50), "root")
add_bone("head", (0, 0, 0.50), (0, 0, 0.90), "spine")
for side, sign in (("L", -1), ("R", 1)):
    if side in flippers:
        fc = flippers[side]
        add_bone(f"flipper.{side}", (sign * 0.27, float(fc[1]), 0.46),
                 (float(fc[0]), float(fc[1]), max(0.20, float(fc[2]) - 0.10)), "spine")
for side in ("L", "R"):
    if side in legs:
        lc = legs[side]
        add_bone(f"leg.{side}", (float(lc[0]), float(lc[1]), 0.18),
                 (float(lc[0]), float(lc[1]), 0.02), "root")

if os.environ.get("RIG_DIAG"):
    print("RIG_DIAG_DONE")
    import sys
    sys.exit(0)

bpy.ops.object.mode_set(mode="OBJECT")
mesh.select_set(True)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
print("RIG armature parented (auto weights)")

# =====================================================================
# 4. beak_open 形态键
# =====================================================================
if mesh.data.shape_keys:
    mesh.shape_key_clear()
mesh.shape_key_add(name="Basis")
sk = mesh.shape_key_add(name="beak_open")
n_moved = 0
if len(beak_idx):
    bz = float(beak_c[2])
    bottom = beak_idx[co[beak_idx, 2] < bz + 0.01]
    for vi in bottom:
        sk.data[vi].co = Vector(co[vi]) + Vector((0.0, -0.012, -0.028))
    n_moved = len(bottom)
print("RIG beak_open verts moved:", n_moved)

# =====================================================================
# 5b. 眼睛 UV 精确定位：渲染正面 → 虹膜像素 → 正交射线反查命中面的 UV
# =====================================================================
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.resolution_x = 360
scene.render.resolution_y = 360
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True

hsv = next(n for n in nt.nodes if n.type == "HUE_SAT")
hsv.inputs["Value"].default_value = 0.32      # 用户要求更黑（线性 0.32 ≈ sRGB 0.60）
hsv.inputs["Saturation"].default_value = 1.30

for o in list(scene.collection.objects):
    if o.type == "CAMERA":
        bpy.data.objects.remove(o, do_unlink=True)
cam_data = bpy.data.cameras.new("TestCam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 1.30
cam = bpy.data.objects.new("TestCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

CAM_Z = 0.975 * 1.1844 - 1.1844 / 2.0
cam.location = (0.0, -3.0, CAM_Z)
cam.rotation_euler = (math.radians(90), 0.0, 0.0)
bpy.context.view_layer.update()

scene.render.filepath = os.path.join(OUT, "rig_eye_scan.png")
bpy.ops.render.render(write_still=True)

scan_img = bpy.data.images.load(os.path.join(OUT, "rig_eye_scan.png"))
scan_img.colorspace_settings.name = "Non-Color"
sw, sh = scan_img.size
sbuf = np.empty(sw * sh * 4, dtype=np.float32)
scan_img.pixels.foreach_get(sbuf)
sbuf = sbuf.reshape(sh, sw, 4)[::-1]           # 屏幕行序
srgb = sbuf[..., :3]
sR, sG, sB = srgb[..., 0], srgb[..., 1], srgb[..., 2]
alpha = sbuf[..., 3]
iris_px_mask = ((sB > sR + 0.03) & (sB > 0.35) & (sR < 0.8) & (alpha > 0.5))
iris_px_mask[:95, :] = False                   # 只扫脸部眼区窗口
iris_px_mask[185:, :] = False
iris_px_mask[:, :90] = False
iris_px_mask[:, 270:] = False
pys, pxs = np.where(iris_px_mask)
print("RIG eye scan pixels:", len(pxs))

depsgraph = bpy.context.evaluated_depsgraph_get()
half = 1.30 / 2.0
uv_hits = []                                    # (u, v, world_x)
for py_, px_ in zip(pys, pxs):
    ndc_x = (px_ + 0.5) / sw * 2.0 - 1.0
    ndc_y = 1.0 - (py_ + 0.5) / sh * 2.0
    ox = ndc_x * half
    oz = CAM_Z + ndc_y * half
    hit, loc, _n, fi, obj, _m = scene.ray_cast(depsgraph, Vector((ox, -3.0, oz)),
                                               Vector((0.0, 1.0, 0.0)))
    if not hit or obj.original.name != mesh.name:
        continue
    poly = mesh.data.polygons[fi]
    us, vs = [], []
    for li in poly.loop_indices:
        us.append(mesh.data.uv_layers.active.data[li].uv[0])
        vs.append(mesh.data.uv_layers.active.data[li].uv[1])
    uv_hits.append((sum(us) / len(us), sum(vs) / len(vs), loc.x))

eye_uv_px = {}
if uv_hits:
    arr = np.array(uv_hits, dtype=np.float32)
    for side, cond in (("L", arr[:, 2] < 0.0), ("R", arr[:, 2] >= 0.0)):
        pts = arr[cond]
        if not len(pts):
            continue
        ppx = np.stack([pts[:, 0] * W, (1.0 - pts[:, 1]) * H], axis=1)
        cu, cv = float(np.median(ppx[:, 0])), float(np.median(ppx[:, 1]))
        near = ppx[(np.abs(ppx[:, 0] - cu) < 200) & (np.abs(ppx[:, 1] - cv) < 200)]
        spread = near.std(axis=0) * 3.2 + 22.0   # 扩大覆盖虹膜+巩膜
        cv += spread[1] * 0.10                   # 略下移，盖住下缘露出的眼球
        eye_uv_px[side] = {"cu": cu, "cv": cv,
                           "ru": float(min(max(spread[0], 30.0), 150.0)),
                           "rv": float(min(max(spread[1], 30.0), 150.0))}
        print(f"RIG raycast eye{side}: center=({cu:.0f},{cv:.0f}) "
              f"r=({eye_uv_px[side]['ru']:.0f},{eye_uv_px[side]['rv']:.0f}) n={len(pts)}")

# 目视校准覆盖（射线中位心略偏小，按裁片实测放大并微移，盖住眼球轮廓）
EYE_OVERRIDE = {
    "L": {"cu": 3453.0, "cv": 805.0, "ru": 112.0, "rv": 95.0},
    "R": {"cu": 2248.0, "cv": 2300.0, "ru": 112.0, "rv": 95.0},
}
for side, bb in EYE_OVERRIDE.items():
    if side in eye_uv_px:
        eye_uv_px[side].update(bb)
        print(f"RIG eye{side} override:", bb)

# =====================================================================
# 6. 表情贴图变体（numpy 直接改像素：肤色眼睑斑 + 睫毛弧线）
# =====================================================================
SKIN = np.array([243, 232, 224], dtype=np.float32) / 255.0
LASH = np.array([52, 56, 72], dtype=np.float32) / 255.0


def draw_eyelid(img2d, bb, arc):
    cx, cy = bb["cu"], bb["cv"]
    rw, rh = bb["ru"], bb["rv"]
    y0, y1 = int(max(0, cy - rh)), int(min(H, cy + rh))
    x0, x1 = int(max(0, cx - rw)), int(min(W, cx + rw))
    if y1 <= y0 or x1 <= x0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    mask = (((xx - cx) / rw) ** 2 + ((yy - cy) / rh) ** 2) <= 1.0
    # 肤色取样：色环上取"暖亮"像素的中位数，失败退回常量
    ry0, ry1 = int(max(0, cy - rh * 1.9)), int(min(H, cy + rh * 1.9))
    rx0, rx1 = int(max(0, cx - rw * 1.9)), int(min(W, cx + rw * 1.9))
    ring = img2d[ry0:ry1, rx0:rx1, :3].reshape(-1, 3)
    r_, g_, b_ = ring[:, 0], ring[:, 1], ring[:, 2]
    skinish = ring[(r_ > 0.62) & (g_ > 0.55) & (b_ > 0.5) & (r_ >= b_)]
    skin = (np.median(skinish, axis=0) if len(skinish) > 50 else SKIN).reshape(1, 3)
    region = img2d[y0:y1, x0:x1]
    msum = int(mask.sum())
    if msum:
        region[mask] = np.concatenate([np.tile(skin, (msum, 1)),
                                       region[mask][:, 3:]], axis=1)
    # 睫毛弧线（沿参数曲线 stamp 圆点）
    lw = max(2.5, rh * 0.14)
    t = np.linspace(0.0, math.pi, 48)
    if arc == "closed":                       # 闭眼：下弯弧
        ax = cx - rw * 0.72 * np.cos(t)
        ay = cy + rh * 0.12 + rh * 0.38 * np.sin(t)
    else:                                      # squint：上拱 ∩
        ax = cx - rw * 0.72 * np.cos(t)
        ay = cy + rh * 0.20 - rh * 0.38 * np.sin(t)
    for axx, ayy in zip(ax, ay):
        s0, s1 = int(ayy - lw), int(ayy + lw) + 1
        t0, t1 = int(axx - lw), int(axx + lw) + 1
        yy2, xx2 = np.mgrid[s0:s1, t0:t1]
        m2 = ((xx2 - axx) ** 2 + (yy2 - ayy) ** 2) <= lw * lw
        sub = img2d[s0:s1, t0:t1]
        sub[m2] = np.concatenate([np.tile(LASH, (int(m2.sum()), 1)),
                                  sub[m2][:, 3:]], axis=1)


variant_images = {}
if eye_uv_px:
    for tag, arc in (("blink", "closed"), ("happy", "squint")):
        work = buf.copy()
        for side, bb in eye_uv_px.items():
            draw_eyelid(work, bb, arc)
            print(f"RIG eyelid drawn: {tag} {side} center=({bb['cu']:.0f},{bb['cv']:.0f}) "
                  f"r=({bb['ru']:.0f},{bb['rv']:.0f})")
        for side, bb in eye_uv_px.items():      # 目视验证裁片
            cx, cy = int(bb["cu"]), int(bb["cv"])
            r = 320
            crop = work[max(0, cy - r):min(H, cy + r), max(0, cx - r):min(W, cx + r)]
            ch2, cw2 = crop.shape[:2]
            cimg = bpy.data.images.new(f"crop_{tag}_{side}", cw2, ch2, alpha=True)
            cimg.colorspace_settings.name = "Non-Color"
            cimg.pixels.foreach_set(crop[::-1].reshape(-1).astype(np.float32))
            cp = os.path.join(OUT, f"eye_crop_{tag}_{side}.png")
            cimg.filepath_raw = cp
            cimg.file_format = "PNG"
            cimg.save()
            print("RIG crop saved:", cp)
        out_img = bpy.data.images.new(f"face_{tag}", W, H, alpha=True)
        out_img.colorspace_settings.name = "Non-Color"
        out_img.pixels.foreach_set(work[::-1].reshape(-1))
        p = os.path.join(MODEL_DIR, f"face_{tag}.png")
        out_img.filepath_raw = p
        out_img.file_format = "PNG"
        out_img.save()
        loaded = bpy.data.images.load(p, check_existing=True)
        loaded.colorspace_settings.name = "sRGB"
        variant_images[tag] = loaded
        print("RIG saved texture variant:", p)
else:
    print("RIG_WARN no iris cluster; texture variants skipped")

# =====================================================================
# 7. 测试渲染：侧面行走 / 闭眼 / 张喙 / 开心挥手
# =====================================================================
scene.cycles.samples = 40


def set_cam(view):
    if view == "front":
        cam.location = (0.0, -3.0, CAM_Z)
        cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    else:
        cam.location = (-3.0, 0.0, CAM_Z)
        cam.rotation_euler = (math.radians(90), 0.0, math.radians(-90))


def reset_pose():
    for pb in arm.pose.bones:
        pb.rotation_euler = (0.0, 0.0, 0.0)
    tex_node.image = base_img
    sk.value = 0.0


def shoot(tag, view):
    set_cam(view)
    scene.render.filepath = os.path.join(OUT, f"rig_test_{tag}.png")
    bpy.ops.render.render(write_still=True)
    print("RIG_TEST_SAVED", tag)


reset_pose()
if "leg.L" in arm.pose.bones:
    arm.pose.bones["leg.L"].rotation_euler = (math.radians(28), 0, 0)
if "leg.R" in arm.pose.bones:
    arm.pose.bones["leg.R"].rotation_euler = (math.radians(-20), 0, 0)
shoot("walk_side", "side")

reset_pose()
if "blink" in variant_images:
    tex_node.image = variant_images["blink"]
shoot("blink", "front")

reset_pose()
sk.value = 1.0
shoot("beak_open", "front")

reset_pose()
if "happy" in variant_images:
    tex_node.image = variant_images["happy"]
if "flipper.L" in arm.pose.bones:
    arm.pose.bones["flipper.L"].rotation_euler = (0, 0, math.radians(-55))
if "flipper.R" in arm.pose.bones:
    arm.pose.bones["flipper.R"].rotation_euler = (0, 0, math.radians(20))
shoot("happy", "front")

reset_pose()
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)

with open(os.path.join(MODEL_DIR, "face_regions.json"), "w", encoding="utf-8") as f:
    json.dump({"eye_uv_px": eye_uv_px,
               "eyes_c": {k: [round(float(v), 4) for v in vv] for k, vv in eyes_c.items()},
               "beak_c": [round(float(v), 4) for v in beak_c]}, f, ensure_ascii=False, indent=2)
print("RIG_BUILD_DONE")
