---
name: blend-weapon-attach
description: >-
  Blender .blend 파일 안에 이미 들어있는 무기 메시(칼·검·총·지팡이·방패)를 캐릭터의 손 본
  (mixamorig:RightHand 등)에 정확히 장착한다. 이미 올바르게 부착된 캐릭터에서 뽑은 *파지 프레임*
  (손잡이 위치·날 방향·날 두께축을 손 본 rest 좌표계로 표현)을 이식해 위치뿐 아니라 **방향까지**
  한 번에 맞추고, 손 본 vertex group 100% weight + Armature modifier 스키닝으로 붙여 FBX/GLB
  export·스프라이트 시트·애니메이션에서도 손을 따라가게 한다(본 패런팅 금지 — export 시 사라짐).
  장축은 PCA 로, 손잡이는 가드(최대폭 단면) 기준으로 판정해 검이 로컬 공간에서 기울어 있거나
  단면이 둥글어도 손잡이를 정확히 찾는다. 부착 후 수치·follow-test·렌더 스샷을 자동 검증한다.
  다음 경우 사용: (1) "이 무기를/칼을/검을 캐릭터 손에 장착/착용/들려줘", (2) ".blend 의 무기가
  손에 안 붙는다·손잡이가 팔뚝에 박힌다·무기가 손에서 떴다·검이 옆으로 누웠다", (3) "무기를
  오른손/왼손 본에 스키닝", (4) 아마추어를 교체해서 무기를 다시 붙여야 할 때, (5) 여러 캐릭터에
  같은 파지 자세로 무기를 일괄 장착, (6) 손이 아니라 **등에 메기**("무기를 등에 붙여줘",
  "칼을 등에 메게 해줘", 자루가 어깨 위로 솟고 칼끝이 아래로 — idle/walk 모델용) — 이때는
  `attach_weapon_back.py` 를 쓰고 척추 본(mixamorig:Spine2)에 스키닝하며, 몸 표면을 실측해
  파고들지 않게 자동 이격한다, (7) 손도 등도 아닌 **다리(허벅지)에 차기**("무기를 다리에
  붙여줘", "칼을 왼쪽 허벅지에 차게 해줘", 자루가 골반 옆·칼끝이 무릎 아래로) — 이때는
  `attach_weapon_leg.py` 를 쓰고 허벅지 본(mixamorig:LeftUpLeg/RightUpLeg)에 스키닝하며,
  다리 표면을 실측해 *칼날 면* 이 다리에 닿도록 앉힌다(가드 두께 때문에 칼날이 뜨는 것을 막는다).
  트리거 키워드 — 무기 장착, 칼 장착, 검 장착, weapon attach,
  재부착, reattach, 손에 들려, grip, 손잡이, RightHand, .blend 무기, 무기 스키닝, 파지,
  등에 메기, 등에 무기, back mount, sheathed, 어깨 위 자루, Spine2,
  다리에 차기, 허벅지 무기, 왼쪽 다리, 오른쪽 다리, leg mount, thigh, LeftUpLeg.
metadata:
  author: laryen
  version: "2.1"
---

# .blend 무기 손·등 장착

`.blend` 안의 무기 메시를 캐릭터 손 본에 **파지 프레임 이식 + 스키닝** 으로 붙인다.

## 빠른 경로 (거의 항상 이걸로 끝)

```bash
blender -b <character.blend> -P .claude/skills/blend-weapon-attach/scripts/attach_weapon.py --
```

**인자가 없어도 된다.** 무기 자동 식별 → 내장 파지 프레임으로 배치 → 스키닝 →
수치 검증 + follow-test + 검증 렌더 2컷까지 한 번에 하고 원본을 덮어쓴다.
크기는 **현재 크기를 그대로 유지** 한다(바꾸려면 `--ratio`).

여러 캐릭터를 돌릴 때:
```bash
for f in game-assets/characters/pc/male/*/*.blend; do
  blender -b "$f" -P .claude/skills/blend-weapon-attach/scripts/attach_weapon.py --
done
```

### 성공 판정 — 아래 4개를 *모두* 확인해야 끝난다
| 확인 | 기준 |
|---|---|
| `####ATTACH_OK` | `det=1.0000`(거울 반전 없음) · `grip_to_fist` < 0.05 · `tip_to_wrist` 가 그보다 훨씬 큼 |
| `####ATTACH_SIZE` | `weapon_to_char` 가 무기 종류 적정 범위 + `SIZE_WARN` 없음 |
| `####FOLLOW_OK` | 무기가 손에 강체 고정(bone_frame_drift ≈ 0) |
| `####SHOT` | 🛑 **PNG 를 Read 로 직접 열어 눈으로** 확인 — 수치만으로는 부족 |

하나라도 어긋나면 옵션을 바꿔 **원본에 그대로 재실행** 한다(스크립트가 기존 부착을 자동 해제).

## 옵션

| 옵션 | 용도 |
|---|---|
| `--ratio 0.8` | 무기 길이/캐릭터 키를 지정값으로. 생략하면 **현재 크기 유지** |
| `--flip-thin` | 칼날 면이 뒤집혀 보일 때(두께축 부호 반전) |
| `--ref frame.json` | 다른 파지 자세(왼손 등). `extract_frame.py` 로 만든다 |
| `--weapon NAME` | 자동 식별이 틀릴 때만 |
| `--bone mixamorig:LeftHand` | 방패·보조 무기 |
| `--dry` | 저장하지 않고 수치만 |
| `--out PATH` | 다른 경로로 저장(기본=원본 덮어쓰기) |

무기 종류별 권장 `weapon_to_char`:
단검 0.25~0.35 · 한손검/도끼/둔기 0.45~0.65 · 대검 0.70~0.95 · 창/지팡이 0.90~1.20

## 핵심 원칙

1. 🛑 **본 패런팅 금지.** `Parent->Bone`(`parent_type='BONE'`)은 Blender 안에선 따라가지만
   FBX/GLB **export 시 사라진다.** 반드시 **손 본 vertex group(100% weight) + Armature
   modifier** 스키닝으로 붙인다(몸 메시와 같은 방식 = export 보존 + rigid follow).

2. **파지는 '프레임 이식' 으로 맞춘다 — 평행이동만으로는 방향이 안 잡힌다.**
   grip 중심을 손 본 head 에 평행이동으로 붙이면 *위치* 는 맞아도 검이 옆으로 눕거나
   뒤를 향한다(구버전이 `--rot` 로 매번 눈대중 보정하던 이유). 이 스킬은
   **(grip 위치 · 날 방향 · 날 두께축)** 세 값을 *손 본 rest 좌표계* 로 표현한
   파지 프레임을 이식하므로 방향까지 한 번에 맞는다.
   - 프레임이 *손 본 로컬* 기준이라 **키·체형·아마추어가 바뀌어도 그대로 옮겨진다.**
     실측: 남녀 16종(키 0.83~0.87)에 같은 프레임을 써서 `grip_to_fist` 0.031~0.033 으로 일정.
   - 여러 캐릭터가 **완전히 같은 자세** 로 무기를 든다(감사 시 `grip_H`·`blade_dir_H` 가 일치).

3. 🛑 **장축은 PCA 로 찾는다 — local X/Y/Z 중 최대가 아니다.**
   무기가 로컬 공간에서 비스듬하면 카디널 축 가정은 통째로 틀린다.
   실측(male_vector): 검이 local XY 평면에서 **44.9도** 기울어 카디널 최대 폭 98.08 vs
   실제 길이 138.61 — **41% 과소측정**, 그 축의 단면 프로파일은 칼날·손잡이가 뒤섞여 무의미.

4. 🛑 **손잡이는 '가드(최대폭 단면) 기준' 으로 찾는다 — 원형도(round ratio)는 자주 틀린다.**
   실측: codexian 검은 전 구간 round>0.7(단면이 거의 원형)이라 칼날을 손잡이로 오검출,
   quantum 검은 칼날 fuller(홈)가 round 0.81 로 튀어 역시 오검출. 가드는 어떤 검이든
   *가장 넓은 단면* 이라 안정적이다. 손잡이 = 끝단 ~ 가드 구간, 그 중심이 주먹에 온다.

5. 🛑 **반드시 *원본* `.blend` 에서 작업한다 (복사본/백업본 금지).**
   `--out` 을 생략하면 원본을 덮어쓴다. 백업본을 만들어 거기 붙이면 원본과 갈라져
   최신본 혼란·유실이 생긴다. 되돌림은 백업 파일이 아니라 **git** 으로.
   GUI Blender 가 그 파일을 열어둔 채 헤드리스로 작업했다면 **작업 후 GUI 를 `revert`** 한다
   (안 하면 GUI 에서 저장하는 순간 이 작업이 통째로 날아간다).

6. **크기는 기본적으로 건드리지 않는다.** 아티스트가 준 스케일(비균일 포함)을 그대로 두고
   위치·방향만 고친다. 비율이 이상하면 `####ATTACH_SIZE_WARN` 이 뜨고, 그때만 `--ratio` 로 조정한다.
   비균일 스케일은 shape space 로 흡수해 **종횡비가 정확히 보존** 된다.

7. 🛑 **스프라이트 시트는 무기를 부착한 *`.blend`* 에서 렌더한다 — *exported `.fbx`* 가 아니다.**
   무기는 *사후* 스키닝이라 mixamo armature 의 0.01 스케일을 상쇄하는
   `matrix_parent_inverse`(대각 ×100)를 갖는데 **FBX export 가 이 bind-pose 보정을 잘못 굽는다**
   → 재import 하면 identity 로 죽어 **애니를 적용해도 무기만 그 자리에 고정·분리** 된다.
   몸 메시는 *원본 리그에서* 스키닝돼 살아남지만 사후 부착 무기는 안 살아남는다.
   해법은 재부착이 아니라 **시트 렌더의 `--character` 를 `.blend` 로 지정** 하는 것
   (`_sheet_config*.json` 의 `"character"`). `.blend` 는 멀쩡한데 시트만 깨지면
   *시트가 `.fbx` 를 가리키는지부터* 확인한다.

## 등에 메기 (칼끝 아래·자루가 어깨 위로)

손이 아니라 **등** 에 메는 것은 별도 스크립트다. 행동별 모델(idle/walk 은 등에 멘
모델, attack 은 손에 쥔 모델)로 한 시트를 굽는 규약에 쓴다.

```bash
blender -b <character.blend> -P .claude/skills/blend-weapon-attach/scripts/attach_weapon_back.py -- \
  --side right
```

**참조 캐릭터가 필요 없다.** 파지 프레임 대신 어깨·목·척추 본과 **몸 표면 실측** 에서
자세를 매번 계산하므로 체형이 달라도 그대로 맞는다. 본은 `mixamorig:Spine2`.

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--side right\|left` | left | 자루가 솟는 어깨. **오른손잡이 = `right`** |
| `--tilt` | 14.5 | 수직에서 기운 각도 |
| `--pommel-up` | 0.20 | 자루끝 높이(Spine2 head 기준·캐릭터 키 비율) |
| `--pommel-side` | 1.0 | 자루끝 좌우(어깨 관절=1.0) |
| `--sink` | 0.024 | 가장 두꺼운 부위가 몸에 묻혀도 되는 깊이(키 비율) |
| `--flip-face` | off | 칼날 앞/뒷면 뒤집기 |

성공 판정: `####BACK_OK`(`plane_dot_back`≈1 · `blade_dot_down`>0.8 · `deepest_sink`≈`--sink`) ·
`####BACK_SIZE` · `####FOLLOW_OK` · **스샷 4컷을 Read 로 직접 확인**(뒤·3/4·옆·클로즈업).

🛑 **`--sink` 를 0 으로 두지 마라 — 칼날이 등에서 뜬다.** 무기 전체를 안 닿게 밀면
*가장 두꺼운 부위*(장식 가드·해골)가 밀어내는 만큼 얇은 칼날이 통째로 딸려 나온다
(실측 male_vector: 해골 7.2cm vs 칼날 1.4~4cm → 칼날 3cm 부양, 옆에서 보면 떠 있는 티가 난다).
등에 멘 무기는 두꺼운 부위가 갑옷에 조금 묻히는 것이 정상이다.

🛑 **좌우를 뒤에서 본 그림으로 판단할 땐 주의** — *뒤에서* 보면 화면 오른쪽이 캐릭터의
**오른쪽** 이다(앞에서 볼 때만 좌우가 뒤집힌다). 참조 그림이 뒷모습이면 그대로 읽으면 된다.

## 다리(허벅지)에 차기 — 자루가 골반 옆·칼끝이 무릎 아래로

손도 등도 아닌 **허벅지 바깥면** 에 납작하게 차는 것은 또 다른 스크립트다.

```bash
blender -b <character.blend> -P .claude/skills/blend-weapon-attach/scripts/attach_weapon_leg.py -- \
  --side left
```

**참조 캐릭터가 필요 없다.** 등 장착과 같이 고관절·무릎 본과 **다리 표면 실측** 으로
매번 계산하며, 본은 `mixamorig:<Side>UpLeg`(허벅지)다. 무릎을 굽혀도 허벅지를 따라간다.

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--side left\|right` | left | 무기를 차는 다리(캐릭터 기준) |
| `--tilt` | 6 | 허벅지 축에서 기운 각도(+ = 칼끝이 뒤로) |
| `--pommel-up` | 0.06 | 자루끝 높이(고관절 기준·캐릭터 키 비율) |
| `--forward` | 0.02 | 앞뒤 위치(고관절 기준·캐릭터 키 비율) |
| `--blade-gap` | 0.010 | **칼날 면** 이 다리에서 떨어지는 거리(키 비율) |
| `--max-sink` | 0.050 | 어느 부위도 이보다 깊게 묻히지 않는 상한 |
| `--sink` | 없음 | 옛 규칙(가장 깊은 점 기준) 강제. 권장하지 않음 |

성공 판정: `####LEG_OK`(`median_gap` ≈ `--blade-gap` · `plane_dot_out`≈1 ·
`blade_dot_down`>0.8) · `####LEG_SIZE` · `####FOLLOW_OK` · **스샷 4컷을 Read 로 직접 확인**.

