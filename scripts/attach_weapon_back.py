#!/usr/bin/env python3
"""Blender `.blend` 안의 무기를 캐릭터 **등(back)** 에 비스듬히 메어 준다.

    blender -b <character.blend> -P attach_weapon_back.py -- [옵션]

`attach_weapon.py` 가 *손* 에 쥐여 주는 것이라면, 이 스크립트는 *등에 멘* 상태
(칼끝 아래·자루가 어깨 위로 솟음)를 만든다. 행동별 모델(idle/walk 은 등에 멘 모델,
attack 은 손에 쥔 모델)로 한 시트를 굽는 라리엔 규약에 쓰인다.

## 손 장착과 무엇이 다른가

| | 손(`attach_weapon.py`) | 등(이 스크립트) |
|---|---|---|
| 본 | `mixamorig:RightHand` | `mixamorig:Spine2`(등 상부) |
| 자세 기준 | 내장 *파지 프레임*(잘 붙은 캐릭터에서 추출) | **캐릭터 해부 축에서 매번 계산** |
| 깊이 | 손이 정해 줌 | **등 표면을 실측해 자동 이격**(파고들지 않게) |

등 장착에는 "잘 붙은 참조 캐릭터" 가 필요 없다. 어깨·목·척추 본과 몸 메시
표면만 있으면 되고, 그 값들이 곧 캐릭터마다 자동으로 맞는 자세를 만든다.

## 자세를 정하는 3개 값 (모두 캐릭터 키 비례라 체형이 달라도 이식된다)
- `--pommel-up`   : 자루끝 높이(Spine2 head 기준, 캐릭터 키 비율). 기본 0.20 → 머리 옆
- `--pommel-side` : 자루끝 좌우(어깨 관절 = 1.0). 기본 1.0 → 어깨 바로 위
- `--tilt`        : 수직에서 기운 각도. 기본 14.5도 (자루=위쪽 어깨, 칼끝=반대쪽 골반)

## 깊이(등에서 얼마나 떨어지나)는 계산하지 않고 **실측** 한다
몸 메시를 (좌우, 상하) 격자로 훑어 등 표면 높이맵을 만들고, 무기 정점이 그
표면보다 `--gap` 만큼 뒤에 오도록 통째로 밀어낸다. 어깨뼈·갑옷 돌출·해골 가드
두께를 전부 흡수하므로 **어떤 캐릭터·어떤 무기든 파고들지 않는다**.
🛑 계산은 *rest*(기본자세) 좌표에서 한다 — 스키닝이 rest 기준으로 걸리기 때문.

## 성공 판정 (4개 모두)
- `####BACK_OK`     : `min_gap` 이 `--gap` 근처(양수) · `plane_dot_back` ≈ 1.0(칼날 면이 등과 평행)
- `####BACK_SIZE`   : `weapon_to_char` 가 무기 종류 적정 범위
- `####FOLLOW_OK`   : 척추를 굽혀도 무기가 등에 강체 고정(bone_frame_drift ≈ 0)
- `####SHOT`        : 🛑 PNG 를 Read 로 **직접 열어 눈으로** 확인(뒷모습·옆모습)
"""
import bpy, sys, os, math, argparse
import numpy as np
from mathutils import Vector, Matrix, Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weapon_geom as wg
from attach_weapon import clear_attachment, skin, deformed_world, SIZE_BANDS

CELL = 0.01           # 등 표면 높이맵 격자 크기(월드 단위)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--weapon", default=None, help="무기 메시 이름(생략=자동 식별)")
    p.add_argument("--bone", default="mixamorig:Spine2", help="장착 본(등 상부)")
    p.add_argument("--side", choices=("left", "right"), default="left",
                   help="자루가 솟는 어깨. left=캐릭터의 왼쪽 어깨(뒤에서 보면 오른쪽)")
    p.add_argument("--tilt", type=float, default=14.5, help="수직에서 기운 각도(도)")
    p.add_argument("--pommel-up", type=float, default=0.20,
                   help="자루끝 높이 — Spine2 head 기준 캐릭터 키 비율")
    p.add_argument("--pommel-side", type=float, default=1.0,
                   help="자루끝 좌우 — 어깨 관절 위치를 1.0 으로 한 배율")
    p.add_argument("--sink", type=float, default=0.024,
                   help="가장 두꺼운 부위가 몸에 묻혀도 되는 깊이(캐릭터 키 비율). "
                        "0=무기가 몸에 전혀 안 묻음(대신 칼날이 뜬다), 음수=일부러 띄움")
    p.add_argument("--flip-face", action="store_true", help="칼날 앞/뒷면을 뒤집는다")
    p.add_argument("--ratio", type=float, default=None,
                   help="목표 무기길이/캐릭터키. 생략하면 현재 크기 유지")
    p.add_argument("--out", default=None, help="저장 경로(생략=원본 덮어쓰기)")
    p.add_argument("--dry", action="store_true", help="저장하지 않고 수치만")
    p.add_argument("--shot-dir", default=None, help="검증 스샷 폴더(생략=.blend 옆)")
    p.add_argument("--no-shot", action="store_true", help="검증 렌더 생략(권장하지 않음)")
    p.add_argument("--no-follow-test", action="store_true", help="follow-test 생략(권장하지 않음)")
    return p.parse_args(argv)


