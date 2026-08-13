"""무기 지오메트리 분석 공용 모듈.

`attach_weapon.py`(부착)와 `extract_frame.py`(참조 프레임 추출)가 **같은 함수** 를 쓴다.
둘이 다른 정의를 쓰면 "참조의 grip" 과 "대상의 grip" 이 다른 것을 가리켜 파지 위치가 어긋난다.

## 두 가지 핵심 정의

### 1) 장축 = PCA(주성분), 카디널 축(local X/Y/Z) 아님
무기가 로컬 공간에서 비스듬히 놓여 있으면 카디널 축 가정은 완전히 틀린다.
실측(2026-08-13 male_vector): 검이 local XY 평면에서 **44.9도** 기울어 있어
카디널 최대 폭 98.08 vs 실제 길이 138.61 — **41% 과소측정**. 그 축으로 자른
단면 프로파일은 칼날과 손잡이가 뒤섞여 손잡이 판정이 통째로 무의미해진다.
정점 공분산의 최대 고유벡터를 쓰면 무기가 어떻게 놓여 있든 항상 진짜 장축이다.

### 2) 손잡이 = 끝단 ~ 가드(최대폭 단면) 사이
과거 방식인 **원형도(round ratio)** 판정은 양식화된 무기에서 자주 틀린다.
실측: codexian 검은 전 구간 round>0.7(단면이 거의 원형)이라 칼날을 손잡이로
잡았고, quantum 검은 칼날의 fuller(홈)가 round 0.81 로 튀어 손잡이로 오인됐다.
가드는 어떤 검이든 *가장 넓은 단면* 이라 훨씬 안정적이다.

### 보조: shape space
비균일 오브젝트 스케일(예: quantum 0.06/0.03546/0.03546)을 그대로 두고 계산하면
종횡비가 왜곡된다. 스케일 *비율만* 남긴 좌표계(shape space)에서 계산한 뒤
되돌리면 아티스트가 준 종횡비가 정확히 보존된다.
"""
import numpy as np
from mathutils import Vector, Matrix

N_BINS = 32
BODY_MESH_NAMES = {"human", "victor", "body"}


def shape_scale(obj):
    """오브젝트 스케일의 *비율* 만 남긴 벡터(최대성분=1). 종횡비 보존용."""
    s = [abs(v) for v in obj.scale]
    m = max(s) if max(s) > 1e-12 else 1.0
    return Vector((s[0] / m, s[1] / m, s[2] / m))


def _coords(obj, S):
    co = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
    obj.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3) * np.array([S[0], S[1], S[2]])


def analyze(obj):
    """무기를 분석해 dict 반환. 좌표/벡터는 모두 shape space 기준.

    반환 키: S(shape scale) · centroid · e1/e2/e3(주축) · t_lo/t_hi/span ·
    guard_bin · grip_low · t_gmin/t_gmax(손잡이 구간) · t_tip ·
    grip_c/tip_c(중심점) · thin(칼날 두께축) · length · blade_w/blade_t
    """
    S = shape_scale(obj)
    co = _coords(obj, S)
    c = co.mean(axis=0)
    X = co - c
    evals, evecs = np.linalg.eigh((X.T @ X) / len(X))
    evecs = evecs[:, np.argsort(evals)[::-1]]
    e1, e2, e3 = evecs[:, 0], evecs[:, 1], evecs[:, 2]

    t = X @ e1
    lo, hi = float(t.min()), float(t.max())
    span = hi - lo
    p2, p3 = X @ e2, X @ e3
    idx = np.clip(((t - lo) / span * N_BINS).astype(int), 0, N_BINS - 1)

    wide = np.zeros(N_BINS)
    for b in range(N_BINS):
        m = idx == b
        if m.any():
            wide[b] = float(p2[m].max() - p2[m].min())
    guard = int(np.argmax(wide))
    grip_low = guard < N_BINS / 2

    if grip_low:
        tgmin, tgmax = lo, lo + guard / N_BINS * span
    else:
        tgmin, tgmax = lo + (guard + 1) / N_BINS * span, hi

    gm = (t >= tgmin) & (t <= tgmax)
    grip_c = Vector(co[gm].mean(axis=0))

    t_tip = hi if grip_low else lo
    tm = np.abs(t - t_tip) <= span * 0.05
    tip_c = Vector(co[tm].mean(axis=0))

    bm = (t > tgmax) if grip_low else (t < tgmin)
    a2 = float(p2[bm].max() - p2[bm].min())
    a3 = float(p3[bm].max() - p3[bm].min())
    thin = Vector(e3 if a3 < a2 else e2)

    return {
        "S": S, "centroid": Vector(c),
        "e1": Vector(e1), "e2": Vector(e2), "e3": Vector(e3),
        "t_lo": lo, "t_hi": hi, "span": span,
        "guard_bin": guard, "grip_low": grip_low,
        "t_gmin": tgmin, "t_gmax": tgmax, "t_tip": t_tip,
        "grip_c": grip_c, "tip_c": tip_c, "thin": thin,
        "length": span, "blade_w": max(a2, a3), "blade_t": min(a2, a3),
    }