🛑 **다리 장착은 *가장 깊은 점* 이 아니라 *칼날* 을 기준으로 앉힌다** — 등 장착의
`--sink` 규칙을 그대로 가져오면 안 된다. 장식 가드가 칼날보다 몇 배 두꺼워서, 가드가
안 묻도록 밀어내면 **칼날이 통째로 허공에 뜬다**(실측 male_chrome: 가드 3~4cm vs 칼날
~1cm → 칼날이 3.8cm 부양, 앞에서 보면 안 붙은 것처럼 보인다). 기본 규칙은
"칼날 면이 `--blade-gap` 만큼 떨어지게" 이고 가드는 필요한 만큼 묻힌다(`--max-sink` 상한).
어디가 묻고 어디가 뜨는지는 `####LEG_BAND`(hilt/mid/point)가 따로 보여준다.

## 다른 파지 자세가 필요할 때 (왼손 등)

내장 프레임은 **오른손 전용** 이다. 왼손·방패·역수(reverse grip) 등은
한 캐릭터에 손으로 맞춰 놓고 그 자세를 뽑아 쓴다:

```bash
# 1) 잘 맞춰둔 캐릭터에서 파지 프레임 추출
blender -b good.blend -P .claude/skills/blend-weapon-attach/scripts/extract_frame.py -- \
  --bone mixamorig:LeftHand --out frame_left.json
# 2) 다른 캐릭터에 이식
blender -b other.blend -P .claude/skills/blend-weapon-attach/scripts/attach_weapon.py -- \
  --bone mixamorig:LeftHand --ref frame_left.json
```