# --------------------------------------------------------------------------- 해부 축
def anatomy(arm, posed=False):
    """캐릭터의 (좌·상·후) 직교 축을 본에서 구한다.

    🛑 월드 축(X/Y/Z)을 그대로 쓰면 안 된다 — 이 프로젝트의 캐릭터는 아마추어
    오브젝트 행렬에 축 교환이 들어 있어 월드 up 이 -Y 인 파일도 있다(실측
    male_vector). 본으로부터 유도하면 파일이 어떻게 놓여 있든 항상 맞는다.

    🛑 **rest 와 posed 가 다를 수 있다**(실측 male_vector: rest 는 누워 있고
    액션이 90도 세운다 — 두 축이 90도 차이). *배치* 는 스키닝 기준인 rest 로,
    *검증 렌더 카메라* 는 실제로 보이는 posed 로 계산해야 한다. 섞으면 배치는
    맞는데 렌더만 엉뚱한 각도로 나와 멀쩡한 결과를 실패로 오판한다.
    """
    AW = arm.matrix_world
    B = arm.pose.bones if posed else arm.data.bones

    def head(n):
        return AW @ (B[n].head if posed else B[n].head_local)

    def tail(n):
        return AW @ (B[n].tail if posed else B[n].tail_local)

    pre = "mixamorig:"
    up = (head(pre + "Neck") - head(pre + "Hips")).normalized()
    left = (head(pre + "LeftShoulder") - head(pre + "RightShoulder"))
    left = (left - up * left.dot(up)).normalized()
    back = up.cross(left).normalized()
    # 발끝은 *앞* 을 향하므로 back 과 반대여야 한다. 같으면 축이 뒤집힌 것.
    fwd = (tail(pre + "LeftToe_End") - head(pre + "LeftFoot")).normalized()
    if back.dot(fwd) > 0:
        back = -back
        left = -left
    return up, left, back


def body_mesh(weapon):
    """스키닝된 몸 메시 = 무기가 아니면서 vertex group 이 가장 많은 메시."""
    ms = [o for o in bpy.data.objects if o.type == "MESH" and o is not weapon]
    if not ms:
        raise SystemExit("####BACK_FAIL body mesh not found")
    return max(ms, key=lambda o: len(o.vertex_groups))


def rest_world(obj):
    """오브젝트의 **rest**(변형 전) 정점 월드 좌표. 배치 계산은 rest 에서 한다."""
    co = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
    obj.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    MW = np.array(obj.matrix_world)
    return co @ MW[:3, :3].T + MW[:3, 3]


class BackSurface:
    """몸의 등 표면을 (좌우, 상하) 격자 높이맵으로 만든 것.

    각 칸에 그 칸에서 **가장 뒤로 튀어나온** 지점의 back 좌표를 담는다.
    3x3 최대 팽창(dilate)을 걸어 격자 경계에서 표면을 얕게 보는 일을 막는다.
    """

    EMPTY = -1e9

    def __init__(self, pts, origin, left, up, back):
        d = pts - np.array(origin)
        self.L = d @ np.array(left)
        self.U = d @ np.array(up)
        self.B = d @ np.array(back)
        self.l0, self.u0 = self.L.min() - CELL, self.U.min() - CELL
        nl = int((self.L.max() - self.l0) / CELL) + 3
        nu = int((self.U.max() - self.u0) / CELL) + 3
        g = np.full((nu, nl), self.EMPTY)
        np.maximum.at(g, (self._i(self.U, self.u0), self._i(self.L, self.l0)), self.B)
        pad = np.full((nu + 2, nl + 2), self.EMPTY)
        pad[1:-1, 1:-1] = g
        self.grid = np.maximum.reduce([pad[a:a + nu, b:b + nl]
                                       for a in range(3) for b in range(3)])
        self.nu, self.nl = nu, nl

    @staticmethod
    def _i(v, o):
        return ((v - o) / CELL).astype(int)

    def sample(self, L, U):
        """무기 정점 (L,U) 위치의 몸 표면 back 값. 몸이 없는 칸은 EMPTY."""
        i, j = self._i(U, self.u0), self._i(L, self.l0)
        ok = (i >= 0) & (i < self.nu) & (j >= 0) & (j < self.nl)
        out = np.full(len(L), self.EMPTY)
        out[ok] = self.grid[i[ok], j[ok]]
        return out


