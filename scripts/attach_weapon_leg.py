#!/usr/bin/env python3
"""Strap the weapon in a `.blend` onto the character's **leg** (thigh mount).

    blender -b <character.blend> -P attach_weapon_leg.py -- [--side left|right]

`attach_weapon.py` puts the weapon *in the hand*, `attach_weapon_back.py` slings it
*across the back*; this one straps it flat against the **outer thigh** (pommel near
the hip, blade pointing down past the knee) and skins it to the thigh bone so it
follows the leg.

## How it differs from the other two

|             | hand                  | back                  | leg (this script)     |
|-------------|-----------------------|-----------------------|-----------------------|
| bone        | `mixamorig:RightHand` | `mixamorig:Spine2`    | `mixamorig:LeftUpLeg` |
| pose source | built-in grip frame   | anatomy axes          | anatomy + thigh bone  |
| depth       | decided by the hand   | measured off the back | measured off the leg  |

Like the back script it needs no reference character: the hip/knee bones plus the
measured leg surface produce a pose that fits any body shape.

## The three values that set the pose (all fractions of character height, so they port)
- `--pommel-up` : pommel height above the hip joint        (default 0.06)
- `--forward`   : how far forward of the hip joint it sits (default 0.02)
- `--tilt`      : degrees off the thigh axis, + tips the point backward (default 6)

## Depth is measured, not guessed — and it seats the **blade**, not the guard
Leg-owned body vertices (Hips + that side's UpLeg/Leg vertex groups) are rasterised
into a (fore-aft, vertical) height map of the outermost lateral surface, and the
weapon is pushed sideways until **the flat of the blade** rests `--blade-gap` off it.
The guard bites as deep as it has to (capped by `--max-sink`), so thigh plates, knee
guards and hilt decoration are absorbed on any character with no per-file tuning.
🛑 The maths runs in **rest** coordinates, because that is the space skinning binds in.

🛑 Never seat on the *deepest* point (the old `--sink` rule, still available). An
ornate guard is several times thicker than the blade, so clearing it parks the blade
in mid-air: measured on male_chrome, the guard is 3-4cm thick against a ~1cm blade and
deepest-point seating left the blade floating 3.8cm out, reading as unattached.
`####LEG_BAND` reports the gap separately for hilt / mid / point so you can see it.

## Success = all four
- `####LEG_OK`    : `median_gap` ≈ `--blade-gap`, `blade_dot_down` > 0.8,
                    `plane_dot_out` ≈ 1.0 (flat of the blade lies on the leg)
- `####LEG_SIZE`  : `weapon_to_char` inside the band for the weapon type
- `####FOLLOW_OK` : bending the leg keeps the weapon rigid in the bone frame
- `####SHOT`      : 🛑 open the PNGs and LOOK — numbers alone are not proof
"""
import bpy, sys, os, math, argparse
import numpy as np
from mathutils import Vector, Matrix, Quaternion

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weapon_geom as wg
from attach_weapon import clear_attachment, skin, deformed_world, SIZE_BANDS
from attach_weapon_back import (anatomy, body_mesh, rest_world, place,
                                setup_scene, purge_check_objects)

CELL = 0.01           # leg surface height-map cell size (world units)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--weapon", default=None, help="weapon mesh name (default: auto-detect)")
    p.add_argument("--side", choices=("left", "right"), default="left",
                   help="which leg carries it (the character's own left/right)")
    p.add_argument("--bone", default=None,
                   help="mount bone (default: mixamorig:<Side>UpLeg)")
    p.add_argument("--tilt", type=float, default=6.0,
                   help="degrees off the thigh axis; + tips the point backward")
    p.add_argument("--pommel-up", type=float, default=0.06,
                   help="pommel height above the hip joint, as a fraction of character height")
    p.add_argument("--forward", type=float, default=0.02,
                   help="fore-aft offset from the hip joint, as a fraction of character height")
    p.add_argument("--blade-gap", type=float, default=0.010,
                   help="how far the flat of the blade rests off the leg (fraction of "
                        "character height). This is what the default seating solves for")
    p.add_argument("--max-sink", type=float, default=0.050,
                   help="hard cap on how deep any part may bite into the leg "
                        "(fraction of character height)")
    p.add_argument("--sink", type=float, default=None,
                   help="override: seat by the deepest point instead, sinking it exactly "
                        "this much (fraction of character height). Rarely what you want - "
                        "an ornate guard then holds the blade off the leg")
    p.add_argument("--flip-face", action="store_true", help="flip which face of the blade shows")
    p.add_argument("--ratio", type=float, default=None,
                   help="target weapon length / character height (default: keep current size)")
    p.add_argument("--out", default=None, help="save path (default: overwrite the original)")
    p.add_argument("--dry", action="store_true", help="report numbers without saving")
    p.add_argument("--shot-dir", default=None,
                   help="folder for the check renders (default: next to the .blend)")
    p.add_argument("--no-shot", action="store_true", help="skip the check renders (not recommended)")
    p.add_argument("--no-follow-test", action="store_true",
                   help="skip the follow test (not recommended)")
    return p.parse_args(argv)


