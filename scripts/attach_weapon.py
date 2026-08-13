#!/usr/bin/env python3
"""Blender .blend 안의 무기 메시를 캐릭터 손 본에 **파지 프레임 이식 + 스키닝** 으로 장착.

    blender -b <character.blend> -P attach_weapon.py -- [옵션]

기본값만으로 동작한다(무기 자동 식별 + 내장 파지 프레임 + 현재 크기 유지 + 자동 검증).

## 무엇을 하는가
1. 무기 메시를 자동 식별하고 기존 부착을 **자동 해제**(재실행 안전).
2. 무기의 grip 중심 · 날 방향 · 날 두께축을 **손 본 rest 좌표계** 의 파지 프레임에 맞춘다.
3. 손 본 vertex group(100% weight) + Armature modifier 로 스키닝한다.
4. 부착 결과를 **자동 검증** 한다: 수치(grip/tip/크기) + follow-test + 렌더 스샷.

## 왜 '파지 프레임 이식' 인가 (구방식과의 차이)
구방식은 grip 중심을 손 본 head 에 **평행이동** 으로만 맞췄다. 위치는 맞지만
**방향을 정하지 못해** 검이 옆으로 눕거나 뒤를 향했고 `--rot` 로 매번 눈대중
보정해야 했다. 이제는 이미 올바르게 부착된 캐릭터에서 뽑은
(grip 위치 · 날 방향 · 두께축) 세 값을 손 본 로컬 좌표계로 이식하므로
**방향까지 한 번에 맞고, 여러 캐릭터가 완전히 같은 자세로 무기를 든다.**
프레임이 *손 본 로컬* 기준이라 키·체형·아마추어가 바뀌어도 그대로 옮겨진다.

## 성공 판정(3개 모두)
- `####ATTACH_OK`: `grip_to_fist` 작고(<0.05) `tip_to_wrist` 가 훨씬 큼, `det=1.0000`
- `####ATTACH_SIZE`: `weapon_to_char` 가 적정 범위 + `SIZE_WARN` 없음
- `####FOLLOW_OK` + `####SHOT` 스샷을 Read 로 **직접 열어** 육안 확인
"""
import bpy, sys, os, json, math, argparse
import numpy as np
from mathutils import Vector, Matrix, Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weapon_geom as wg

# 라리엔 PC(mixamo rig) 기준 **오른손** 파지 프레임. 손 본 rest 좌표계 기준이라
# 캐릭터/아마추어가 달라도 그대로 쓰인다(실측: 남녀 16종 + 아마추어 교체 후에도 동일).
# 다른 파지를 원하거나 왼손이면 extract_frame.py 로 새로 뽑아 --ref 로 넘긴다.
DEFAULT_FRAME = {
    "grip_H": [2.338, 3.329, 2.046],
    "blade_dir_H": [0.9492, -0.2864, -0.1304],
    "thin_dir_H": [0.2137, 0.2909, 0.9326],
}

# 무기 종류별 권장 weapon_to_char(무기 길이 / 캐릭터 키)
SIZE_BANDS = {
    "단검": (0.25, 0.35), "한손검": (0.45, 0.65),
    "대검": (0.70, 0.95), "창/지팡이": (0.90, 1.20),
}


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--weapon", default=None, help="무기 메시 이름(생략=자동 식별)")
    p.add_argument("--bone", default="mixamorig:RightHand", help="장착 손 본")
    p.add_argument("--ref", default=None, help="파지 프레임 json(생략=내장 기본값)")
    p.add_argument("--ratio", type=float, default=None,
                   help="목표 무기길이/캐릭터키. 생략하면 현재 크기를 그대로 유지")
    p.add_argument("--flip-thin", action="store_true", help="칼날 면이 뒤집혔을 때")
    p.add_argument("--out", default=None, help="저장 경로(생략=원본 덮어쓰기)")
    p.add_argument("--dry", action="store_true", help="저장하지 않고 수치만 확인")
    p.add_argument("--shot-dir", default=None, help="검증 스샷 폴더(생략=.blend 옆)")
    p.add_argument("--no-shot", action="store_true", help="검증 렌더 생략(권장하지 않음)")
    p.add_argument("--no-follow-test", action="store_true", help="follow-test 생략(권장하지 않음)")
    return p.parse_args(argv)