# --------------------------------------------------------------------------- 배치
def place(w, H, g, S, grip_local, R, s, grip_world_pos):
    """무기를 '손잡이 중심이 grip_world_pos 에 오도록' 회전 R·스케일 s 로 놓는다."""
    grip_H = H.inverted() @ grip_world_pos
    w.matrix_world = H @ (Matrix.Translation(grip_H)
                          @ (R @ Matrix.Diagonal(Vector((s, s, s)))).to_4x4()
                          @ Matrix.Diagonal(S).to_4x4()
                          @ Matrix.Translation(-grip_local))
    bpy.context.view_layer.update()


def follow_test(arm, w, bone):
    """척추를 크게 굽혀 무기가 등에 **강체** 로 붙어 있는지 본다.

    🛑 액션을 잠시 떼었다가 **반드시 되돌린다** — 안 되돌리면 저장 시 이 파일의
    애니메이션 연결이 통째로 사라진다(idle 모델은 포즈가 곧 자산이다).
    """
    ad = arm.animation_data
    keep = (ad.action, getattr(ad, "action_slot", None)) if ad else None
    if ad:
        ad.action = None

    def sample():
        bpy.context.view_layer.update()
        Bw = arm.matrix_world @ arm.pose.bones[bone].matrix
        c = Vector(deformed_world(w).mean(axis=0))
        return Bw.translation.copy(), c, Bw.inverted() @ c

    h0, c0, b0 = sample()
    pre = bone.rsplit(":", 1)[0] + ":" if ":" in bone else ""
    posed = []
    for bn, ang, ax in (("Spine", 22, "X"), ("Spine1", 18, "Z"), ("Spine2", 15, "X")):
        pb = arm.pose.bones.get(pre + bn)
        if not pb:
            continue
        pb.rotation_mode = "QUATERNION"
        v = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[ax]
        pb.rotation_quaternion = Quaternion(v, math.radians(ang))
        posed.append(pre + bn)
    if not posed:
        print("####FOLLOW_SKIP no spine bones to pose")
        return
    h1, c1, b1 = sample()
    for n in posed:
        arm.pose.bones[n].rotation_quaternion = Quaternion((1, 0, 0, 0))
    if keep:
        ad.action = keep[0]
        if keep[1] is not None and hasattr(ad, "action_slot"):
            ad.action_slot = keep[1]
    bpy.context.view_layer.update()

    dh, dw, drift = (h1 - h0).length, (c1 - c0).length, (b1 - b0).length
    print("####FOLLOW spine_moved=%.4f weapon_moved=%.4f bone_frame_drift=%.6f" % (dh, dw, drift))
    if dh < 0.005 and dw < 0.005:
        print("####FOLLOW_INCONCLUSIVE spine barely moved")
    elif dw < dh * 0.3:
        print("####FOLLOW_FAIL weapon does not follow the back - check skinning")
    elif drift < 0.01:
        print("####FOLLOW_OK weapon rigid in bone frame")
    else:
        print("####FOLLOW_WARN bone_frame_drift=%.4f" % drift)


# --------------------------------------------------------------------------- 렌더
def purge_check_objects():
    """검증용 카메라·조명을 지운다(직전 실행이 남긴 것 포함).

    🛑 이것들이 **저장 파일에 남으면 안 된다** — 캐릭터 `.blend` 는 자산이지 씬이
    아니다. 시트 렌더러가 `.blend` 입력의 LIGHT/CAMERA 를 어차피 지우긴 하지만
    (`_sheet_render.py`), GUI 로 열었을 때 남은 조명이 보이고 파일만 지저분해진다.
    """
    gone = [o.name for o in bpy.data.objects if o.type in ("CAMERA", "LIGHT")]
    for o in list(bpy.data.objects):
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o, do_unlink=True)
    if gone:
        print("####SCENE_PURGE removed %s" % gone)


