#!/usr/bin/env python3
"""Blender .blend 안에 이미 들어있는 무기 메시를 캐릭터 손 본에 grip-align + 스키닝으로 장착.

핵심 원칙:
  1) 본 패런팅(Parent->Bone)은 FBX/GLB export 시 사라진다. vertex group(손 본 100% weight)
     + Armature modifier 스키닝만 export 에 보존되어 애니메이션/스프라이트에서 손을 따라간다.
  2) 무기의 실제 손잡이(grip) 정점 중심을 손 본 head 월드 위치에 *실측* 정렬한다(추정 offset 금지).
     손잡이는 단면적이 아니라 **원형 단면(round ratio)** 으로 식별한다 — 칼날은 납작(round~0.45),
     손잡이는 원통(round~0.9). 단면적만 비교하면 칼날을 grip 으로 오인해 칼날이 손등에 박힌다.
  3) 키 비례 auto_scale 로 무기 크기를 캐릭터에 맞춘다.
  4) **grip_to_hand 거리 0 은 "내가 grip 이라 식별한 부분"이 손에 왔다는 뜻일 뿐**, 그 부분이
     진짜 손잡이인지는 보장하지 않는다 → 부착 후 **반드시 스크린샷으로 손잡이가 손에 왔는지
     눈으로 검증**한다(이 스크립트는 검증용 렌더를 자동 생성한다).

사용:
  blender -b <character.blend> -P attach_weapon.py -- \
      --weapon <mesh_name_or_keyword> --bone mixamorig:RightHand \
      [--scale 1.0] [--ref-height 0.8759] [--rot 0,0,0] \
      [--grip-zmin 38 --grip-zmax 47] [--out <out.blend>] [--shot-dir /tmp] [--no-shot]

성공 시 stdout 에 `####ATTACH_OK ... grip_to_hand=<d> tip_to_hand=<d>` + `####SHOT <png>` 출력.
**tip_to_hand 가 grip_to_hand 보다 충분히 커야**(칼끝이 손에서 멀어야) 손잡이를 쥔 것이다.
"""
import bpy, sys, math, argparse
from mathutils import Vector, Matrix, Euler

HEAD_KEYS = ("head", "Head")
FOOT_KEYS = ("foot", "toe", "Foot", "Toe")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--weapon", required=True, help="무기 메시 이름(정확) 또는 키워드(부분일치)")
    p.add_argument("--bone", default="mixamorig:RightHand", help="장착 손 본(방패/왼손은 mixamorig:LeftHand)")
    p.add_argument("--scale", type=float, default=1.0, help="무기 추가 스케일")
    p.add_argument("--ref-height", type=float, default=0.0, help=">0 이면 캐릭터 키/ref 비율로 auto_scale")
    p.add_argument("--rot", default="0,0,0", help="무기 로컬 회전 보정 deg 'X,Y,Z'(검신 방향이 어색할 때)")
    p.add_argument("--grip-zmin", type=float, default=None, help="grip 정점 긴축 좌표 하한(미지정=자동)")
    p.add_argument("--grip-zmax", type=float, default=None, help="grip 정점 긴축 좌표 상한(미지정=자동)")
    p.add_argument("--out", default=None, help="저장 경로(미지정=현재 .blend 덮어쓰기)")
    p.add_argument("--shot-dir", default="/tmp", help="검증 스크린샷 저장 폴더")
    p.add_argument("--no-shot", action="store_true", help="검증 스크린샷 생략(권장하지 않음)")
    return p.parse_args(argv)


def get_armature():
    a = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if not a:
        raise SystemExit("####ATTACH_FAIL armature 없음")
    return a


def find_weapon(name):
    o = bpy.data.objects.get(name)
    if o and o.type == "MESH":
        return o
    cand = [o for o in bpy.data.objects if o.type == "MESH" and name.lower() in o.name.lower()]
    if len(cand) == 1:
        return cand[0]
    raise SystemExit(f"####ATTACH_FAIL 무기 메시 미발견/모호: {name!r} 후보={[c.name for c in cand]}")


def char_height(arm):
    names = set(arm.pose.bones.keys())
    hb = next((n for n in names if any(k in n for k in HEAD_KEYS)), None)
    fbs = [pb for pb in arm.pose.bones
           if any(k in pb.name for k in FOOT_KEYS)
           and "ik" not in pb.name.lower() and "ctrl" not in pb.name.lower()]
    if not hb or not fbs:
        return None
    hz = (arm.matrix_world @ arm.pose.bones[hb].head).z
    fz = min((arm.matrix_world @ pb.head).z for pb in fbs)
    return abs(hz - fz)