## 함정 (시간 낭비 회피)

- **수치가 좋아도 스샷을 봐야 한다.** `grip_to_fist` 가 작다는 건 "내가 손잡이라고 *판정한*
  부분" 이 주먹에 왔다는 뜻일 뿐이다. 판정 자체가 틀렸으면 칼날이 손등에 박혀 있어도 수치는 좋다.
  `tip_to_wrist` 가 `grip_to_wrist` 보다 훨씬 커야 하고, **스샷으로 최종 확인** 한다.
- 🛑 **빈 렌더를 '검증' 으로 착각하지 말 것.** 새로 만든 `.blend` 에는 카메라·라이트가 아예 없는
  경우가 흔하고, 그러면 렌더가 통째로 비어 나온다(실측 2026-08-13 male_vector: 서로 다른 3컷이
  *바이트까지 동일* 했다). 스크립트가 카메라·라이트·월드를 새로 구성하고 픽셀 평균(`mean=`)을
  찍으니, **`mean` 이 비정상이거나 여러 컷이 똑같으면 렌더를 의심** 한다.
- 🛑 **"이미 붙어 있다" 는 판단은 금방 낡는다.** 개발자가 캐릭터를 다시 굽거나 아마추어를 바꾸면
  무기가 미스키닝 상태로 원위치에 돌아온다(실측: 같은 파일이 30분 만에 그렇게 됐다).
  요청받으면 *반드시 지금 파일을 다시 확인* 하고, 과거 결론을 재사용하지 않는다.