def setup_scene():
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "Standard"
        sc.display_settings.display_device = "sRGB"
    except Exception:
        pass
    world = sc.world or bpy.data.worlds.new("W")
    sc.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.16, 0.18, 0.22, 1.0)
    nt.links.new(bg.outputs[0], nt.nodes.new("ShaderNodeOutputWorld").inputs[0])
    purge_check_objects()
    cd = bpy.data.cameras.new("ChkCam")
    cd.clip_start, cd.clip_end = 0.001, 500.0
    cam = bpy.data.objects.new("ChkCam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam, cd


def render_check(arm, w, up, left, back, out_dir):
    """뒷모습·옆모습·3/4 뒷모습. 카메라는 **해부 축** 으로 세운다(월드 Z-up 가정 금지)."""
    sc, cam, cd = setup_scene()
    # 라이트도 해부 축 기준(캐릭터 뒤 위쪽에서)
    for vec, e in ((back * 1.0 + up * 0.8 - left * 0.6, 4.0),
                   (-back * 1.0 + up * 0.5 + left * 0.8, 2.2),
                   (up * -0.3 - back * 0.6, 1.2)):
        ld = bpy.data.lights.new("L", "SUN")
        ld.energy = e
        lo = bpy.data.objects.new("L", ld)
        sc.collection.objects.link(lo)
        lo.rotation_euler = (-vec).normalized().to_track_quat("-Z", "Y").to_euler()

    meshes = [o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render]
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in meshes:
        oe = o.evaluated_get(deps)
        pts += [oe.matrix_world @ Vector(c) for c in oe.bound_box]
    cen = sum(pts, Vector()) / len(pts)
    height = max(p.dot(up) for p in pts) - min(p.dot(up) for p in pts)
    sc.render.resolution_x, sc.render.resolution_y = 760, 1000

    def shot(view, name, target, ortho, dist=3.0):
        cd.type, cd.ortho_scale = "ORTHO", ortho
        cam.location = target + view.normalized() * dist
        z = view.normalized()                       # 카메라 -Z 가 피사체를 향함
        y = (up - z * up.dot(z)).normalized()
        x = y.cross(z)
        m = Matrix.Identity(3)
        for r in range(3):
            m[r][0], m[r][1], m[r][2] = x[r], y[r], z[r]
        cam.rotation_euler = m.to_euler()
        p = os.path.join(out_dir, name)
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        stat = ""
        try:
            tmp = os.path.join(out_dir, "_back_stat.png")
            bpy.data.images.get("Render Result").save_render(filepath=tmp)
            im = bpy.data.images.load(tmp)
            a = np.array(im.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
            stat = "mean=%.3f" % a.mean()
            bpy.data.images.remove(im)
            os.remove(tmp)
        except Exception:
            pass
        print("####SHOT %s %s" % (p, stat))

    torso = Vector(deformed_world(w).mean(axis=0))
    shot(back, "back_check_rear.png", cen, height * 1.05)
    shot((back * 2 + left).normalized(), "back_check_rear34.png", cen, height * 1.05)
    shot(-left, "back_check_side.png", cen, height * 1.05)
    shot((back * 2 - left * 1.2 + up * 0.5).normalized(), "back_check_closeup.png",
         torso, height * 0.55)


# --------------------------------------------------------------------------- main
def main():
    a = parse_args()
    arm = wg.find_armature()
    w = wg.find_weapon(a.weapon)
    if a.bone not in arm.data.bones:
        raise SystemExit("####BACK_FAIL no bone: %s" % a.bone)
    body = body_mesh(w)
    up, left, back = anatomy(arm)                       # 배치용(rest = 스키닝 기준)
    bpy.context.view_layer.update()
    pup, pleft, pback = anatomy(arm, posed=True)        # 카메라용(실제로 보이는 자세)
    if a.side == "right":
        left, pleft = -left, -pleft   # 자루가 솟는 쪽을 +left 로 통일
    if up.angle(pup) > math.radians(5):
        print("####POSE_NOTE rest and posed axes differ by %.0f deg - "
              "placing in rest, rendering in posed" % (up.angle(pup) * 57.2958))
    print("####WEAPON name=%r verts=%d body=%r bone=%s side=%s"
          % (w.name, len(w.data.vertices), body.name, a.bone, a.side))

    clear_attachment(w)
    smax_cur = max(abs(v) for v in w.matrix_world.to_scale())
    g = wg.analyze(w)
    S = g["S"]
    grip_local = wg.to_local(g["grip_c"], S)

    H = arm.matrix_world @ arm.data.bones[a.bone].matrix_local
    sH = max(abs(v) for v in H.to_scale())
    chh = wg.char_height(arm)
    s = (smax_cur / sH) if a.ratio is None else (a.ratio * chh) / (sH * g["length"])
    wlen = g["length"] * s * sH                       # 부착 후 무기 실제 길이(월드)

    # ---- 목표 자세: 자루끝=어깨 위, 칼끝=반대쪽 골반 ----
    th = math.radians(a.tilt)
    blade_dir = (-up * math.cos(th) - left * math.sin(th)).normalized()
    thin_dir = -back if a.flip_face else back        # 칼날 면 ∥ 등면
    O = arm.matrix_world @ arm.data.bones[a.bone].head_local
    sh = arm.matrix_world @ arm.data.bones["mixamorig:%sArm" % a.side.capitalize()].head_local
    shoulder_x = abs((sh - O).dot(left))
    pommel = (O + up * (a.pommel_up * chh)
              + left * (a.pommel_side * shoulder_x))
    # grip 중심은 자루끝에서 칼끝 방향으로 (grip 구간 중심까지) 떨어져 있다
    d_pommel = (g["t_hi"] - (g["t_gmin"] + g["t_gmax"]) / 2 if not g["grip_low"]
                else (g["t_gmin"] + g["t_gmax"]) / 2 - g["t_lo"]) * s * sH
    grip_pos = pommel + blade_dir * d_pommel

    # 🛑 R 은 **본 로컬(H) 공간** 에서 작동한다(월드가 아니다). 목표 방향을 월드
    # 그대로 넣으면 H 의 축 교환만큼 어긋나 칼이 거꾸로 선다(실측: blade_dot_down=-0.96).
    Hi3 = H.to_3x3().inverted()
    R = wg.basis((Hi3 @ blade_dir).normalized(), (Hi3 @ thin_dir).normalized()) \
        @ wg.basis(g["tip_c"] - g["grip_c"], g["thin"]).transposed()
    if R.determinant() < 0:
        raise SystemExit("####BACK_FAIL rotation det<0 (mirrored)")
    place(w, H, g, S, grip_local, R, s, grip_pos)

    # ---- 깊이: 등 표면을 실측해 통째로 밀어낸다(rest 좌표에서) ----
    # 🛑 무기 *전체* 가 몸에 안 닿게 밀면 **칼날이 등에서 뜬다** — 가장 두꺼운
    # 부위(장식 가드·해골)가 밀어내는 양만큼 얇은 칼날이 통째로 딸려 나오기
    # 때문이다(실측 male_vector: 해골 두께 7.2cm vs 칼날 1.4~4cm → 칼날이 3cm
    # 부양, 옆에서 보면 둥둥 뜬 티가 난다). 등에 멘 무기는 두꺼운 부위가 갑옷에
    # 살짝 묻히는 것이 정상이므로, "가장 깊은 곳이 몇 cm 묻혀도 되는가"(--sink)
    # 하나로 조절한다. 부위를 칼날/가드로 분류하는 방식은 쓰지 않는다 — 해골처럼
    # 가드 밖까지 두꺼운 장식이 있으면 분류 자체가 틀린다(실측).
    surf = BackSurface(rest_world(body), O, left, up, back)
    sw = rest_world(w) - np.array(O)
    SL, SU, SB = sw @ np.array(left), sw @ np.array(up), sw @ np.array(back)
    bs = surf.sample(SL, SU)
    hit = bs > surf.EMPTY / 2
    if not hit.any():
        raise SystemExit("####BACK_FAIL weapon does not overlap the body silhouette")
    push_strict = float(np.max(bs[hit] - SB[hit]))     # 어디도 안 묻는 최소 이동
    sink = a.sink * chh
    push = push_strict - sink
    print("####BACK_CLEAR push_strict=%.4f sink=%.4f push=%.4f" % (push_strict, sink, push))
    grip_pos = grip_pos + back * push
    place(w, H, g, S, grip_local, R, s, grip_pos)

    # ---- 부착 ----
    skin(w, arm, a.bone)
    bpy.context.view_layer.update()

    # ---- 수치 검증 (전부 rest 기준 = 배치를 계산한 좌표계) ----
    sw = rest_world(w) - np.array(O)
    SL, SU, SB = sw @ np.array(left), sw @ np.array(up), sw @ np.array(back)
    bs = surf.sample(SL, SU)
    hit = bs > surf.EMPTY / 2
    gap_v = SB[hit] - bs[hit]                            # 양수=몸에서 떨어짐, 음수=묻힘
    min_gap = float(np.min(gap_v))
    med_gap = float(np.median(gap_v))                    # 대표 이격(칼날이 등에서 뜬 정도)
    sunk_pct = float((gap_v < 0).mean() * 100)
    t = wg.t_values(w, g)
    pts_r = rest_world(w)
    gc = Vector(pts_r[(t >= g["t_gmin"]) & (t <= g["t_gmax"])].mean(axis=0))
    tipc = Vector(pts_r[np.abs(t - g["t_tip"]) <= g["span"] * 0.05].mean(axis=0))

    def lub(p):
        d = p - O
        return d.dot(left), d.dot(up), d.dot(back)

    gl, gu, gb = lub(gc)
    tl, tu, tb = lub(tipc)
    axis_w = (tipc - gc).normalized()
    # 칼날 면 법선(월드) = thin 축을 실제 배치 행렬로 보낸 것
    n_w = (w.matrix_world.to_3x3() @ wg.to_local(g["thin"], S)).normalized()
    print("####BACK_OK deepest_sink=%.4f median_gap=%.4f sunk_verts=%.1f%% push=%.4f "
          "tilt=%.1f plane_dot_back=%.4f blade_dot_down=%.4f"
          % (-min_gap, med_gap, sunk_pct, push, a.tilt, abs(n_w.dot(back)), axis_w.dot(-up)))
    print("####BACK_POSE grip(left=%+.4f up=%+.4f back=%+.4f) tip(left=%+.4f up=%+.4f back=%+.4f)"
          % (gl, gu, gb, tl, tu, tb))
    nk = (arm.matrix_world @ arm.data.bones["mixamorig:Neck"].head_local - O).dot(up)
    hp = (arm.matrix_world @ arm.data.bones["mixamorig:Hips"].head_local - O).dot(up)
    print("####BACK_LANDMARK neck_up=%+.4f hips_up=%+.4f shoulder_side=%.4f char_h=%.4f"
          % (nk, hp, shoulder_x, chh))
    ratio = wlen / chh
    print("####BACK_SIZE weapon_len=%.4f char_height=%.4f weapon_to_char=%.2f"
          % (wlen, chh, ratio))
    bands = " ".join("%s %s-%s" % (k, v[0], v[1]) for k, v in SIZE_BANDS.items())
    if ratio > 1.05 or 0 < ratio < 0.20:
        print("####BACK_SIZE_WARN %.0f%% of height - use --ratio (%s)" % (ratio * 100, bands))
    if med_gap > 0.030 * chh / 0.85:
        print("####BACK_WARN weapon floats %.1fcm off the back - lower --sink is not the fix, "
              "raise it" % (med_gap * 100))
    if sunk_pct > 25:
        print("####BACK_WARN %.0f%% of the weapon is inside the body - lower --sink" % sunk_pct)
    if abs(n_w.dot(back)) < 0.9:
        print("####BACK_WARN blade plane not parallel to the back")
    if axis_w.dot(-up) < 0.8:
        print("####BACK_WARN blade does not point downward")

    if not a.no_follow_test:
        follow_test(arm, w, a.bone)

    # 🛑 **저장이 먼저, 검증 렌더가 나중.** 렌더 준비(setup_scene)는 카메라·조명·
    # 월드·view_transform 을 갈아엎으므로, 렌더 뒤에 저장하면 그 씬 설정이 자산
    # 파일에 그대로 굳는다(실측: ChkCam+SUN 3개 + AgX→Standard + 월드색이 저장됨).
    if a.dry:
        print("####DRY not saved")
    else:
        path = a.out or bpy.data.filepath
        purge_check_objects()
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print("####SAVED %s" % path)
    if not a.no_shot:
        render_check(arm, w, pup, pleft, pback,
                     a.shot_dir or (os.path.dirname(bpy.data.filepath) or os.getcwd()))


if __name__ == "__main__":
    main()