def long_axis(obj):
    vs = obj.data.vertices
    ext = [max(v.co[i] for v in vs) - min(v.co[i] for v in vs) for i in range(3)]
    return ext.index(max(ext))


def section_profile(obj, axis, N=24):
    """긴축을 N 구간으로 나눠 각 구간의 두 부축 폭과 round ratio(원형도) 반환.
    round = min(w0,w1)/max(w0,w1). 칼날(납작)~0.4, 손잡이(원통)~0.9."""
    vs = obj.data.vertices
    other = [i for i in range(3) if i != axis]
    co = [v.co[axis] for v in vs]
    lo, hi = min(co), max(co)
    span = hi - lo if hi > lo else 1.0
    cols = [[1e9, -1e9, 1e9, -1e9] for _ in range(N)]
    for v in vs:
        b = min(N - 1, max(0, int((v.co[axis] - lo) / span * N)))
        c = cols[b]
        c[0] = min(c[0], v.co[other[0]]); c[1] = max(c[1], v.co[other[0]])
        c[2] = min(c[2], v.co[other[1]]); c[3] = max(c[3], v.co[other[1]])
    rnd = []
    for c in cols:
        w0 = c[1] - c[0]; w1 = c[3] - c[2]
        rnd.append(min(w0, w1) / max(w0, w1) if max(w0, w1) > 1e-6 else 0.0)
    return lo, hi, span, rnd