# --------------------------------------------------------------------------- leg surface
def leg_vertices(body, side):
    """Indices of the body vertices owned by the hip + that leg.

    Selecting by vertex group beats a spatial box: it never picks up the other leg,
    or a hand that happens to hang at hip height in the rest pose.
    """
    S = side.capitalize()
    names = {"mixamorig:Hips", "mixamorig:%sUpLeg" % S, "mixamorig:%sLeg" % S}
    idx = {g.index for g in body.vertex_groups if g.name in names}
    if not idx:
        return None
    keep = [v.index for v in body.data.vertices
            if sum(ge.weight for ge in v.groups if ge.group in idx) > 0.3]
    return np.array(keep, dtype=int) if keep else None


class LegSurface:
    """The outer surface of the leg as a (fore-aft, vertical) height map.

    Each cell holds the most *outboard* lateral coordinate found in it, dilated 3x3
    so cell edges never report the surface as further in than it really is.
    """

    EMPTY = -1e9

    def __init__(self, pts, origin, fore, up, out):
        d = pts - np.array(origin)
        self.F = d @ np.array(fore)
        self.U = d @ np.array(up)
        self.O = d @ np.array(out)
        self.f0, self.u0 = self.F.min() - CELL, self.U.min() - CELL
        nf = int((self.F.max() - self.f0) / CELL) + 3
        nu = int((self.U.max() - self.u0) / CELL) + 3
        g = np.full((nu, nf), self.EMPTY)
        np.maximum.at(g, (self._i(self.U, self.u0), self._i(self.F, self.f0)), self.O)
        pad = np.full((nu + 2, nf + 2), self.EMPTY)
        pad[1:-1, 1:-1] = g
        self.grid = np.maximum.reduce([pad[a:a + nu, b:b + nf]
                                       for a in range(3) for b in range(3)])
        self.nu, self.nf = nu, nf

    @staticmethod
    def _i(v, o):
        return ((v - o) / CELL).astype(int)

    def sample(self, F, U):
        i, j = self._i(U, self.u0), self._i(F, self.f0)
        ok = (i >= 0) & (i < self.nu) & (j >= 0) & (j < self.nf)
        res = np.full(len(F), self.EMPTY)
        res[ok] = self.grid[i[ok], j[ok]]
        return res


# --------------------------------------------------------------------------- follow test
def follow_test(arm, w, bone, side):
    """Swing the leg and check the weapon stays rigid in the bone's own frame.

    🛑 The action is detached for the test and **must be put back** — saving without
    restoring it wipes this character's animation link (the pose is the asset).
    """
    ad = arm.animation_data
    keep = (ad.action, getattr(ad, "action_slot", None)) if ad else None
    if ad:
        ad.action = None

    def sample():
        # Probe the bone **tail** (the knee): rotating a bone never moves its own head,
        # so a head probe reports leg_moved=0 and the follow check reads as inconclusive.
        bpy.context.view_layer.update()
        pb = arm.pose.bones[bone]
        Bw = arm.matrix_world @ pb.matrix
        c = Vector(deformed_world(w).mean(axis=0))
        return (arm.matrix_world @ pb.tail), c, Bw.inverted() @ c

    h0, c0, b0 = sample()
    S = side.capitalize()
    posed = []
    for bn, ang, ax in (("%sUpLeg" % S, 40, "X"), ("%sLeg" % S, 35, "X")):
        pb = arm.pose.bones.get("mixamorig:" + bn)
        if not pb:
            continue
        pb.rotation_mode = "QUATERNION"
        v = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[ax]
        pb.rotation_quaternion = Quaternion(v, math.radians(ang))
        posed.append("mixamorig:" + bn)
    if not posed:
        print("####FOLLOW_SKIP no leg bones to pose")
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
    print("####FOLLOW leg_moved=%.4f weapon_moved=%.4f bone_frame_drift=%.6f" % (dh, dw, drift))
    if dh < 0.005 and dw < 0.005:
        print("####FOLLOW_INCONCLUSIVE leg barely moved")
    elif dw < dh * 0.3:
        print("####FOLLOW_FAIL weapon does not follow the leg - check skinning")
    elif drift < 0.01:
        print("####FOLLOW_OK weapon rigid in bone frame")
    else:
        print("####FOLLOW_WARN bone_frame_drift=%.4f" % drift)


