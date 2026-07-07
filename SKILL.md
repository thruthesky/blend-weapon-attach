---
name: blend-weapon-attach
description: >-
  Blender .blend 파일 안에 이미 들어있는 무기 메시(칼·검·총·지팡이·방패)를 캐릭터의 손 본
  (mixamorig:RightHand 등)에 정확히 장착한다. 무기의 실제 손잡이(grip) 정점 중심을 손 본 head 에
  실측 정렬(grip-align)하여 손잡이가 팔뚝이 아닌 손에 정확히 오게 하고, 손 본 vertex group 100%
  weight + Armature modifier 스키닝으로 붙여 FBX/GLB export·스프라이트 시트·애니메이션에서도 손을
  따라가게 한다(본 패런팅 금지 — export 시 사라짐). 장착 시 무기 크기는 *반드시* 캐릭터 키에
  비례하게 scale 하고 weapon_to_char 비율로 검증한다(거대/왜소하면 재조정 강제). 다음 경우 사용:
  (1) "이 무기를/칼을/검을 캐릭터 손에 장착/착용/들려줘", (2) ".blend 의 무기가 손에 안 붙는다·손잡이가
  팔뚝에 박힌다·무기가 손에서 떴다", (3) "무기를 오른손/왼손 본에 스키닝", (4) sword.fbx 등 무기 메시를
  female.blend·male.blend 등 캐릭터에 부착. 트리거 키워드 — 무기 장착, 칼 장착, 검 장착, weapon attach,
  손에 들려, grip, 손잡이, RightHand, .blend 무기, 무기 스키닝.
metadata:
  author: laryen
  version: "1.2"
---

# .blend 무기 손 장착

`.blend` 안의 무기 메시를 캐릭터 손 본에 **grip-align(손잡이 실측 정렬) + 스키닝**으로 붙인다.

## 핵심 원칙 (먼저 읽을 것)

0. **한 .blend = 캐릭터 1개 + 무기 1개 (필수 전제).** 이 스킬은 캐릭터 1개와 무기 1개가 *같은
   .blend 파일 안에* 함께 들어 있는 것을 **전제**로 한다. **양손 무기(쌍검 등)일 때만 무기가 2개**일
   수 있다. 따라서 무기를 외부 파일에서 *따로 찾지 않고*, 같은 .blend 안에 들어 있는 무기 메시를
   그대로 사용한다. 무기 메시는 *캐릭터 몸 파트가 아닌 메시*(예: `tripo_part_*` 외의 메시)로
   식별한다. (만약 .blend 안에 무기가 없다면 전제 위반이므로, import 하지 말고 사용자에게 알린다.)

1. **본 패런팅 금지.** `Parent->Bone`(`parent_type='BONE'`)은 Blender 안에선 따라가지만
   FBX/GLB **export 시 사라진다.** 반드시 **손 본 이름의 vertex group(100% weight) + Armature
   modifier** 스키닝으로 붙인다(몸 메시와 동일 방식 = export 보존 + rigid follow).
2. **손잡이는 실측 정렬.** `sword.json` 류 `loc` 오프셋은 기준 캐릭터에만 맞아 다른 캐릭터에선
   손잡이가 팔뚝에 박힌다. 무기의 실제 **grip 정점 중심**을 손 본 head 에 직접 맞춘다(거리 0.0).
3. **rest head 기준.** grip-align 은 `bones[bone].head_local`(rest)에 맞춘다 — 스키닝이 그걸
   현재 pose 손으로 옮긴다. 측정만 pose 기준(`pose.bones`).

4. 🛑 **반드시 *원본* `.blend` 에서 직접 작업한다 (ABSOLUTE — 복사본/백업본 작업 금지).**
   무기 장착은 *원본 캐릭터 `.blend`* 를 열어 그 안에서 수행하고, `--out` 을 *원본 경로* 로 지정해
   **원본을 곧바로 덮어쓴다**. **별도 백업본(`*.pre-weapon.blend`·`*_copy.blend`·`*-bak.blend` 등)을
   만들어 거기서 작업하지 않으며, 이미 백업본이 있어도 그쪽이 아니라 *원본* 에 장착·저장한다.** 이유:
   ① 부착이 틀려도 스크립트가 *기존 부착을 자동 해제* 하므로 옵션만 바꿔 *원본에* 재실행하면 되고,
   ② `.blend` 는 git 으로 언제든 되돌릴 수 있어 백업 파일이 불필요하며, ③ 복사본에서 작업하면
   *원본과 갈라져* 어느 파일이 최신인지 혼란·유실이 생긴다(원본이 항상 유일한 진실이어야 한다).
   GUI Blender 가 원본을 열어둔 채 헤드리스로 작업했다면, 작업 후 GUI 를 `revert` 해 원본과 동기화한다.