def auto_grip_range(obj, axis):
    """손잡이 = 긴축 한쪽 끝의 *원형 단면(round>0.65)* 연속 구간. 칼날(납작)은 제외된다.
    양 끝 round 평균이 높은 쪽을 손잡이 끝으로 보고, 그 절반에서 원통 구간을 grip 으로 잡는다."""
    lo, hi, span, rnd = section_profile(obj, axis)
    N = len(rnd)
    q = max(1, N // 4)
    lo_r = sum(rnd[:q]) / q
    hi_r = sum(rnd[-q:]) / q
    THRESH = 0.65
    if hi_r >= lo_r:
        bins = [b for b in range(N) if rnd[b] > THRESH and b >= N // 2]
    else:
        bins = [b for b in range(N) if rnd[b] > THRESH and b < N // 2]
    if not bins:   # 원통이 뚜렷하지 않으면(예: 막대형) 끝 단면적 작은 쪽 반대를 grip 으로 fallback
        other = [i for i in range(3) if i != axis]
        vs = obj.data.vertices

        def cross(zlo, zhi):
            pts = [v for v in vs if zlo <= v.co[axis] <= zhi]
            if not pts:
                return 0.0
            a = [v.co[other[0]] for v in pts]; b2 = [v.co[other[1]] for v in pts]
            return (max(a) - min(a)) * (max(b2) - min(b2))
        lo_tip = cross(lo, lo + span * 0.25); hi_tip = cross(hi - span * 0.25, hi)
        return (lo + span * 0.55, lo + span * 0.85) if lo_tip < hi_tip else (lo + span * 0.15, lo + span * 0.45)
    bmn, bmx = min(bins), max(bins)
    return (lo + bmn / N * span, lo + (bmx + 1) / N * span)


def centroid(obj, axis, zmin, zmax, world=True):
    pts = [(obj.matrix_world @ v.co) if world else v.co
           for v in obj.data.vertices if zmin <= v.co[axis] <= zmax]
    if not pts:
        raise SystemExit("####ATTACH_FAIL grip 정점 0개 - grip-z 범위 확인")
    return sum(pts, Vector((0, 0, 0))) / len(pts)


def clear_skin(obj):
    mw = obj.matrix_world.copy()
    for m in list(obj.modifiers):
        if m.type == "ARMATURE":
            obj.modifiers.remove(m)
    if obj.parent:
        obj.parent = None
    obj.matrix_world = mw
    while obj.vertex_groups:
        obj.vertex_groups.remove(obj.vertex_groups[0])


def skin(obj, arm, bone):
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = arm
    obj.matrix_parent_inverse = arm.matrix_world.inverted()
    obj.matrix_world = mw
    vg = obj.vertex_groups.new(name=bone)
    vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    m = obj.modifiers.new("WeaponRig", "ARMATURE")
    m.object = arm


def deformed_centroid(obj, axis, zmin, zmax):
    deps = bpy.context.evaluated_depsgraph_get()
    oe = obj.evaluated_get(deps)
    me = oe.to_mesh()
    pts = [oe.matrix_world @ me.vertices[i].co
           for i, v in enumerate(obj.data.vertices) if zmin <= v.co[axis] <= zmax]
    c = sum(pts, Vector((0, 0, 0))) / len(pts) if pts else None
    oe.to_mesh_clear()
    return c


def render_check(arm, weapon, bone, out_dir):
    """검증용 렌더: 전신 정면 + 손 클로즈업. 손잡이가 손에 왔는지 *눈으로* 확인하기 위함.
    (grip_to_hand 거리만으론 칼날을 grip 으로 오인했을 때 못 잡는다.)"""
    import os
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass
    cam = scene.camera
    if cam is None:
        cd = bpy.data.cameras.new("ChkCam")
        cam = bpy.data.objects.new("ChkCam", cd)
        scene.collection.objects.link(cam)
        scene.camera = cam
    # 캐릭터 전신 중심·키
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render]
    zs = []
    for o in meshes:
        for c in o.bound_box:
            zs.append((o.matrix_world @ Vector(c)).z)
    cz = (min(zs) + max(zs)) / 2 if zs else 0.5
    center = Vector((0.0, 0.0, cz))
    pb = arm.pose.bones[bone]
    hand = (arm.matrix_world @ pb.matrix).translation
    scene.render.resolution_x = 700
    scene.render.resolution_y = 800
    paths = []

    def shot(eye, target, name):
        cam.location = Vector(eye)
        cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
        p = os.path.join(out_dir, name)
        scene.render.filepath = p
        bpy.ops.render.render(write_still=True)
        paths.append(p)

    span = max(max(zs) - min(zs), 1.0) if zs else 1.0
    shot((center.x, center.y - span * 2.4, center.z + 0.05), center, "attach_check_front.png")
    # 손 클로즈업(손 쪽으로 접근, 손이 화면 왼/오 어디든 hand 좌표 사용)
    side = -1.0 if hand.x < 0 else 1.0
    shot((hand.x + side * 0.30, hand.y - 0.65, hand.z + 0.12), hand, "attach_check_hand.png")
    return paths


def main():
    a = parse_args()
    arm = get_armature()
    w = find_weapon(a.weapon)
    if a.bone not in arm.data.bones:
        raise SystemExit(f"####ATTACH_FAIL 본 없음: {a.bone}")

    auto = 1.0
    if a.ref_height > 1e-6:
        ch = char_height(arm)
        if ch:
            auto = ch / a.ref_height
    total = a.scale * auto

    clear_skin(w)

    if abs(total - 1.0) > 1e-6:
        w.scale = [s * total for s in w.scale]
        # matrix_world 는 depsgraph 평가 결과라 scale 대입만으론 갱신되지 않는다. 여기서 갱신하지
        # 않으면 아래 --rot 의 `w.matrix_world = w.matrix_world @ E` 가 *구* matrix(스케일 반영 전)
        # 를 읽어 되쓰면서 방금 준 scale 을 조용히 덮어쓴다(= --rot 과 --scale 을 같이 주면 --scale
        # 이 무시됨). 실측 회귀 2026-07-28 titan.
        bpy.context.view_layer.update()
    rx, ry, rz = [math.radians(float(t)) for t in a.rot.split(",")]
    if any((rx, ry, rz)):
        w.matrix_world = w.matrix_world @ Euler((rx, ry, rz), "XYZ").to_matrix().to_4x4()
    bpy.context.view_layer.update()

    axis = long_axis(w)
    if a.grip_zmin is not None and a.grip_zmax is not None:
        zmin, zmax = a.grip_zmin, a.grip_zmax
    else:
        zmin, zmax = auto_grip_range(w, axis)
    grip = centroid(w, axis, zmin, zmax)
    hand = arm.matrix_world @ arm.data.bones[a.bone].head_local
    w.matrix_world = Matrix.Translation(hand - grip) @ w.matrix_world

    skin(w, arm, a.bone)
    bpy.context.view_layer.update()

    # 검증 측정: 손잡이 중심은 손에, 칼끝은 손에서 멀어야(손잡이를 쥔 증거)
    gc = deformed_centroid(w, axis, zmin, zmax)
    lo = min(v.co[axis] for v in w.data.vertices)
    hi = max(v.co[axis] for v in w.data.vertices)
    far_end = lo if abs(((zmin + zmax) / 2) - hi) < abs(((zmin + zmax) / 2) - lo) else hi
    tip = deformed_centroid(w, axis, far_end - abs(hi - lo) * 0.06, far_end + abs(hi - lo) * 0.06) \
        if far_end == hi else deformed_centroid(w, axis, far_end - abs(hi - lo) * 0.06, far_end + abs(hi - lo) * 0.06)
    pb = arm.pose.bones[a.bone]
    hp = (arm.matrix_world @ pb.matrix).translation
    grip_d = (gc - hp).length if gc else -1.0
    tip_d = (tip - hp).length if tip else -1.0

    # --- 무기 크기 적정성(반드시 점검): 변형 후 무기 월드 길이 vs 캐릭터 키 비율 ---
    # 무기는 캐릭터 키에 비례한 "적절한 크기"여야 한다. ref-height/scale 없이 기본값(1.0)으로
    # 두면 무기가 캐릭터에 비해 거대/왜소해도 grip/tip 검증은 통과해 *조용히* 어색한 크기가 남는다.
    # → 항상 비율을 측정·출력하고, 적정 범위를 벗어나면 ####ATTACH_SIZE_WARN 으로 재조정을 강제한다.
    deps = bpy.context.evaluated_depsgraph_get()
    oe = w.evaluated_get(deps); me2 = oe.to_mesh()
    bmn = [1e18, 1e18, 1e18]; bmx = [-1e18, -1e18, -1e18]
    for v in me2.vertices:
        p = oe.matrix_world @ v.co
        for i in range(3):
            if p[i] < bmn[i]: bmn[i] = p[i]
            if p[i] > bmx[i]: bmx[i] = p[i]
    oe.to_mesh_clear()
    weapon_len = max(bmx[i] - bmn[i] for i in range(3))
    chh = char_height(arm) or 0.0
    size_ratio = (weapon_len / chh) if chh > 1e-6 else -1.0

    if a.out:
        bpy.ops.wm.save_as_mainfile(filepath=a.out)
    else:
        bpy.ops.wm.save_mainfile()

    print(f"####ATTACH_OK weapon={w.name!r} bone={a.bone} long_axis={axis} "
          f"grip_z=[{zmin:.2f},{zmax:.2f}] auto_scale={auto:.3f} total_scale={total:.3f} "
          f"grip_to_hand={grip_d:.4f} tip_to_hand={tip_d:.4f}")
    if tip_d >= 0 and grip_d >= 0 and tip_d < grip_d + 0.05:
        print("####ATTACH_WARN tip 이 손에 가깝다 - 칼날을 쥐었을 수 있음. grip-z 범위/스크린샷 확인!")

    # 무기 크기 비율 보고 + 적정 범위 가드(반드시 확인). 권장 비율(무기 길이 / 캐릭터 키):
    #   단검 0.25~0.35 · 한손검 0.45~0.65 · 대검 0.70~0.95 · 창/지팡이 0.90~1.20
    print(f"####ATTACH_SIZE weapon_len={weapon_len:.4f} char_height={chh:.4f} "
          f"weapon_to_char={size_ratio:.2f}")
    if size_ratio > 1.05:
        print(f"####ATTACH_SIZE_WARN 무기가 캐릭터 키의 {size_ratio*100:.0f}% — 너무 큼. "
              f"--ref-height(무기 프로파일 키) 또는 --scale 로 *줄여* 재실행하라 "
              f"(권장: 단검 0.25~0.35 · 한손검 0.45~0.65 · 대검 0.70~0.95 · 창/지팡이 0.90~1.20).")
    elif 0 < size_ratio < 0.20:
        print(f"####ATTACH_SIZE_WARN 무기가 캐릭터 키의 {size_ratio*100:.0f}% — 너무 작음. "
              f"--scale 로 *키워* 재실행하라.")

    if not a.no_shot:
        for p in render_check(arm, w, a.bone, a.shot_dir):
            print(f"####SHOT {p}")


if __name__ == "__main__":
    main()
