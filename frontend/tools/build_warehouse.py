"""Build the original Operix warehouse GLB and reference render in Blender.

Run Blender in background mode with --factory-startup --python <this file>.
"""
import math
from pathlib import Path

import bpy
from mathutils import Vector

OUTPUT = Path(__file__).resolve().parents[1] / "public" / "experience"


def material(name, color, metal=0, roughness=0.62):
    channels = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgba = tuple(c / 12.92 if c < 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                 for c in channels) + (1,)
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = roughness
    return mat


def finish(obj, mat, parent, bevel=0, smooth=False):
    if parent:
        obj.parent = parent
    obj.data.materials.append(mat)
    if smooth:
        for face in obj.data.polygons:
            face.use_smooth = True
    if bevel:
        mod = obj.modifiers.new("Rounded manufactured edges", "BEVEL")
        mod.width, mod.segments = bevel, 2
        obj.modifiers.new("Face normals", "WEIGHTED_NORMAL")
    return obj


def group(name, loc=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent, obj.location = parent, loc
    return obj


def box(loc, dims, mat, parent=None, bevel=0.025):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.location = loc
    return finish(obj, mat, parent, bevel)


def ellipsoid(loc, dims, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12)
    obj = bpy.context.object
    obj.location, obj.scale = loc, Vector(dims) / 2
    return finish(obj, mat, parent, smooth=True)


def beam(a, b, radius, mat, parent=None, tip=None, vertices=16):
    start, end = Vector(a), Vector(b)
    axis = end - start
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius,
                                    radius2=radius if tip is None else tip, depth=axis.length)
    obj = bpy.context.object
    obj.location = (start + end) / 2
    obj.rotation_euler = axis.to_track_quat("Z", "Y").to_euler()
    return finish(obj, mat, parent, smooth=True)