- **follow 검증은 `object.matrix_world` 가 아니라 *변형(evaluated) 정점* 으로** 한다
  (스키닝은 origin 을 안 옮겨 거짓 음성이 난다). 그리고 판정은 **손 본 로컬 프레임 드리프트** 로
  한다 — 월드 상대 오프셋은 손이 회전하면 당연히 변하므로 그걸로 판정하면 멀쩡한 부착을 실패로 읽는다.
- **정점 수로 무기/캐릭터를 단정하지 말 것.** 985K 짜리 검, 2.4K 짜리 검이 모두 실재한다.
- **잡동사니 메시(default `Cube` 등)는 부착 전에 지운다.** 시트 framing 의 bbox 를 지배해
  캐릭터를 작게 만들거나 카메라를 가린다.
- mixamo armature 의 0.01 스케일 때문에 무기를 본 좌표계 행렬에 직접 끼우면 100배 축소된다
  (스크립트는 `matrix_parent_inverse` 로 상쇄한다).

## 스크립트

| 파일 | 역할 |
|---|---|
| `scripts/attach_weapon.py` | **손** 부착 + 자동 검증(수치·follow-test·렌더). 진입점 |
| `scripts/attach_weapon_back.py` | **등** 부착(해부 축 계산 + 몸 표면 실측 이격) + 자동 검증 |
| `scripts/attach_weapon_leg.py` | **다리(허벅지)** 부착(다리 표면 실측 + 칼날 기준 안착) + 자동 검증 |
| `scripts/extract_frame.py` | 잘 맞춰진 캐릭터에서 파지 프레임 추출 |
| `scripts/weapon_geom.py` | 공용 분석(PCA 장축·가드 기준 손잡이·shape space). 위 셋이 같이 쓴다 |

전체 개념·로직·함정은 [references/attach-weapon.md](references/attach-weapon.md).