5. 🛑 **무기 크기는 *반드시* 캐릭터 키에 맞춰 적절히 scale 한다 (ABSOLUTE — 절대 생략 금지).**
   grip-align(손잡이가 손에 옴)이 맞아도 *무기 크기*가 캐릭터에 비해 거대/왜소하면 결과는 어색하다
   (실측 회고: skeleton 해골 로봇에 대검을 기본값 scale 1.0 으로 붙였더니 검 길이가 캐릭터 키의
   ~100% 라 비정상적으로 컸다). **장착할 때마다 무기 길이 / 캐릭터 키 비율(`weapon_to_char`)을
   반드시 확인하고, 무기 종류에 맞는 적정 범위로 scale 한다:**

   | 무기 종류 | 권장 `weapon_to_char`(무기 길이 / 캐릭터 키) |
   |---|---|
   | 단검(dagger) | 0.25 ~ 0.35 |
   | 한손검·도끼·둔기 | 0.45 ~ 0.65 |
   | 대검(greatsword)·대형 무기 | 0.70 ~ 0.95 |
   | 창·지팡이·장병기 | 0.90 ~ 1.20 |

   - 크기를 맞추는 **1순위 수단은 `--ref-height`**(무기 프로파일 기준 키 → 캐릭터 키 비율로 자동 보정).
     `game-assets/weapons/<weapon>.json` 의 `ref_height` 사용. 프로파일이 없으면 첫 실행의
     `####ATTACH_SIZE weapon_to_char=...` 출력을 보고 **`--scale (목표비율 ÷ 현재비율)`** 로 재실행한다.
   - 스크립트가 `####ATTACH_SIZE_WARN`(비율 >1.05 거대 / <0.20 왜소)을 내면 **반드시 재조정 후
     재실행**한다 — 경고를 무시한 채 마무리하지 않는다.