def clear_attachment(w):
    """기존 스키닝/패런팅 해제 — 옵션만 바꿔 몇 번이든 재실행할 수 있게 한다."""
    mw = w.matrix_world.copy()
    for m in list(w.modifiers):
        if m.type == "ARMATURE":
            w.modifiers.remove(m)
    if w.parent:
        w.parent = None
    w.matrix_world = mw
    while w.vertex_groups:
        w.vertex_groups.remove(w.vertex_groups[0])


def skin(w, arm, bone):
    """🛑 본 패런팅이 아니라 스키닝. Parent->Bone 은 FBX/GLB export 시 사라진다."""
    bpy.context.view_layer.update()
    mw = w.matrix_world.copy()
    w.parent = arm
    # mixamo armature 의 0.01 스케일 상쇄(대각 x100). 없으면 무기가 100배 축소된다.
    w.matrix_parent_inverse = arm.matrix_world.inverted()
    w.matrix_world = mw
    vg = w.vertex_groups.new(name=bone)
    vg.add(list(range(len(w.data.vertices))), 1.0, "REPLACE")
    m = w.modifiers.new("WeaponRig", "ARMATURE")
    m.object = arm


def deformed_world(w):
    """Armature modifier 적용 후(evaluated) 정점의 월드 좌표.
    🛑 object.matrix_world 로 검증하면 안 된다 — 스키닝은 origin 을 옮기지 않아
    거짓 음성이 난다."""
    deps = bpy.context.evaluated_depsgraph_get()
    oe = w.evaluated_get(deps)
    me = oe.to_mesh()
    dv = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", dv)
    dv = dv.reshape(-1, 3)
    MW = np.array(oe.matrix_world)
    out = dv @ MW[:3, :3].T + MW[:3, 3]
    oe.to_mesh_clear()
    return out


