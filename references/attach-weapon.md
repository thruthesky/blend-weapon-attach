# .blend 무기 손 장착 — 핵심 개념·로직·소스코드

`.blend` 파일 안에 이미 들어있는 무기 메시(칼·검·총·지팡이)를 캐릭터의 손 본에 장착하는
작업의 완전한 레퍼런스. 이 문서만으로 `scripts/attach_weapon.py` 전체를 재구성할 수 있다.

## 목차
1. [핵심 개념](#1-핵심-개념)
2. [핵심 로직](#2-핵심-로직)
3. [핵심 소스코드](#3-핵심-소스코드)
4. [실전 함정(시간 낭비 회피)](#4-실전-함정)
5. [MCP execute 로 직접 실행](#5-mcp-execute-로-직접-실행)
6. [검증 — 스크린샷 시각 확인 필수](#6-검증)
7. [weapon-attach 스킬과의 차이](#7-weapon-attach-스킬과의-차이)
8. [export 후 무기 분리(FBX skin 깨짐) 진단 + 해법](#8-export-후-무기-분리-fbx-skin-깨짐-진단--해법)

---

## 1. 핵심 개념

**목표**: 무기가 모든 애니메이션 프레임에서 손 본을 따라가야 하며, Blender 안에서뿐 아니라
FBX/GLB export 후(스프라이트 시트 렌더)에도 따라가야 한다.

**원칙 ① 스키닝만 export 에 보존된다.**
*Parent -> Bone*(`parent_type='BONE'`)은 Blender 안에선 따라가지만 **FBX/GLB export 시 사라진다.**
해결: 무기를 몸 메시와 같은 방식으로 — **손 본 이름의 vertex group(100% weight) + Armature
modifier** 로 바인딩. 단일 본 100% weight = 변형 없는 rigid follow, export 보존.

**원칙 ② 손잡이(grip)는 원형 단면으로 식별 + 실측 정렬.**
무기 origin 은 보통 중앙이라 그냥 손에 두면 손이 칼날 중간을 쥔다. `sword.json` 류 `loc` 오프셋은
기준 캐릭터에만 맞아 다른 캐릭터에선 손잡이가 팔뚝에 박힌다. 그래서 무기의 **실제 손잡이 정점
중심**을 손 본 head 에 직접 맞춘다. **단, 손잡이를 단면적(area)으로 찾으면 칼날을 손잡이로 오인한다**
(실제 회귀: 칼날이 손등에 박힘). 손잡이는 **원형 단면(round ratio = 짧은폭/긴폭 ≈ 0.9 원통)** 으로
식별한다 — 칼날은 납작(round ~0.45), 가드는 넓은 돌출, 손잡이만 원통이다.

**원칙 ③ 무기 크기는 *반드시* 캐릭터 키에 비례해야 한다(ABSOLUTE).** grip-align(손잡이가 손에 옴)이
맞아도 무기 *크기* 가 캐릭터에 비해 거대/왜소하면 결과는 어색하다. 프로파일 기준 키(`ref_height`)
대비 현재 캐릭터 키 비율을 곱해(auto_scale) 맞추고, 부착 후 **무기 길이 / 캐릭터 키 비율
(`weapon_to_char`)을 측정해 무기 종류 적정 범위 안인지 검증**한다(§2.3). 범위 밖이면 재조정 강제.

**원칙 ④ grip_to_hand 거리만으론 검증 불가.** "내가 grip 이라 *식별한* 부분"이 손에 왔다는 거리가
0 이어도, 그 부분이 칼날이면 칼날이 손에 온다. **반드시 스크린샷으로 시각 검증** + `tip_to_hand`
(칼끝~손 거리)가 `grip_to_hand` 보다 충분히 큰지 확인한다.

---

## 2. 핵심 로직

### 2.1 손잡이(grip) 정점 식별 — 원형도 기반

무기의 **가장 긴 로컬 축**(검신/총신 방향)을 구하고, 그 축을 N 구간으로 나눠 각 구간의 **두 부축 폭
비율 round = min(w0,w1)/max(w0,w1)** 을 본다.

| 부위 | round ratio | 단면적 |
|---|---|---|
| 칼날(blade) | ~0.4~0.5 (납작한 판) | 중간 |
| 가드(crossguard) | 낮음 | 최대(돌출) |
| **손잡이(grip)** | **~0.8~0.99 (원통)** | 작음 |
| 검끝(tip)·자루끝(pommel) | 끝에서 수렴 | 0 으로 |

손잡이 = 긴축 한쪽 끝의 **round > 0.65 인 원통 구간**. 양 끝 round 평균이 높은 쪽이 손잡이 끝이다.
원통이 뚜렷하지 않은 막대형 무기는 단면적이 작은 끝(=검끝/총구)의 *반대쪽* 끝을 grip 으로 fallback.
무기 형태가 특이하면 `--grip-zmin/zmax`(긴축 로컬 좌표)로 직접 지정한다.

> female 검 실측: long_axis=y(span 100). pos -48 검끝, pos -48~+13 칼날(round 0.45), pos 13~19
> 가드(area 최대 385), **pos 38~50 손잡이(round 0.76~0.99 원통)**, pos 50 pommel. 자동 식별 결과
> grip_z=[37.5,50.0] → grip_to_hand 0.0, tip_to_hand 0.556(칼끝이 멀어 손잡이를 쥔 것 확인).
> (초기 버전은 단면적만 봐서 grip_z=[5,35]=칼날을 잡아 칼날이 손등에 박혔다.)

### 2.2 grip-align

```
hand = arm.matrix_world @ arm.data.bones[bone].head_local   # rest 손 본 head(월드)
offset = hand - grip_centroid_world
weapon.matrix_world = Translation(offset) @ weapon.matrix_world   # 무기 전체 평행이동
```

**왜 rest head 인가**: 스키닝은 무기 정점에 `pose @ rest^-1` 본 델타를 적용한다. 무기를 *rest 손
위치*에 두면 modifier 가 *현재 pose 손*으로 옮긴다. 그래서 align 기준은 `bones[bone].head_local`
(rest)이고, 측정/검증만 pose 기준(`pose.bones`).

### 2.3 무기 크기 — auto_scale + weapon_to_char 비율 검증(반드시)

**개념**: 무기 크기는 캐릭터 키에 비례해야 한다. grip 위치가 맞아도 크기가 안 맞으면 미완성이다
(실측 회귀: skeleton 해골 로봇에 대검을 scale 1.0 으로 붙였더니 검 길이가 캐릭터 키의 ~100% 라
비정상적으로 컸다 — grip/tip 검증은 통과했지만 시각적으로 거대).

**(1) auto_scale — 키 비례 보정**
```
char_h = |head본 z - foot본 z| (pose, world);  auto_scale = char_h / ref_height (ref>0)
total_scale = weapon_scale * auto_scale;  weapon.scale = [s*total for s in weapon.scale]
```
`ref_height` = 무기 프로파일(`game-assets/weapons/<weapon>.json`)이 만들어진 기준 캐릭터 키.
프로파일이 없으면 auto_scale=1.0 이므로 *반드시* 아래 (2) 비율을 보고 `--scale` 로 맞춘다.

**(2) weapon_to_char 비율 측정 + 적정 범위 가드(부착 후 항상)**
변형(evaluated) 정점의 월드 bbox 긴축 길이 = 무기 길이. 캐릭터 키로 나눈 비율을 적정 범위와 비교.
```python
deps = bpy.context.evaluated_depsgraph_get(); oe = w.evaluated_get(deps); me = oe.to_mesh()
bmn=[1e18]*3; bmx=[-1e18]*3
for v in me.vertices:
    p = oe.matrix_world @ v.co
    for i in range(3):
        bmn[i]=min(bmn[i],p[i]); bmx[i]=max(bmx[i],p[i])
oe.to_mesh_clear()
weapon_len = max(bmx[i]-bmn[i] for i in range(3))     # 무기 월드 길이(긴축)
size_ratio = weapon_len / char_height(arm)            # weapon_to_char
```

| 무기 종류 | 권장 `weapon_to_char` |
|---|---|
| 단검(dagger) | 0.25 ~ 0.35 |
| 한손검·도끼·둔기 | 0.45 ~ 0.65 |
| 대검(greatsword)·대형 무기 | 0.70 ~ 0.95 |
| 창·지팡이·장병기 | 0.90 ~ 1.20 |

스크립트는 `####ATTACH_SIZE weapon_len=.. char_height=.. weapon_to_char=..` 를 항상 출력하고,
`size_ratio > 1.05`(거대) 또는 `< 0.20`(왜소)이면 `####ATTACH_SIZE_WARN` 을 낸다. WARN 이면
**반드시** `--ref-height`(1순위) 또는 `--scale (목표비율 ÷ 현재비율)` 로 재조정 후 재실행한다.

### 2.4 스키닝(rigid follow)
```
weapon.parent = arm                          # OBJECT parent (본 패런팅 아님!)
weapon.matrix_parent_inverse = arm.matrix_world.inverted()
vg = weapon.vertex_groups.new(name=bone); vg.add(all_indices, 1.0, 'REPLACE')   # 손 본 100%
weapon.modifiers.new("WeaponRig", 'ARMATURE').object = arm
```
순서: scale/rot -> grip-align -> skin.

---

## 3. 핵심 소스코드

전체는 [`../scripts/attach_weapon.py`](../scripts/attach_weapon.py). 핵심 함수:

```python
def long_axis(obj):
    vs = obj.data.vertices
    ext = [max(v.co[i] for v in vs) - min(v.co[i] for v in vs) for i in range(3)]
    return ext.index(max(ext))                     # 가장 긴 축 = 검신 방향

def section_profile(obj, axis, N=24):
    """긴축 N 구간의 round ratio(원형도). 칼날~0.45 / 손잡이~0.9."""
    vs = obj.data.vertices; other = [i for i in range(3) if i != axis]
    co = [v.co[axis] for v in vs]; lo, hi = min(co), max(co); span = hi - lo or 1.0
    cols = [[1e9,-1e9,1e9,-1e9] for _ in range(N)]
    for v in vs:
        b = min(N-1, max(0, int((v.co[axis]-lo)/span*N))); c = cols[b]
        c[0]=min(c[0],v.co[other[0]]); c[1]=max(c[1],v.co[other[0]])
        c[2]=min(c[2],v.co[other[1]]); c[3]=max(c[3],v.co[other[1]])
    rnd = [min(c[1]-c[0],c[3]-c[2])/max(c[1]-c[0],c[3]-c[2],1e-6) if c[1]>c[0] else 0 for c in cols]
    return lo, hi, span, rnd

def auto_grip_range(obj, axis):
    """손잡이 = 긴축 한쪽 끝의 round>0.65 원통 구간(칼날 제외)."""
    lo, hi, span, rnd = section_profile(obj, axis); N = len(rnd); q = max(1, N//4)
    lo_r = sum(rnd[:q])/q; hi_r = sum(rnd[-q:])/q
    if hi_r >= lo_r: bins = [b for b in range(N) if rnd[b] > 0.65 and b >= N//2]
    else:            bins = [b for b in range(N) if rnd[b] > 0.65 and b <  N//2]
    if not bins:     # 막대형 fallback: 가는 끝(tip)의 반대쪽
        # ... 단면적 비교(원본 코드 참조) ...
        return (lo+span*0.55, lo+span*0.85)
    bmn, bmx = min(bins), max(bins)
    return (lo + bmn/N*span, lo + (bmx+1)/N*span)

def centroid(obj, axis, zmin, zmax, world=True):
    pts = [(obj.matrix_world @ v.co) if world else v.co
           for v in obj.data.vertices if zmin <= v.co[axis] <= zmax]
    return sum(pts, Vector((0,0,0))) / len(pts)

def skin(obj, arm, bone):
    bpy.context.view_layer.update(); mw = obj.matrix_world.copy()
    obj.parent = arm; obj.matrix_parent_inverse = arm.matrix_world.inverted(); obj.matrix_world = mw
    vg = obj.vertex_groups.new(name=bone); vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    obj.modifiers.new("WeaponRig", "ARMATURE").object = arm

# grip-align 한 줄:
hand = arm.matrix_world @ arm.data.bones[bone].head_local
zmin, zmax = auto_grip_range(weapon, axis)        # 또는 --grip-zmin/zmax
weapon.matrix_world = Matrix.Translation(hand - centroid(weapon, axis, zmin, zmax)) @ weapon.matrix_world
```

`render_check(arm, weapon, bone, out_dir)` 는 부착 후 전신 정면 + 손 클로즈업을 EEVEE 로 렌더해
`attach_check_front.png` / `attach_check_hand.png` 를 저장한다(시각 검증용). 전체 코드는 스크립트 참조.

---

## 4. 실전 함정

1. **grip_to_hand 거리 0 ≠ 손잡이를 쥠(가장 중요).** 손잡이를 *잘못 식별*하면(칼날을 grip 으로)
   거리 0 이어도 칼날이 손등에 박힌다. **원형도(round ratio)로 손잡이를 식별**하고, **반드시
   스크린샷 시각 검증** + `tip_to_hand > grip_to_hand` 를 확인한다.
2. **rest pose ≠ 현재 자세.** tripo3d+mixamo 캐릭터는 rest 손이 엉뚱한 곳(예 world z=0.003)이고
   보이는 T-pose 손은 z≈0.55 다. grip-align 은 **rest head**(`bones[bone].head_local`)에 맞춰야
   스키닝 후 손에 온다. 측정만 pose 기준.
3. **스키닝은 object origin 을 안 옮긴다.** `object.matrix_world.translation` 으로 follow 측정 시
   거짓 음성. **변형(evaluated) 정점 중심**으로 측정한다(§6).
4. **0.01 스케일 회전 armature.** mixamo armature 의 `matrix_world` 는 0.01 스케일 + 축 교환 포함.
   무기를 본 좌표계 행렬에 직접 끼우면 100배 축소되니 평행이동(grip-align)으로 푼다.
5. **본 패런팅 절대 금지.** `Ctrl+P -> Bone` 는 Blender 안에선 맞아도 export 에서 사라진다.
6. **무기 크기 미조정(자주 놓침, grip 만 보다 빠뜨림).** `--scale`/`--ref-height` 없이 기본값(1.0)으로
   붙이면 grip/tip 거리 검증은 통과해도 무기가 캐릭터에 비해 거대/왜소할 수 있다(실측 회귀: skeleton
   해골 로봇 대검 `weapon_to_char≈1.0` 으로 검이 캐릭터 키만큼 컸다). 부착 후 `weapon_to_char`
   비율(§2.3)을 측정해 무기 종류 적정 범위로 맞추고, `####ATTACH_SIZE_WARN` 은 **반드시** 재조정한다.
7. **반드시 *원본* `.blend` 에서 작업(복사본/백업본 금지).** 무기 장착은 원본 캐릭터 `.blend` 를 열어
   `--out` =원본 경로로 *원본에 직접* 저장한다. 백업본(`*.pre-weapon.blend` 등)을 만들어 거기서 작업하면
   원본과 갈라져 최신본 혼란·유실이 생긴다(원본이 유일한 진실). 부착이 틀려도 스크립트가 기존 부착을
   자동 해제하므로 원본에 재실행하면 되고, 되돌림은 백업이 아니라 **git** 으로 한다. GUI 가 원본을
   열어둔 채 헤드리스로 작업했다면 작업 후 GUI 를 `bpy.ops.wm.revert_mainfile()` 로 동기화한다.

---

## 5. MCP execute 로 직접 실행

Blender 가 MCP 로 떠 있으면 헤드리스 CLI 대신 `mcp__blender__execute_blender_code` 로 같은 로직을
실행해도 된다(파일 열어둔 채 작업·렌더 검증에 유리). 핵심만:

```python
import bpy
from mathutils import Vector, Matrix
arm = next(o for o in bpy.data.objects if o.type=='ARMATURE')
w   = bpy.data.objects['<무기 메시>']; bone = 'mixamorig:RightHand'
# 스키닝 해제 -> (scale/rot) -> 손잡이(원형 단면) 구간 grip-align:
axis = 1                          # long_axis()로 구함(female 검은 y)
zmin, zmax = 38.0, 47.0           # auto_grip_range(원형도) 또는 단면 프로파일로 직접
grip = sum((w.matrix_world @ v.co for v in w.data.vertices if zmin<=v.co[axis]<=zmax), Vector())/N
hand = arm.matrix_world @ arm.data.bones[bone].head_local
w.matrix_world = Matrix.Translation(hand-grip) @ w.matrix_world
w.parent=arm; w.matrix_parent_inverse=arm.matrix_world.inverted()
vg=w.vertex_groups.new(name=bone); vg.add(list(range(len(w.data.vertices))),1.0,'REPLACE')
w.modifiers.new("WeaponRig",'ARMATURE').object=arm
bpy.ops.wm.save_mainfile()
# 그 다음 정면+손 클로즈업을 렌더해 Read 로 손잡이가 손에 왔는지 눈으로 확인(필수).
```

헤드리스 1커맨드(검증 스크린샷 자동 생성):
```bash
blender -b game-assets/blender/female.blend -P .claude/skills/blend-weapon-attach/scripts/attach_weapon.py -- \
  --weapon tripo_node_c832a3a7 --bone mixamorig:RightHand --ref-height 0.8759 --shot-dir /tmp
# -> ####ATTACH_OK ... grip_to_hand=0.0000 tip_to_hand=0.5557 / ####SHOT /tmp/attach_check_hand.png
```

---

## 6. 검증 — 스크린샷 시각 확인 필수

**거리 측정만으로는 부족하다(§4-1).** 두 가지를 모두 한다:

1. **수치**: 변형 정점 기준 `grip_to_hand` < 0.02 **그리고** `tip_to_hand`(칼끝~손)가 충분히 큼.
   스크립트가 `tip_to_hand < grip_to_hand + 0.05` 이면 `####ATTACH_WARN`(칼날을 쥔 의심)을 낸다.
```python
deps = bpy.context.evaluated_depsgraph_get(); oe = w.evaluated_get(deps); me = oe.to_mesh()
gpts = [oe.matrix_world @ me.vertices[i].co for i,v in enumerate(w.data.vertices) if zmin<=v.co[axis]<=zmax]
gc = sum(gpts, Vector())/len(gpts); oe.to_mesh_clear()
hp = (arm.matrix_world @ arm.pose.bones[bone].matrix).translation
assert (gc-hp).length < 0.02
```
2. **시각(필수)**: 스크립트가 자동 생성한 `attach_check_hand.png` 를 **Read 로 직접 열어** 손이
   *손잡이* 를 쥐고 칼날이 바깥으로 뻗는지 눈으로 확인한다. 칼날이 손에 왔으면(손등에 박힘)
   `--grip-zmin/zmax` 로 손잡이 구간을 직접 지정해 재실행한다. 검신 방향이 어색하면 `--rot` 보정.

이 시각 검증 단계를 건너뛰면 칼날을 손에 꽂은 채로 "성공(거리 0)"으로 오판한다 — 이 스킬이
원형도 식별 + 자동 스크린샷을 도입한 직접적 이유다.

---

## 7. weapon-attach 스킬과의 차이

| | `weapon-attach`(기존) | `blend-weapon-attach`(이 스킬) |
|---|---|---|
| 초점 | FBX/GLB **export** 시 무기가 안 깨지게(bone-parent->skinning 변환) | **.blend 안에서** 무기를 손에 직접 장착·검증 |
| grip | `--grip-mesh`(별도 손잡이 메시 지정) | **원형도(round) 자동 식별** + 수동(`--grip-zmin/max`) + 키 비례 |
| 검증 | export 자기검사 | **자동 스크린샷 + tip_to_hand**(칼날 오인 방지) |
| 주 산출물 | 재export 된 FBX | 무기 부착·저장된 `.blend` + 검증 PNG |
| 공통 | 스키닝(손 본 vgroup 100% + Armature modifier)으로 follow 보존 | 동일 |

---

## 8. export 후 무기 분리(FBX skin 깨짐) 진단 + 해법

> **회고 (2026-06-18, victor + fantasy sword).** `.blend` 안에서 부착이 *완벽* (grip_to_hand=0.0003,
> tip_to_hand=0.4391, 검증 스샷 OK) 했는데, *스프라이트 시트* 의 모든 프레임에서 검이 캐릭터 옆에
> *둥둥 떠 분리* 됐다. 원인은 부착 코드가 아니라 — **시트 렌더가 `.blend` 가 아닌 *export 된*
> `game-assets/characters/victor.fbx` 를 읽었고, 그 FBX 에서 사후 부착 무기의 스킨이 깨져 있었다.**

### 증상

- `.blend` 부착·검증은 전부 통과(거리 0, 스샷 OK).
- 그런데 시트 프레임에서 무기가 **한 곳에 고정** 된 채 캐릭터만 움직인다(걷기·피격·idle 전부 분리).
- 무기가 *틀어진* 게 아니라 *전혀 안 따라온다* → "스킨이 안 먹는다" 의 전형.

### 진단 — follow-test (`.blend` 와 `.fbx` 를 각각 측정해 비교)

부착 거리(grip_to_hand)는 *정적 1프레임* 증거일 뿐이다. **애니를 실제로 적용해 무기 *변형 정점
중심* 이 손과 함께 움직이는지** 를, *시트가 읽는 바로 그 파일* 에서 측정한다:

```python
# blender -b <FILE: .blend 또는 .fbx> -P follow_test.py
import bpy, math
from mathutils import Vector
# (.fbx 면 먼저 read_homefile(use_empty=True) 후 import_scene.fbx; .blend 면 그대로)
arm   = next(o for o in bpy.data.objects if o.type=='ARMATURE')
sword = bpy.data.objects.get('fantasy sword')      # 무기 메시명

def dc(o):                                          # 변형(evaluated) 정점 중심 — origin 아님!
    dg=bpy.context.evaluated_depsgraph_get(); oe=o.evaluated_get(dg); me=oe.to_mesh()
    c=sum((oe.matrix_world@v.co for v in me.vertices), Vector())/len(me.vertices)
    oe.to_mesh_clear(); return c
def hand():
    bpy.context.view_layer.update()
    return (arm.matrix_world @ arm.pose.bones['mixamorig:RightHand'].matrix).translation

for pb in arm.pose.bones: pb.matrix_basis.identity()
bpy.context.view_layer.update(); s0, h0 = dc(sword), hand()
# 같은 본 이름의 mixamo 애니 1개를 import 해 직접 적용(retarget 불필요)
bpy.ops.import_scene.fbx(filepath=r"…/animations/<rig>/walk.fbx", use_custom_props=False)
src = [a for a in bpy.data.actions][-1]
if arm.animation_data is None: arm.animation_data_create()
ad = arm.animation_data
ad.action = src
# 🛑 Blender 4.4+ 슬롯형 action: action 만 지정하면 *아무것도 안 움직인다*. slot 을 반드시
# 할당해야 한다(시트 렌더러 bind() 와 동일). 안 하면 hand_moved=0/sword_moved=0 의 *거짓*
# STATIC-DETACHED 가 나온다(실측 회고 2026-06-18 spike sword — slot 누락으로 오진).
if hasattr(ad, "action_suitable_slots"):
    s = ad.action_suitable_slots
    if s and getattr(ad, "action_slot", None) is None:
        ad.action_slot = s[0]
bpy.context.scene.frame_set(int(src.frame_range[0])+3); bpy.context.view_layer.update()
s1, h1 = dc(sword), hand()
print("hand_moved=%.3f sword_moved=%.3f"%((h1-h0).length,(s1-s0).length))
# hand_moved 가 0 이면 애니가 *아예 적용 안 된 것*(slot 누락/본 불일치) — 분리 판정 *전에*
# hand_moved>0 인지부터 확인한다. hand_moved>0 인데 sword_moved≈0 이라야 진짜 분리.
print("VERDICT",
      "NO-ANIM(slot/bone 확인)" if (h1-h0).length < 0.01
      else "FOLLOWS" if (s1-s0).length > 0.05 else "STATIC-DETACHED")
```

실측 결과:

| 파일 | 무기 `matrix_parent_inverse` 대각 | hand_moved | sword_moved | 판정 |
|---|---|---|---|---|
| `victor.blend` | **[100,100,100,1]** (0.01 스케일 보정) | 0.40 | 0.40 | **FOLLOWS** |
| `victor.fbx` (export 사본) | **[1,1,1,1]** (보정 죽음) | 0.000 | 0.000 | **STATIC-DETACHED** |

> 몸 메시(victor)는 *원본 리그에서* 스키닝돼 FBX 에도 살아남지만, *사후 부착 무기* 는 bind-pose
> 보정(×100 parent inverse)이 FBX export 에서 잘못 구워져 죽는다.

### 해법 — 시트를 `.blend` 에서 렌더

무기를 다시 붙이는 게 아니라, **시트 렌더의 입력을 `.fbx` → `.blend` 로 바꾼다.** 라리엔 시트
렌더러는 `.blend` 캐릭터를 통째로 열어(`open_mainfile`) 본 스키닝 무기를 그대로 따라가게 한다:

```jsonc
// outputs/<name>_preview/_sheet_config*.json
"character": "D:\\…\\game-assets\\blender\\victor.blend"   // ← .fbx 아님
```

그 뒤 `_sheet_preview_render.py`(또는 `sheet.py --character …/blender/<name>.blend`)로 재렌더하면
무기가 손을 따라간다. **검증은 시트 프레임 자체를 Read 로 열어** 무기가 손에 있는지 눈으로 확인한다
(idle·walk·hit·attack 등 여러 행동). FBX 경로를 고집할 이유가 없다 — `.blend` 가 항상 진실이다.

### 주의 — `.blend` 의 잡동사니 메시 정리

시트를 `.blend` 에서 렌더하기 *전에* 캐릭터·무기 외 메시(default `Cube` 등)를 지운다. 잔여 큐브가
있으면 framing bbox 를 지배하거나 카메라를 가려 **프레임이 통째로 회색** 으로 나온다(실측). 부착 전
`[o.name for o in bpy.data.objects if o.type=='MESH']` 로 확인 → 캐릭터·무기만 남기고 삭제.