6. 🛑 **스프라이트 시트는 *반드시* 무기를 부착한 *`.blend`* 에서 렌더한다 — *exported `.fbx`* 가
   아니다 (ABSOLUTE — 실측 회고 2026-06-18 victor + fantasy sword).**
   `.blend` 안에서 부착이 *완벽해도*(검증 스샷 OK·grip_to_hand≈0·follow-test 통과), **그 `.blend`
   를 FBX 로 export 한 사본(`game-assets/characters/<name>.fbx`)에서는 무기 스킨이 *조용히 깨질 수
   있다*.** 원인: 무기는 *사후*(post-hoc) 스키닝이라 mixamo armature 의 0.01 스케일을 보정하는
   `matrix_parent_inverse`(대각 ×100)를 갖는데, **FBX export 가 이 bind-pose 보정을 잘못 굽는다** →
   재import 하면 무기의 `matrix_parent_inverse` 가 identity 로 죽고, 애니를 적용해도 **무기가
   *전혀* 안 움직인다**(몸은 정상 애니, 무기만 그 자리에 *고정·분리*). 몸 메시는 *원본 리그에서*
   스키닝돼 export 에 살아남지만 *사후 부착 무기* 는 안 살아남는다.
   - **그래서 해법은 *시트 렌더의 `--character` 를 `.fbx` 가 아니라 무기 부착 `.blend` 로 지정*** 하는
     것이다. 라리엔 시트 렌더러(`_sheet_preview_render.py`/`_sheet_render.py`)는 `.blend` 캐릭터를
     *통째로 열어*(`open_mainfile`) 본에 스키닝된 무기를 그대로 따라가게 한다 — FBX 재export 불필요.
     `_sheet_config*.json` 의 `"character"` 를 `…/blender/<name>.blend` 로 바꿔 재렌더한다.
   - **`grip_to_hand≈0` 과 검증 스샷만으로 "끝" 이라 하지 않는다.** 그 둘은 *`.blend` 정적 1프레임*
     의 증거일 뿐, *export 후 애니 적용 시 무기가 손을 따라가는지* 는 보장하지 않는다. 부착 직후
     **follow-test**(애니 1개를 armature 에 적용 → 무기 *변형 정점 중심* 이 손과 함께 움직이는지
     측정; 움직임≈0 이면 분리)로 *최종 산출물 경로(시트가 읽는 파일)* 를 검증한다 — 자세한 진단
     스크립트는 [references/attach-weapon.md §8](references/attach-weapon.md#8-export-후-무기-분리-fbx-skin-깨짐-진단--해법).

## 빠른 경로 (대부분 이걸로 끝 — 먼저 시도)

캐릭터 1 + 무기 1 전제(§0)라, **무기명만 자동 식별하면 거의 기본 인자로 끝난다**(grip 자동 추정이
대개 맞음). 손 본은 mixamo 표준 `mixamorig:RightHand`(왼손/보조는 LeftHand).
**단, 무기 크기 검증(§핵심원칙 5)은 빠른 경로에서도 생략하지 않는다.**

1. 무기 메시명 자동 식별 — 위 [파악 §1](#1-파악) 의 한 줄(`tripo_part_*` 아닌 메시).
2. 기본 장착(무기 프로파일이 있으면 `--ref-height` 를 *처음부터* 함께 준다):
   ```bash
   blender -b <character.blend> -P .claude/skills/blend-weapon-attach/scripts/attach_weapon.py -- \
     --weapon <자동식별명> --bone mixamorig:RightHand [--ref-height <프로파일 키>] --out <character.blend>
   ```
3. 다음 **세 가지를 모두** 확인해야 끝난다:
   - `####ATTACH_OK ... grip_to_hand≈0 tip_to_hand≫0` (손이 *손잡이* 를 쥠)
   - `####ATTACH_SIZE ... weapon_to_char=<비율>` 이 무기 종류 적정 범위(§핵심원칙 5 표) 안 + `SIZE_WARN` 없음
   - 검증 스샷(손이 손잡이를 쥐고 **무기 크기가 캐릭터에 비례**)
   **하나라도 어긋나면** §2 옵션으로 재조정·재실행한다(기존 부착 자동 해제):
   grip 틀림→`--grip-zmin/zmax`, 방향 어색→`--rot`, **크기 어긋남→`--ref-height`/`--scale`**.
4. 🛑 **시트를 새로 뽑는다면, 시트 렌더의 캐릭터는 *이 `.blend`* 로 지정한다(§핵심원칙 6)** —
   `<name>.fbx` 가 아니다. FBX 사본은 사후 부착 무기 스킨이 깨져 *시트에서 무기가 손과 분리* 된다.

> **실측 성공 예** (`female_parts_rig.blend` 대검, 485K verts): `--weapon tripo_node_c832a3a7
> --bone mixamorig:RightHand` **기본값만으로** `long_axis=1 grip_z=[37.5,50] grip_to_hand=0.0000
> tip_to_hand=1.1730` 한 번에 성공. 고폴리여도 칼 — 정점 수로 캐릭터라 단정 말 것.

## 워크플로우

### 1) 파악
- 캐릭터 `.blend` 안의 armature, **손 본 이름**(보통 `mixamorig:RightHand`, 방패·보조무기는
  `mixamorig:LeftHand`), **무기 메시 이름**을 확인한다.
- **무기 메시는 같은 .blend 안에 이미 들어 있다(핵심 원칙 §0 — 캐릭터 1 + 무기 1 필수 전제).**
  외부에서 무기를 *따로 찾지 않는다.* 무기는 *캐릭터 몸 파트 명명 규칙이 아닌 메시*이므로, 아래
  한 줄로 **자동 식별**한다(laryen tripo3d 캐릭터는 몸이 `tripo_part_*`, 무기는 그 외 메시 1개 —
  양손 무기면 2개):
  ```bash
  blender -b <character.blend> --python-expr "import bpy;print('WEAPON=',[o.name for o in bpy.data.objects if o.type=='MESH' and not o.name.startswith('tripo_part_')])"
  ```
  (무기가 *캐릭터 메시에 합쳐져 export 깨짐*을 고치는 경우만 예외로 `weapon-attach` 스킬을 쓴다 —
  §차이는 [references/attach-weapon.md](references/attach-weapon.md#7-weapon-attach-스킬과의-차이).)
- 무기가 칼인지 캐릭터인지 헷갈리면(고폴리 검은 수십만 verts 일 수 있음) **렌더로 직접 확인**한다.
  정점 수만으로 "캐릭터"라 단정하지 말 것(실측: 485K verts 메시가 대검이었음).
- **메시 목록에 캐릭터·무기 외 *잡동사니*(default `Cube` 8 verts 등)가 있으면 부착·렌더 전에
  삭제**한다 — framing 을 망가뜨리고 프레임을 회색으로 채운다(§함정 참조).

### 2) 장착 (둘 중 하나)

**(a) 헤드리스 1커맨드** — 결정론적, 재사용:
```bash
blender -b <character.blend> -P .claude/skills/blend-weapon-attach/scripts/attach_weapon.py -- \
  --weapon <무기메시명> --bone mixamorig:RightHand [--ref-height 0.8759] [--scale 1.0] \
  [--rot 0,0,0] [--grip-zmin 3 --grip-zmax 13] [--out <out.blend>]
```
`####ATTACH_OK ... grip_to_hand=<dist>` 가 나오고 dist 가 0 에 가까우면 성공. `####ATTACH_FAIL`
이면 멈추고 인자(무기명·본·grip 범위)를 점검한다.

**(b) MCP execute** — Blender 가 떠 있어 파일을 열어둔 채 작업·렌더 검증할 때. 핵심 코드는
[references/attach-weapon.md §5](references/attach-weapon.md#5-mcp-execute-로-직접-실행).

옵션 의미:
- `--ref-height`: 이 값(>0)이면 캐릭터 키 / ref 비율로 무기 auto_scale(작은 캐릭터엔 작게).
  laryen 무기 프로파일 기준은 `game-assets/weapons/<weapon>.json` 의 `ref_height`.
- `--scale`: 무기가 너무 크/작을 때 추가 배율.
- `--rot X,Y,Z`(deg): 검신 방향이 어색할 때(위로/앞으로) 보정.
- `--grip-zmin/zmax`: grip 자동 추정이 틀릴 때 긴축 로컬 좌표로 직접 지정.

### 3) 검증 (필수 — grip 위치 + 무기 크기 둘 다, 거리만 믿지 말 것)
스크립트는 부착 후 **검증 스크린샷을 자동 생성**한다(`####SHOT <png>` 로 경로 출력:
전신 정면 `attach_check_front.png` + 손 클로즈업 `attach_check_hand.png`). 다음을 모두 확인한다:
- **(위치)** `grip_to_hand` < 0.02 **그리고** `tip_to_hand` 가 그보다 충분히 큼(칼끝이 손에서 멀어야
  손잡이를 쥔 것). `####ATTACH_WARN tip 이 손에 가깝다` 가 뜨면 **칼날을 쥔 것** = 실패.
- **(크기 — 필수)** `####ATTACH_SIZE ... weapon_to_char=<비율>` 이 무기 종류 적정 범위(§핵심원칙 5 표:
  단검 0.25~0.35 · 한손검 0.45~0.65 · 대검 0.70~0.95 · 창/지팡이 0.90~1.20) 안에 있고
  `####ATTACH_SIZE_WARN` 이 **없어야** 한다. 비율이 범위 밖이거나 WARN 이 뜨면 **무기가 거대/왜소** =
  미완성. `--ref-height`(1순위) 또는 `--scale (목표비율÷현재비율)` 로 *반드시 재조정 후 재실행*한다.
- **(시각)** **자동 생성된 `attach_check_hand.png` + `attach_check_front.png` 를 Read 로 직접 열어**
  ① 손이 *손잡이(grip)* 를 쥐고 칼날이 바깥으로 뻗는지, ② **무기 크기가 캐릭터에 비례**하는지
  *눈으로* 확인한다. `grip_to_hand=0` 은 "내가 grip 이라 *식별한* 부분"이 손에 왔다는 뜻일 뿐,
  진짜 손잡이인지·크기가 적절한지는 **스크린샷으로만** 안다(칼날을 grip 으로 오인하면 거리 0 이어도
  칼날이 손등에 박히고, scale 을 안 맞추면 검이 캐릭터만큼 거대해도 거리는 0 — 둘 다 실제 회귀).
- 칼날이 손에 왔으면 단면 프로파일([references/attach-weapon.md](references/attach-weapon.md) §2.1)로
  손잡이의 긴축 좌표 구간을 확인해 `--grip-zmin/zmax` 로 직접 지정하고 재실행한다(스크립트는 기존
  부착을 자동 해제하므로 반복 안전). 검신 방향이 어색하면 `--rot`, 크기가 어긋나면 `--ref-height`/`--scale` 조정.

## 함정 (시간 낭비 회피)

- **grip_to_hand 거리 0 ≠ 손잡이를 쥠.** 손잡이를 *잘못 식별*(칼날을 grip 으로)하면 거리 0 이어도
  칼날이 손등에 박힌다(실제 회귀). 손잡이는 **단면적이 아니라 원형 단면(round ratio≈0.9 원통)** 으로
  식별한다(칼날은 납작 round~0.45). 그리고 **반드시 자동 스크린샷으로 시각 검증**하며,
  `tip_to_hand` 가 `grip_to_hand` 보다 충분히 커야 한다(칼끝이 손에서 멀어야 손잡이를 쥔 것).
- **🛑 grip 위치가 맞아도 *무기 크기* 가 안 맞으면 미완성(자주 놓침).** scale 옵션 없이 기본값(1.0)
  으로 붙이면 grip/tip 검증은 통과해도 무기가 캐릭터에 비해 거대/왜소할 수 있다(실측 회귀: skeleton
  해골 로봇에 대검을 scale 1.0 으로 붙였더니 검 길이가 캐릭터 키의 ~100%). **장착마다 `weapon_to_char`
  비율을 보고 무기 종류 적정 범위(§핵심원칙 5)로 맞춘다.** `####ATTACH_SIZE_WARN` 은 *반드시* 재조정한다.
- **🛑 복사본/백업본이 아니라 *원본* `.blend` 에서 작업한다(§핵심원칙 4).** 백업본을 만들어 거기 장착하면
  원본과 갈라져 최신본 혼란·유실이 생긴다. 무기 장착은 *원본* 을 열어 *원본에* 저장하고(`--out` =원본 경로),
  되돌림이 필요하면 백업 파일이 아니라 **git** 으로 한다. (색칠 등 다른 작업의 백업 관행과 혼동 금지.)
- 스키닝은 **object origin 을 안 옮긴다.** follow 검증은 `object.matrix_world` 가 아니라
  **변형(evaluated) 정점 중심**으로 측정한다(안 그러면 거짓 음성).
- tripo3d+mixamo 캐릭터는 **rest pose ≠ 보이는 자세**일 수 있다(rest 손이 바닥 근처). grip-align
  은 rest head 기준이어야 스키닝 후 손에 온다.
- mixamo armature 의 0.01 스케일 때문에 무기를 본 좌표계 행렬에 직접 끼우면 100배 축소된다.
  평행이동(grip-align)으로 푸는 게 안전하다.
- **🛑 `.blend` 에선 완벽한데 *시트에선 무기가 손과 분리* 되는 회귀 = FBX export 가 사후 부착 무기
  스킨을 깬 것(§핵심원칙 6).** 실측(2026-06-18 victor + fantasy sword): `.blend` 에서 애니 적용 시
  무기 변형 정점 중심이 손과 함께 **0.40 이동**(follow), 그러나 같은 모델의 `victor.fbx` 에선 애니를
  적용해도 **손 0.000 / 무기 0.000 이동**(완전 정지·분리). FBX 의 무기 `matrix_parent_inverse` 가
  ×100 보정을 잃고 identity 로 죽은 것이 원인. **해법은 무기를 재부착하는 게 아니라 *시트 렌더를
  `.blend` 에서* 하는 것.** `.blend` 부착이 맞는데 시트만 깨지면 *반드시 시트 `--character` 가
  `.fbx` 를 가리키는지부터* 확인한다.
- **잡동사니 메시(default `Cube` 등)는 부착·렌더 전에 정리한다.** import/제작 과정에서 남은 기본
  큐브(2×2×2, 8 verts)가 `.blend` 에 있으면 ① 시트 framing 의 bbox 를 지배해 캐릭터가 셀 안에서
  *작아지거나*, 큐브가 카메라를 가려 *프레임이 통째로 회색* 으로 나온다(실측: victor 의 잔여 Cube 가
  brighten 프리뷰와 첫 시트 렌더를 회색으로 채움). ② 머티리얼이 있으면 "머티리얼 없는 헬퍼 제거"
  컬링도 안 걸린다. 부착 전 `[o.name for o in bpy.data.objects if o.type=='MESH']` 로 확인해
  캐릭터·무기 외 메시를 삭제한다.

전체 개념·로직·소스코드·함정은 [references/attach-weapon.md](references/attach-weapon.md).