def setup_render_scene():
    """카메라·라이트·월드를 *명시적으로* 새로 구성.
    🛑 .blend 에 카메라/라이트가 아예 없는 경우가 흔하다(새로 만든 캐릭터).
    그때 기존 씬 설정에 기대면 프레임이 통째로 비어 나오고, 그걸 '검증' 으로
    착각하게 된다(실측 2026-08-13 male_vector — 3컷이 모두 같은 빈 이미지)."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "Standard"
        sc.display_settings.display_device = "sRGB"
    except Exception:
        pass
    world = sc.world
    if world is None:
        world = bpy.data.worlds.new("W")
        sc.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.16, 0.18, 0.22, 1.0)
    nt.links.new(bg.outputs[0], nt.nodes.new("ShaderNodeOutputWorld").inputs[0])
    for o in list(bpy.data.objects):
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o, do_unlink=True)
    cd = bpy.data.cameras.new("ChkCam")
    cd.clip_start, cd.clip_end = 0.001, 500.0
    cam = bpy.data.objects.new("ChkCam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    for nm, rot, e in (("K", (math.radians(55), 0, math.radians(35)), 4.0),
                       ("F", (math.radians(70), 0, math.radians(-120)), 2.5),
                       ("R", (math.radians(110), 0, math.radians(180)), 1.5)):
        ld = bpy.data.lights.new(nm, "SUN")
        ld.energy = e
        lo = bpy.data.objects.new(nm, ld)
        sc.collection.objects.link(lo)
        lo.rotation_euler = rot
    return sc, cam, cd


def render_check(arm, bone, out_dir):
    """전신 측면 + 손 클로즈업. 픽셀 통계도 찍어 '빈 렌더' 를 스스로 걸러낸다."""
    sc, cam, cd = setup_render_scene()
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render]
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (mn + mx) / 2
    span = max((mx - mn).x, (mx - mn).y, (mx - mn).z)
    hand = (arm.matrix_world @ arm.pose.bones[bone].matrix).translation
    sc.render.resolution_x, sc.render.resolution_y = 800, 900

    def shot(eye, target, name, ortho=None):
        cd.type = "ORTHO" if ortho else "PERSP"
        if ortho:
            cd.ortho_scale = ortho
        cam.location = Vector(eye)
        cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
        p = os.path.join(out_dir, name)
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        stat = ""
        try:
            tmp = os.path.join(out_dir, "_attach_stat.png")
            bpy.data.images.get("Render Result").save_render(filepath=tmp)
            im2 = bpy.data.images.load(tmp)
            a = np.array(im2.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
            stat = f"mean={a.mean():.3f}"
            bpy.data.images.remove(im2)
            os.remove(tmp)
        except Exception:
            pass
        print(f"####SHOT {p} {stat}")

    shot((center.x + span * 1.7, center.y - span * 0.6, center.z), center, "attach_check_side.png")
    side = -1.0 if hand.x < 0 else 1.0
    shot((hand.x + side * 0.25, hand.y - 0.35, hand.z + 0.12), hand,
         "attach_check_hand.png", ortho=0.34)


def follow_test(arm, w, bone):
    """팔 본을 크게 회전시켜 무기가 손을 **강체로** 따라가는지 측정.

    🛑 판정은 *손 본 로컬 프레임에서의 드리프트* 로 한다. 월드 상대 오프셋은
    손이 회전하면 당연히 변하므로, 그걸로 판정하면 멀쩡한 부착을 실패로 읽는다.
    """
    if arm.animation_data:
        arm.animation_data.action = None

    def sample():
        bpy.context.view_layer.update()
        Bw = arm.matrix_world @ arm.pose.bones[bone].matrix
        c = Vector(deformed_world(w).mean(axis=0))
        return Bw.translation.copy(), c, Bw.inverted() @ c

    h0, c0, b0 = sample()
    prefix = bone.rsplit(":", 1)[0] + ":" if ":" in bone else ""
    posed = []
    for bn, ang, ax in (("RightArm", 55, "Z"), ("RightForeArm", 40, "Y"), ("RightHand", 35, "X")):
        pb = arm.pose.bones.get(prefix + bn)
        if not pb:
            continue
        pb.rotation_mode = "QUATERNION"
        v = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[ax]
        pb.rotation_quaternion = Quaternion(v, math.radians(ang))
        posed.append(prefix + bn)
    if not posed:
        print("####FOLLOW_SKIP 포즈할 팔 본을 못 찾음")
        return
    h1, c1, b1 = sample()
    for n in posed:  # 포즈 원복 — 저장 파일에 테스트 포즈가 남지 않게
        arm.pose.bones[n].rotation_quaternion = Quaternion((1, 0, 0, 0))
    bpy.context.view_layer.update()

    dh, dwv, drift = (h1 - h0).length, (c1 - c0).length, (b1 - b0).length
    print(f"####FOLLOW hand_moved={dh:.4f} weapon_moved={dwv:.4f} bone_frame_drift={drift:.6f}")
    if dh < 0.01:
        print("####FOLLOW_INCONCLUSIVE 손이 거의 안 움직임")
    elif dwv < dh * 0.3:
        print("####FOLLOW_FAIL 무기가 손을 따라가지 않음 — 스키닝 확인")
    elif drift < 0.01:
        print("####FOLLOW_OK 무기가 손에 강체 고정 — 본 로컬 좌표 불변")
    else:
        print(f"####FOLLOW_WARN bone_frame_drift={drift:.4f}")


def main():
    a = parse_args()
    arm = wg.find_armature()
    w = wg.find_weapon(a.weapon)
    if a.bone not in arm.data.bones:
        raise SystemExit(f"####ATTACH_FAIL 본 없음: {a.bone}")
    ref = json.load(open(a.ref)) if a.ref else DEFAULT_FRAME
    print(f"####WEAPON name={w.name!r} verts={len(w.data.vertices)} bone={a.bone} "
          f"frame={'file:' + a.ref if a.ref else 'builtin'}")

    clear_attachment(w)
    smax_cur = max(abs(v) for v in w.matrix_world.to_scale())
    g = wg.analyze(w)
    S = g["S"]
    grip_local = wg.to_local(g["grip_c"], S)
    n_t = -g["thin"] if a.flip_thin else g["thin"]

    H = arm.matrix_world @ arm.data.bones[a.bone].matrix_local
    sH = max(abs(v) for v in H.to_scale())
    chh = wg.char_height(arm)

    R = wg.basis(Vector(ref["blade_dir_H"]), Vector(ref["thin_dir_H"])) \
        @ wg.basis(g["tip_c"] - g["grip_c"], n_t).transposed()
    s = (smax_cur / sH) if a.ratio is None else (a.ratio * chh) / (sH * g["length"])

    w.matrix_world = H @ (Matrix.Translation(Vector(ref["grip_H"]))
                          @ (R @ Matrix.Diagonal(Vector((s, s, s)))).to_4x4()
                          @ Matrix.Diagonal(S).to_4x4()
                          @ Matrix.Translation(-grip_local))
    bpy.context.view_layer.update()
    skin(w, arm, a.bone)
    bpy.context.view_layer.update()

    # ---- 수치 검증 ----
    t = wg.t_values(w, g)
    pts = deformed_world(w)
    gc = Vector(pts[(t >= g["t_gmin"]) & (t <= g["t_gmax"])].mean(axis=0))
    tipc = Vector(pts[np.abs(t - g["t_tip"]) <= g["span"] * 0.05].mean(axis=0))
    pb = arm.pose.bones[a.bone]
    wrist = (arm.matrix_world @ pb.matrix).translation
    fist = ((arm.matrix_world @ pb.head) + (arm.matrix_world @ pb.tail)) / 2
    true_len = g["length"] * max(abs(v) for v in w.matrix_world.to_scale())
    ratio = true_len / chh
    gw, gf, tw = (gc - wrist).length, (gc - fist).length, (tipc - wrist).length

    print(f"####ATTACH_OK det={R.determinant():.4f} pca_len={g['length']:.2f} "
          f"guard_bin={g['guard_bin']} grip_to_wrist={gw:.4f} grip_to_fist={gf:.4f} "
          f"tip_to_wrist={tw:.4f}")
    print(f"####ATTACH_SIZE weapon_len={true_len:.4f} char_height={chh:.4f} "
          f"weapon_to_char={ratio:.2f} (before={g['length'] * smax_cur / chh:.2f})")
    bands = " · ".join(f"{k} {v[0]}~{v[1]}" for k, v in SIZE_BANDS.items())
    if ratio > 1.05:
        print(f"####ATTACH_SIZE_WARN 캐릭터 키의 {ratio * 100:.0f}% — 너무 큼. --ratio 로 줄여라 ({bands})")
    elif 0 < ratio < 0.20:
        print(f"####ATTACH_SIZE_WARN 캐릭터 키의 {ratio * 100:.0f}% — 너무 작음. --ratio 로 키워라 ({bands})")
    if abs(R.determinant() - 1.0) > 1e-3:
        print("####ATTACH_WARN 회전 행렬 det!=1 — 거울 반전 가능")
    if tw < gw + 0.05:
        print("####ATTACH_WARN tip 이 손에 가깝다 — 칼날을 쥐었을 수 있음. 스샷 확인!")
    if gf > 0.12:
        print(f"####ATTACH_WARN grip 이 주먹에서 {gf:.3f} 떨어짐 — 손에서 뜬 것일 수 있음")

    if not a.no_follow_test:
        follow_test(arm, w, a.bone)
    if not a.no_shot:
        render_check(arm, a.bone, a.shot_dir or (os.path.dirname(bpy.data.filepath) or os.getcwd()))

    if a.dry:
        print("####DRY 저장하지 않음")
    else:
        path = a.out or bpy.data.filepath
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print(f"####SAVED {path}")


if __name__ == "__main__":
    main()
