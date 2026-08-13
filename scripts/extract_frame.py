#!/usr/bin/env python3
"""이미 올바르게 부착된 캐릭터에서 **파지 프레임** 을 뽑아 json 으로 저장.

    blender -b <good_character.blend> -P extract_frame.py -- --out frame.json

`attach_weapon.py --ref frame.json` 으로 그 파지 자세를 다른 캐릭터에 이식한다.

## 언제 쓰나
- **왼손/보조 무기**: 내장 기본 프레임은 오른손 전용이다. 왼손 파지를 하나
  손으로 맞춰 놓고 여기서 뽑아 쓴다(`--bone mixamorig:LeftHand`).
- **다른 파지 스타일**: 역수(reverse grip)·어깨 걸침 등 새 자세를 정착시킬 때.
- 기본 프레임이 마음에 안 들 때, 손으로 고친 캐릭터를 기준으로 재추출.

## 무엇을 뽑나 (손 본 rest 좌표계 기준)
- `grip_H`     : 손잡이 중심의 위치
- `blade_dir_H`: 손잡이 -> 칼끝 방향(단위벡터)
- `thin_dir_H` : 칼날 두께축(칼날 면의 방향을 결정)

월드 좌표가 아니라 **손 본 로컬** 이라 캐릭터 키·체형·아마추어가 달라도 이식된다.
"""
import bpy, sys, os, json, argparse
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weapon_geom as wg


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--weapon", default=None, help="무기 메시(생략=자동 식별)")
    p.add_argument("--bone", default="mixamorig:RightHand")
    p.add_argument("--out", required=True, help="저장할 frame json 경로")
    a = p.parse_args(argv)

    arm = wg.find_armature()
    w = wg.find_weapon(a.weapon)
    if a.bone not in arm.data.bones:
        raise SystemExit(f"####FRAME_FAIL 본 없음: {a.bone}")
    if not any(m.type == "ARMATURE" for m in w.modifiers):
        print("####FRAME_WARN 이 무기는 스키닝돼 있지 않다 — "
              "'올바르게 부착된' 캐릭터에서 뽑아야 의미가 있다")

    H = arm.matrix_world @ arm.data.bones[a.bone].matrix_local
    Hi = H.inverted()
    g = wg.analyze(w)
    S = g["S"]
    M3, Hi3 = w.matrix_world.to_3x3(), Hi.to_3x3()

    grip_H = Hi @ (w.matrix_world @ wg.to_local(g["grip_c"], S))
    blade_H = (Hi3 @ (M3 @ wg.to_local(g["tip_c"] - g["grip_c"], S))).normalized()
    thin_H = (Hi3 @ (M3 @ wg.to_local(g["thin"], S))).normalized()

    chh = wg.char_height(arm)
    true_len = g["length"] * max(abs(v) for v in w.matrix_world.to_scale())
    data = {
        "grip_H": list(grip_H),
        "blade_dir_H": list(blade_H),
        "thin_dir_H": list(thin_H),
        "_source": bpy.data.filepath, "_weapon": w.name, "_bone": a.bone,
        "_char_height": chh, "_weapon_len": true_len, "_ratio": true_len / chh,
    }
    json.dump(data, open(a.out, "w"), indent=1)
    print(f"####FRAME grip_H={[round(v, 3) for v in grip_H]} "
          f"blade_dir_H={[round(v, 4) for v in blade_H]} "
          f"thin_dir_H={[round(v, 4) for v in thin_H]}")
    print(f"####FRAME_SIZE char_h={chh:.4f} weapon_len={true_len:.4f} ratio={true_len / chh:.3f}")
    print(f"####SAVED {a.out}")


if __name__ == "__main__":
    main()