def t_values(obj, g):
    """각 정점의 장축 투영값 t (analyze 와 같은 좌표계). 검증용 정점 선택에 쓴다."""
    co = _coords(obj, g["S"])
    return (co - np.array(g["centroid"])) @ np.array(g["e1"])


def to_local(v, S):
    """shape space 벡터/점 -> 오브젝트 로컬."""
    return Vector((v[0] / S[0], v[1] / S[1], v[2] / S[2]))


def basis(u, n):
    """u(주축)·n(보조축)으로 직교정규 우수 좌표계(열벡터 e1,e2,e3)."""
    e1 = u.normalized()
    e3 = (n - e1 * n.dot(e1)).normalized()
    e2 = e3.cross(e1)
    M = Matrix.Identity(3)
    for r in range(3):
        M[r][0] = e1[r]; M[r][1] = e2[r]; M[r][2] = e3[r]
    return M


def char_height(arm):
    """머리 본 ~ 발 본 z 차이 = 캐릭터 키(무기 크기 비율의 분모)."""
    HEAD = ("head", "Head")
    FOOT = ("foot", "toe", "Foot", "Toe")
    hb = next(n for n in arm.pose.bones.keys() if any(k in n for k in HEAD))
    fbs = [pb for pb in arm.pose.bones if any(k in pb.name for k in FOOT)
           and "ik" not in pb.name.lower() and "ctrl" not in pb.name.lower()]
    return abs((arm.matrix_world @ arm.pose.bones[hb].head).z
               - min((arm.matrix_world @ pb.head).z for pb in fbs))


def find_armature():
    import bpy
    a = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if not a:
        raise SystemExit("####ATTACH_FAIL armature 없음")
    return a


def find_weapon(name=None):
    """무기 메시 자동 식별: 몸 메시가 아니고 vertex group 이 적은(<=2) 메시.

    이미 부착된 무기는 손 본 vertex group 1개만 갖고, 몸은 50개 이상이라
    이 기준으로 갈린다. 후보가 여럿이면 정점이 가장 많은 것을 고른다.
    """
    import bpy
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if name:
        o = bpy.data.objects.get(name)
        if not o or o.type != "MESH":
            cand = [m for m in meshes if name.lower() in m.name.lower()]
            if len(cand) != 1:
                raise SystemExit(f"####ATTACH_FAIL 무기 메시 미발견/모호: {name!r} "
                                 f"후보={[c.name for c in cand]}")
            return cand[0]
        return o
    cands = [o for o in meshes if o.name not in BODY_MESH_NAMES and len(o.vertex_groups) <= 2]
    if not cands:
        cands = [o for o in meshes if o.name not in BODY_MESH_NAMES]
    if not cands:
        raise SystemExit("####ATTACH_FAIL 무기 메시 없음 — 캐릭터 1 + 무기 1 전제 위반")
    return max(cands, key=lambda o: len(o.data.vertices))