def loft(sections, mat, parent, sides=24):
    """Elliptical cross-sections produce shaped panels and clothing."""
    verts = [(x + rx * math.cos(i * math.tau / sides), y + ry * math.sin(i * math.tau / sides), z)
             for x, z, y, rx, ry in sections for i in range(sides)]
    faces = [tuple(reversed(range(sides)))]
    for ring in range(len(sections) - 1):
        for i in range(sides):
            a = ring * sides + i
            b = ring * sides + (i + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    faces.append(tuple(range(len(verts) - sides, len(verts))))
    mesh = bpy.data.meshes.new("Shaped surface")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Shaped surface", mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, mat, parent, smooth=True)


def pallet(x, y, z, count, parent):
    for offset in (-0.36, 0, 0.36):
        box((x + offset, y, z + 0.06), (0.10, 0.78, 0.09), slate, parent, 0.01)
    for offset in (-0.31, -0.15, 0, 0.15, 0.31):
        box((x, y + offset, z + 0.125), (0.86, 0.115, 0.045), gray, parent, 0.008)
    for index in range(count):
        dx = (index % 2 - 0.5) * 0.39 if count > 1 else 0
        dz = index // 2 * 0.34
        height = 0.26 if index % 2 else 0.31
        length = 0.35 if count > 1 else 0.70
        box((x + dx, y, z + 0.15 + height / 2 + dz),
            (length, 0.66, height), (white, pale, carton)[(index + count) % 3], parent, 0.024)
        box((x + dx, y - 0.334, z + 0.23 + dz), (0.12, 0.005, 0.067), white, parent, 0.004)
        for dx2 in (-0.033, -0.01, 0.013, 0.036):
            box((x + dx + dx2, y - 0.338, z + 0.23 + dz),
                (0.006, 0.002, 0.043), slate, parent, 0)
        box((x + dx, y, z + 0.151 + height + dz), (0.07, 0.66, 0.004), seam, parent, 0)


def shelving(x, y, parent, inventory):
    for dx in (-1.01, 1.01):
        for dy in (-0.52, 0.52):
            box((x + dx, y + dy, 1.48), (0.09, 0.09, 2.96), ink, parent, 0.014)
            box((x + dx, y + dy, 0.052), (0.23, 0.22, 0.1), gray, parent, 0.018)
            box((x + dx, y + dy, 0.20), (0.13, 0.125, 0.29), brand, parent, 0.016)
            for z in [0.75, 1.11, 1.48, 1.84, 2.21, 2.57]:
                box((x + dx, y + dy - 0.05, z), (0.027, 0.013, 0.039), gray, parent, 0.003)
        for z in (0.33, 1.17, 2.19):
            box((x + dx, y, z), (0.068, 1.03, 0.07), slate, parent, 0.008)
        for a, b in ((0.36, 1.34), (1.35, 2.45)):
            beam((x + dx, y - 0.46, a), (x + dx, y + 0.46, b), 0.022, gray, parent, vertices=8)
    for index, z in enumerate([0.34, 1.3, 2.26]):
        for dy in (-0.48, 0.48):
            box((x, y + dy, z), (2.04, 0.083, 0.108), brand, parent, 0.012)
        box((x, y, z - 0.008), (1.91, 0.92, 0.043), slate, parent, 0.006)
        for slot, dx in enumerate((-0.48, 0.48)):
            if inventory[index][slot]:
                pallet(x + dx, y, z + 0.035, inventory[index][slot], parent)


def worker():
    root = group("Worker", (-1.9, -1.27, 0))
    ellipsoid((0, 0, 0.92), (0.37, 0.25, 0.27), ink, root)
    loft([(0, 0.94, 0, 0.176, 0.119), (0, 1.18, 0, 0.195, 0.134),
          (0, 1.38, 0, 0.232, 0.143), (0, 1.46, 0, 0.139, 0.1)], brand, root)
    for z in (1.015, 1.079):
        loft([(0, z, 0, 0.183, 0.132), (0, z + 0.023, 0, 0.186, 0.132)], white, root)
    beam((0, 0, 1.40), (0, 0, 1.57), 0.061, skin, root)
    ellipsoid((0, -0.025, 1.59), (0.199, 0.216, 0.245), skin, root)
    ellipsoid((0, -0.129, 1.59), (0.038, 0.053, 0.05), skin, root)
    ellipsoid((0, -0.014, 1.695), (0.24, 0.257, 0.167), white, root)
    ellipsoid((0, -0.048, 1.653), (0.253, 0.31, 0.038), white, root)
    ellipsoid((0, -0.009, 1.755), (0.032, 0.179, 0.027), pale, root)
    for side, sign in (("L", -1), ("R", 1)):
        x = sign * 0.104
        leg = group("Leg" + side, (x, 0, 0.92), root)
        beam((0, 0, -0.025), (sign * .025, -.018, -.44), .092, ink, leg, tip=.072)
        beam((sign * .025, -.018, -.42), (sign * .044, .008, -.79), .071, ink, leg, tip=.051)
        ellipsoid((sign * .046, -.063, -.845), (.155, .256, .135), rubber, leg)
        shoulder = group("Arm" + side, (sign * .216, 0, 1.36), root)
        ellipsoid((0, 0, 0), (.167, .186, .196), slate, shoulder)
        beam((0, 0, -.022), (sign * .057, -.004, -.21), .077, slate, shoulder, tip=.057)
        beam((sign * .057, -.004, -.20), (sign * .061, -.065, -.36), .053, skin, shoulder, tip=.039)
        ellipsoid((sign * .065, -.068, -.38), (.098, .105, .12), skin, shoulder)
    return root


def forklift():
    root = group("Forklift", (2.35, -0.68, 0))
    loft([(0, .29, .17, .63, .98), (0, .49, .24, .67, 1.1),
          (0, .83, .31, .64, .96), (0, 1.03, .58, .58, .59)], brand, root)
    box((0, -.46, .61), (1.08, .82, .18), slate, root, .048)
    box((0, .09, .97), (.52, .51, .14), rubber, root, .065)
    seat = box((0, .31, 1.21), (.47, .13, .46), rubber, root, .055)
    seat.rotation_euler.x = math.radians(-12)
    box((0, -.7, 1.09), (.94, .27, .22), ink, root, .06)
    beam((0, -.57, 1.09), (0, -.51, 1.32), .045, gray, root)
    bpy.ops.mesh.primitive_torus_add(major_segments=24, minor_segments=8, major_radius=.155, minor_radius=.021)
    steering = bpy.context.object
    steering.location = (0, -.51, 1.32)
    steering.rotation_euler.x = math.radians(20)
    finish(steering, rubber, root, smooth=True)
    for x in (-.51, .51):
        beam((x, -.55, 1.04), (x, -.52, 2.13), .053, ink, root)
        beam((x, .66, 1.0), (x, .44, 2.13), .057, ink, root)
        box((x, -.56, 1.65), (.16, .09, .12), pale, root, .025)
        box((x, -.99, 1.26), (.116, .125, 2.02), ink, root, .012)
        box((x * .69, -1.08, 1.25), (.085, .093, 1.97), gray, root, .01)
        box((x * .70, -1.22, .40), (.12, .15, .56), slate, root, .022)
        box((x * .70, -1.62, .188), (.13, .79, .098), gray, root, .019)
        tip = box((x * .70, -2.05, .185), (.125, .19, .06), gray, root, .014)
        tip.rotation_euler.x = math.radians(-9)
    box((0, -1.13, .63), (1.09, .14, .19), ink, root, .022)
    box((0, -.99, 2.18), (1.17, .16, .10), ink, root)
    box((0, -.044, 2.17), (1.18, 1.12, .063), slate, root, .026)
    for x in (-.39, -.195, 0, .195, .39):
        box((x, -.03, 2.219), (.035, 1.02, .03), gray, root, .008)
    ellipsoid((.40, .38, 2.265), (.142, .142, .116), pale, root)
    for i, (y, radius) in enumerate(((-.66, .34), (.75, .266))):
        for side, sign in (("L", -1), ("R", 1)):
            x = sign * .597
            wheel = group(f"Wheel{i}{side}", (x, y, radius), root)
            beam((-.121, 0, 0), (.121, 0, 0), radius, rubber, wheel, vertices=28)
            beam((-.128, 0, 0), (.128, 0, 0), radius * .57, gray, wheel, vertices=24)
            beam((-.135, 0, 0), (.135, 0, 0), radius * .23, ink, wheel)
            for step in range(5):
                angle = step * math.tau / 5
                ellipsoid((sign * .134, math.cos(angle)*radius*.36, math.sin(angle)*radius*.36),
                          (.026, .048, .048), slate, wheel)
    for z in (.68, .75, .82, .89):
        box((0, 1.151, z), (.52, .02, .024), ink, root, .007)
    return root


def security_camera():
    root = group("SecurityCamera", (-4.9, 2.05, 2.92))
    box((0, .25, 0), (.25, .11, .38), gray, root)
    beam((0, .24, -.08), (0, -.05, -.17), .045, slate, root)
    body = group("Optics", (0, -.15, -.04), root)
    body.rotation_euler.x = math.radians(17)
    body.rotation_euler.z = math.radians(30)
    box((0, -.11, .05), (.31, .64, .26), white, body, .046)
    box((0, -.16, .188), (.39, .66, .067), pale, body, .025)
    beam((0, -.445, .046), (0, -.503, .046), .106, ink, body, vertices=32)
    beam((0, -.505, .046), (0, -.512, .046), .068, lens, body, vertices=32)


def consolidate(root):
    """Group each rigid part by material without changing its transform."""
    for node in [root, *[o for o in root.children_recursive if o.type == "EMPTY"]]:
        meshes_by_material = {}
        for obj in list(node.children):
            if obj.type != "MESH":
                continue
            for mod in list(obj.modifiers):
                bpy.context.view_layer.objects.active = obj
                bpy.ops.object.modifier_apply(modifier=mod.name)
            meshes_by_material.setdefault(obj.data.materials[0].name, []).append(obj)
        for mat_name, meshes in meshes_by_material.items():
            bpy.ops.object.select_all(action="DESELECT")
            for mesh in meshes:
                mesh.select_set(True)
            bpy.context.view_layer.objects.active = meshes[0]
            if len(meshes) > 1:
                bpy.ops.object.join()
            meshes[0].name = f"{node.name}_{mat_name}"


bpy.ops.wm.read_factory_settings(use_empty=True)
brand = material("Operix blue", "3767e8", .24, .31)
ink = material("Navy powder coat", "202e47", .15)
slate = material("Structural slate", "394d66", .22)
gray = material("Brushed steel", "8997a8", .44, .35)
white = material("Pearl white", "edf2f8", .05, .5)
pale = material("Fog blue", "aab9ce")
carton = material("Silver packaging", "c7c2bc")
seam = material("Pallet tape", "98a9bd")
rubber = material("Tire rubber", "141e30", 0, .87)
skin = material("Warm skin", "a87968", 0, .8)
lens = material("Optical glass", "263f69", .35, .16)
floor = material("Concrete", "bec9d8", 0, .86)

warehouse = group("Warehouse")
box((0, 0, -.27), (11.4, 7.6, .47), ink, warehouse, .12)
box((0, 0, -.045), (11.35, 7.55, .10), floor, warehouse, .035)
box((0, 3.57, 1.38), (11.05, .15, 2.76), pale, warehouse, .04)
for x in (-5.35, -2.7, 0, 2.7, 5.35):
    box((x, 3.47, 1.48), (.15, .18, 2.96), slate, warehouse, .014)
box((0, 3.46, 2.57), (10.65, .12, .13), gray, warehouse, .015)
for x in (-4.2, -1.4, 1.4, 4.2):
    box((x, -3.17, .014), (1.28, .05, .008), white, warehouse, .004)
for x in (-3.94, -1.79, 2.1, 4.25):
    shelving(x, 2.23, warehouse, [(2, 3), (1, 2), (2, 0)] if x < 0 else [(3, 2), (2, 1), (0, 2)])
for slot in range(5):
    box((-3.7 + slot * .15, -.12, .015), (.061, 1.17, .008), white, warehouse, .002)
for y in (-2.52, -.99, .54):
    box((.0, y, .014), (.08, .47, .008), white, warehouse, .004)
for x in (-5.2, 5.2):
    box((x, 1.15, .015), (.05, 3.89, .008), white, warehouse, .003)
pallet(4.52, .78, .02, 3, warehouse)
pallet(-4.7, .83, .02, 2, warehouse)
worker_root = worker()
worker_root.rotation_euler.z = math.radians(34)
forklift_root = forklift()
forklift_root.rotation_euler.z = math.radians(-35)
security_camera()
for root in [warehouse, worker_root, forklift_root, bpy.data.objects["SecurityCamera"]]:
    consolidate(root)

scene = bpy.context.scene
bpy.ops.object.camera_add(location=(10.0, -14.8, 11.2))
camera = bpy.context.object
camera.name = "StoryCamera"
camera.rotation_euler = (Vector((0, 0, .82)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 15.2
scene.camera = camera
scene.render.resolution_x, scene.render.resolution_y = 1200, 800
scene.render.resolution_percentage = 100
scene.world = bpy.data.worlds.new("Studio ambient")
scene.world.color = (.42, .45, .52)
scene.render.film_transparent = True


def light(position, strength, diameter):
    bpy.ops.object.light_add(type="AREA", location=position)
    obj = bpy.context.object
    obj.rotation_euler = (-obj.location).to_track_quat("-Z", "Y").to_euler()
    obj.data.energy, obj.data.shape, obj.data.size = strength, "DISK", diameter


light((-4, -6, 11), 1650, 7)
light((6, 3, 8), 1250, 8)
light((2, -2, 6), 310, 5)
scene.render.engine = "CYCLES"
scene.cycles.samples = 20
scene.cycles.use_denoising = True
OUTPUT.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(OUTPUT / "warehouse.glb"), export_format="GLB",
                          export_cameras=False, export_lights=False,
                          export_meshopt_compression_enable=True)
scene.render.image_settings.file_format = "WEBP"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.quality = 88
scene.render.filepath = str(OUTPUT / "warehouse-reference.webp")
bpy.ops.render.render(write_still=True)