# --------------------------------------------------------------------------- render
def render_check(arm, w, up, left, back, side, out_dir):
    """Front, 3/4 and profile from the carrying side, plus a thigh close-up.
    Cameras are built from the **anatomy** axes — never assume world Z is up."""
    sc, cam, cd = setup_scene()
    out = left if side == "left" else -left
    fore = -back
    for vec, e in ((fore * 1.0 + up * 0.8 + out * 0.6, 4.0),
                   (-fore * 1.0 + up * 0.5 - out * 0.8, 2.2),
                   (up * -0.3 + fore * 0.6, 1.2)):
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
        z = view.normalized()
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
            tmp = os.path.join(out_dir, "_leg_stat.png")
            bpy.data.images.get("Render Result").save_render(filepath=tmp)
            im = bpy.data.images.load(tmp)
            a = np.array(im.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
            stat = "mean=%.3f" % a.mean()
            bpy.data.images.remove(im)
            os.remove(tmp)
        except Exception:
            pass
        print("####SHOT %s %s" % (p, stat))

    wc = Vector(deformed_world(w).mean(axis=0))
    shot(fore, "leg_check_front.png", cen, height * 1.05)
    shot((fore * 2 + out).normalized(), "leg_check_front34.png", cen, height * 1.05)
    shot(out, "leg_check_side.png", cen, height * 1.05)
    shot((fore + out * 1.6 + up * 0.25).normalized(), "leg_check_closeup.png",
         wc, height * 0.60)


# --------------------------------------------------------------------------- main
def main():
    a = parse_args()
    arm = wg.find_armature()
    w = wg.find_weapon(a.weapon)
    S = a.side.capitalize()
    bone = a.bone or "mixamorig:%sUpLeg" % S
    knee = "mixamorig:%sLeg" % S
    for b in (bone, knee):
        if b not in arm.data.bones:
            raise SystemExit("####LEG_FAIL no bone: %s" % b)
    body = body_mesh(w)
    up, left, back = anatomy(arm)                  # placement: rest = the skinning basis
    bpy.context.view_layer.update()
    pup, pleft, pback = anatomy(arm, posed=True)   # cameras: what you actually see
    if up.angle(pup) > math.radians(5):
        print("####POSE_NOTE rest and posed axes differ by %.0f deg - "
              "placing in rest, rendering in posed" % (up.angle(pup) * 57.2958))
    out = left if a.side == "left" else -left
    fore = -back
    print("####WEAPON name=%r verts=%d body=%r bone=%s side=%s"
          % (w.name, len(w.data.vertices), body.name, bone, a.side))

    clear_attachment(w)
    smax_cur = max(abs(v) for v in w.matrix_world.to_scale())
    g = wg.analyze(w)
    Sh = g["S"]
    grip_local = wg.to_local(g["grip_c"], Sh)
    t = wg.t_values(w, g)         # per-vertex position along the weapon's long axis

    H = arm.matrix_world @ arm.data.bones[bone].matrix_local
    sH = max(abs(v) for v in H.to_scale())
    chh = wg.char_height(arm)
    s = (smax_cur / sH) if a.ratio is None else (a.ratio * chh) / (sH * g["length"])
    wlen = g["length"] * s * sH                    # true world length once attached

    # ---- target pose: pommel by the hip, blade down the outside of the thigh ----
    O = arm.matrix_world @ arm.data.bones[bone].head_local
    K = arm.matrix_world @ arm.data.bones[knee].head_local
    down = (K - O).normalized()                    # along the thigh, not merely -up
    fore_p = (fore - down * fore.dot(down)).normalized()
    th = math.radians(a.tilt)
    blade_dir = (down * math.cos(th) - fore_p * math.sin(th)).normalized()
    thin_dir = -out if a.flip_face else out        # flat of the blade lies on the leg

    pommel = O + up * (a.pommel_up * chh) + fore * (a.forward * chh)
    d_pommel = (g["t_hi"] - (g["t_gmin"] + g["t_gmax"]) / 2 if not g["grip_low"]
                else (g["t_gmin"] + g["t_gmax"]) / 2 - g["t_lo"]) * s * sH
    grip_pos = pommel + blade_dir * d_pommel

    # 🛑 R lives in **bone-local (H) space**, not world. Feeding world directions
    # straight in leaves it off by H's axis swap and stands the blade on its head.
    Hi3 = H.to_3x3().inverted()
    R = wg.basis((Hi3 @ blade_dir).normalized(), (Hi3 @ thin_dir).normalized()) \
        @ wg.basis(g["tip_c"] - g["grip_c"], g["thin"]).transposed()
    if R.determinant() < 0:
        raise SystemExit("####LEG_FAIL rotation det<0 (mirrored)")
    place(w, H, g, Sh, grip_local, R, s, grip_pos)

    # ---- depth: measure the leg and shove the weapon out (in rest coords) ----
    keep = leg_vertices(body, a.side)
    bpts = rest_world(body)
    if keep is None:
        print("####LEG_NOTE leg vertex groups not found - using the whole body mesh")
    surf = LegSurface(bpts if keep is None else bpts[keep], O, fore, up, out)
    sw = rest_world(w) - np.array(O)
    WF, WU, WO = sw @ np.array(fore), sw @ np.array(up), sw @ np.array(out)
    bs = surf.sample(WF, WU)
    hit = bs > surf.EMPTY / 2
    if not hit.any():
        raise SystemExit("####LEG_FAIL weapon does not overlap the leg silhouette")
    over = bs[hit] - WO[hit]                           # + = that vertex is inside the leg
    push_strict = float(np.max(over))                  # smallest shift that touches nothing
    # 🛑 Seating on the *deepest* point is what makes a blade float. On this weapon the
    # ornate guard is 3-4cm thick against a ~1cm blade, so clearing the guard parks the
    # blade 4cm out in mid-air (measured: median_gap 3.8cm, and it reads as unattached).
    # So solve for the **blade** instead: push until the flat of the blade sits
    # `--blade-gap` off the leg, and let the guard bite as deep as it needs, capped by
    # `--max-sink`. Thick guard -> more bite, plain guard -> less, with no per-character
    # tuning. `--sink` restores the old deepest-point rule when you want it.
    deep_u = float(WU[hit][int(np.argmax(over))])
    blade_hit = ((t > g["t_gmax"]) if g["grip_low"] else (t < g["t_gmin"]))[hit]
    if a.sink is not None:
        push = push_strict - a.sink * chh
        rule = "sink"
    elif blade_hit.any():
        push = max(float(np.median(over[blade_hit])) + a.blade_gap * chh,
                   push_strict - a.max_sink * chh)     # cap: never bury more than this
        rule = "blade_gap"
    else:
        push = push_strict - a.max_sink * chh
        rule = "no_blade_overlap"
    print("####LEG_CLEAR rule=%s push_strict=%.4f driven_at_up=%+.4f push=%.4f deepest_sink=%.4f"
          % (rule, push_strict, deep_u, push, push_strict - push))
    grip_pos = grip_pos + out * push
    place(w, H, g, Sh, grip_local, R, s, grip_pos)

    # ---- attach ----
    skin(w, arm, bone)
    bpy.context.view_layer.update()

    # ---- numeric check (all in rest = the space the placement was computed in) ----
    sw = rest_world(w) - np.array(O)
    WF, WU, WO = sw @ np.array(fore), sw @ np.array(up), sw @ np.array(out)
    bs = surf.sample(WF, WU)
    hit = bs > surf.EMPTY / 2
    gap_v = WO[hit] - bs[hit]                          # + = clear of the leg, - = buried
    min_gap, med_gap = float(np.min(gap_v)), float(np.median(gap_v))
    sunk_pct = float((gap_v < 0).mean() * 100)
    pts_r = rest_world(w)
    gc = Vector(pts_r[(t >= g["t_gmin"]) & (t <= g["t_gmax"])].mean(axis=0))
    tipc = Vector(pts_r[np.abs(t - g["t_tip"]) <= g["span"] * 0.05].mean(axis=0))

    def ouf(p):
        d = p - O
        return d.dot(out), d.dot(up), d.dot(fore)

    go, gu, gf = ouf(gc)
    to_, tu, tf = ouf(tipc)
    axis_w = (tipc - gc).normalized()
    n_w = (w.matrix_world.to_3x3() @ wg.to_local(g["thin"], Sh)).normalized()
    print("####LEG_OK deepest_sink=%.4f median_gap=%.4f sunk_verts=%.1f%% push=%.4f "
          "tilt=%.1f plane_dot_out=%.4f blade_dot_down=%.4f"
          % (-min_gap, med_gap, sunk_pct, push, a.tilt, abs(n_w.dot(out)), axis_w.dot(-up)))
    print("####LEG_POSE grip(out=%+.4f up=%+.4f fore=%+.4f) tip(out=%+.4f up=%+.4f fore=%+.4f)"
          % (go, gu, gf, to_, tu, tf))
    # A thick guard and a thin blade want different offsets, so a single rigid push
    # always trades one against the other. Split the gap along the weapon's own axis
    # so it is obvious *where* it bites and *where* it stands off.
    th_hit = t[hit]
    lo3, hi3 = float(th_hit.min()), float(th_hit.max())
    edges = np.linspace(lo3, hi3, 4)
    if not g["grip_low"]:                       # keep the report ordered hilt -> point
        edges = edges[::-1]
    for nm, i in (("hilt", 0), ("mid", 1), ("point", 2)):
        a0, b0 = sorted((edges[i], edges[i + 1]))
        m = (th_hit >= a0) & (th_hit <= b0)
        if m.any():
            print("####LEG_BAND %-5s deepest_sink=%+.4f median_gap=%+.4f sunk=%.1f%%"
                  % (nm, -float(gap_v[m].min()), float(np.median(gap_v[m])),
                     float((gap_v[m] < 0).mean() * 100)))
    kn = (K - O).dot(up)
    ank = (arm.matrix_world @ arm.data.bones["mixamorig:%sFoot" % S].head_local - O).dot(up)
    print("####LEG_LANDMARK hip_up=+0.0000 knee_up=%+.4f ankle_up=%+.4f char_h=%.4f"
          % (kn, ank, chh))
    ratio = wlen / chh
    print("####LEG_SIZE weapon_len=%.4f char_height=%.4f weapon_to_char=%.2f"
          % (wlen, chh, ratio))
    bands = " ".join("%s %s-%s" % (k, v[0], v[1]) for k, v in SIZE_BANDS.items())
    if ratio > 1.05 or 0 < ratio < 0.20:
        print("####LEG_SIZE_WARN %.0f%% of height - use --ratio (%s)" % (ratio * 100, bands))
    if med_gap > 0.030 * chh / 0.85:
        print("####LEG_WARN weapon floats %.1fcm off the leg - lower --blade-gap, or raise "
              "--max-sink if the cap is what is holding it out" % (med_gap * 100))
    if (push_strict - push) > a.max_sink * chh + 1e-6:
        print("####LEG_WARN deepest bite %.1fcm exceeds --max-sink" % ((push_strict - push) * 100))
    if abs(n_w.dot(out)) < 0.9:
        print("####LEG_WARN blade plane is not parallel to the leg")
    if axis_w.dot(-up) < 0.8:
        print("####LEG_WARN blade does not point downward")
    if tu > 0:
        print("####LEG_WARN the point ends up above the hip - check --tilt/--pommel-up")

    if not a.no_follow_test:
        follow_test(arm, w, bone, a.side)

    # 🛑 **Save first, render second.** setup_scene() replaces the camera, lights,
    # world and view transform, so rendering before saving bakes that check scene
    # into the asset file.
    if a.dry:
        print("####DRY not saved")
    else:
        path = a.out or bpy.data.filepath
        purge_check_objects()
        bpy.ops.wm.save_as_mainfile(filepath=path)
        print("####SAVED %s" % path)
    if not a.no_shot:
        render_check(arm, w, pup, pleft, pback, a.side,
                     a.shot_dir or (os.path.dirname(bpy.data.filepath) or os.getcwd()))


if __name__ == "__main__":
    main()
