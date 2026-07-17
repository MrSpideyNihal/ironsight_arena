# maps/arena_01.py
# ──────────────────────────────────────────────
# Expanded deathmatch arena — 120×120 units.
# Walls, towers, ramps, bunkers, crate clusters, climb route.
# ──────────────────────────────────────────────
from ursina import (Entity, color, Vec3, DirectionalLight,
                    AmbientLight, PointLight, scene)


def build_arena():
    """Construct the arena geometry and return a list of all entities created."""
    entities = []

    def _e(**kw):
        ent = Entity(**kw)
        entities.append(ent)
        return ent

    # ── Lighting ───────────────────────────────
    sun = DirectionalLight(y=30, rotation=(50, -35, 0))
    sun.color = color.rgb32(255, 240, 210)
    entities.append(sun)

    ambient = AmbientLight(color=color.rgb32(70, 75, 100))
    entities.append(ambient)

    pt = PointLight(position=(0, 12, 0))
    pt.color = color.rgb32(80, 160, 255)
    pt.attenuation = (0, 0, 0.02)
    entities.append(pt)

    # ── Ground ─────────────────────────────────
    _e(model='plane', scale=(120, 1, 120),
       color=color.rgb32(38, 42, 50), texture='white_cube',
       texture_scale=(120, 120), collider='box')

    # ── Boundary Walls ─────────────────────────
    wall_col = color.rgb32(55, 58, 68)
    _e(model='cube', scale=(120, 10, 1.2), position=( 0, 5,  60), color=wall_col, collider='box')
    _e(model='cube', scale=(120, 10, 1.2), position=( 0, 5, -60), color=wall_col, collider='box')
    _e(model='cube', scale=(1.2, 10, 120), position=( 60, 5,  0), color=wall_col, collider='box')
    _e(model='cube', scale=(1.2, 10, 120), position=(-60, 5,  0), color=wall_col, collider='box')

    # wall top trim
    trim_col = color.rgb32(0, 180, 255)
    _e(model='cube', scale=(120, 0.25, 1.2), position=( 0, 9.8,  60), color=trim_col)
    _e(model='cube', scale=(120, 0.25, 1.2), position=( 0, 9.8, -60), color=trim_col)
    _e(model='cube', scale=(1.2, 0.25, 120), position=( 60, 9.8,  0), color=trim_col)
    _e(model='cube', scale=(1.2, 0.25, 120), position=(-60, 9.8,  0), color=trim_col)

    # ── Center Platform ─────────────────────────
    _e(model='cube', scale=(12, 1.8, 12), position=(0, 0.9, 0),
       color=color.rgb32(25, 130, 175), collider='box')
    _e(model='cube', scale=(2.5, 4, 2.5), position=(0, 3.7, 0),
       color=color.rgb32(18, 110, 155), collider='box')
    _e(model='cube', scale=(3, 0.2, 3), position=(0, 5.8, 0),
       color=color.rgb32(0, 220, 255))

    # ── Ramps ──────────────────────────────────
    ramp_col = color.rgb32(45, 120, 158)
    for rx, rz, ry_rot in [(8, 0, 90), (-8, 0, -90), (0, 8, 0), (0, -8, 180)]:
        ramp = _e(model='cube', scale=(5, 0.35, 6),
                  position=(rx, 0.7, rz), color=ramp_col, collider='box')
        ramp.rotation_x = -14 if ry_rot in (0, 90) else 14
        ramp.rotation_y = ry_rot

    # ── Corner Towers ──────────────────────────
    tower_col = color.rgb32(170, 125, 45)
    for px, pz in [(24, 24), (-24, 24), (24, -24), (-24, -24)]:
        _e(model='cube', scale=(5, 9, 5), position=(px, 4.5, pz),
           color=tower_col, collider='box')
        _e(model='cube', scale=(7, 0.4, 7), position=(px, 9.2, pz),
           color=color.rgb32(140, 100, 35), collider='box')
        # Glowing beacon lights on top of each tower
        _e(model='sphere', scale=0.45, position=(px, 9.6, pz),
           color=color.rgb32(255, 60, 60))
        pt_beacon = PointLight(position=(px, 10.2, pz))
        pt_beacon.color = color.rgb32(255, 50, 50)
        pt_beacon.attenuation = (0, 0, 0.15)
        entities.append(pt_beacon)

    # ── Mid Cover Walls ─────────────────────────
    cover_col = color.rgb32(180, 80, 35)
    _e(model='cube', scale=(15, 3, 1.8), position=( 0, 1.5,  22), color=cover_col, collider='box')
    _e(model='cube', scale=(15, 3, 1.8), position=( 0, 1.5, -22), color=cover_col, collider='box')
    _e(model='cube', scale=(1.8, 3, 15), position=( 22, 1.5,  0), color=cover_col, collider='box')
    _e(model='cube', scale=(1.8, 3, 15), position=(-22, 1.5,  0), color=cover_col, collider='box')

    # ── Side Bunkers ───────────────────────────
    bunker_col = color.rgb32(65, 70, 82)
    for sx in (1, -1):
        for bz in (16, -16):
            _e(model='cube', scale=(6, 4, 2), position=(sx * 33, 2, bz),
               color=bunker_col, collider='box')
            _e(model='cube', scale=(2, 4, 6), position=(sx * 36, 2, bz * 0.55),
               color=bunker_col, collider='box')

    # ── Crate Clusters ──────────────────────────────────
    import random
    crate_tex = 'assest/48-crate/Wooden Crate/Textures/1024/Wooden Crate_Crate_BaseColor.png'
    crate_col = color.rgb32(165, 120, 65)
    for cx, cz in [(15, 33), (-15, 33), (15, -33), (-15, -33),
                   (33, 15), (-33, 15), (33, -15), (-33, -15)]:
        rot_y = random.uniform(0, 40)
        # Large crate (1.6x1.6x1.6 centered at Y=0.8)
        _e(model='cube', texture=crate_tex, scale=(1.6, 1.6, 1.6),
           position=(cx, 0.8, cz), color=crate_col, collider='box')
        # Small crate (1.2x1.2x1.2 centered at Y=0.6)
        _e(model='cube', texture=crate_tex, scale=(1.2, 1.2, 1.2),
           position=(cx + 2.2, 0.6, cz + 1.8), rotation_y=rot_y,
           color=color.rgb32(145, 105, 55), collider='box')

    # ── Diagonal Barricades ────────────────────
    barr_col = color.rgb32(90, 50, 40)
    for bx, bz, bry in [(12, 12, 45), (-12, 12, -45), (12, -12, -45), (-12, -12, 45)]:
        b = _e(model='cube', scale=(7, 2.5, 1.5), position=(bx, 1.25, bz),
               color=barr_col, collider='box')
        b.rotation_y = bry

    # ── Floor Accent Lines ─────────────────────
    accent = color.rgb32(0, 160, 220)
    _e(model='cube', scale=(80, 0.05, 0.3), position=(0, 0.03, 0), color=accent)
    _e(model='cube', scale=(0.3, 0.05, 80), position=(0, 0.03, 0), color=accent)
    for gx, gz, gry in [(20, 0, 45), (-20, 0, 45), (0, 20, 45), (0, -20, 45)]:
        strip = _e(model='cube', scale=(22, 0.04, 0.2), position=(gx, 0.03, gz),
                   color=color.rgb32(0, 100, 180))
        strip.rotation_y = gry

    # ── Climb Route ────────────────────────────
    climb_col = color.rgb32(40, 150, 120)
    ramp_a = _e(model='cube', scale=(10, 1.2, 10), position=(34, 0.6, 42), color=climb_col, collider='box')
    ramp_a.rotation_x = -18
    ramp_b = _e(model='cube', scale=(10, 1.2, 10), position=(34, 1.8, 50), color=climb_col, collider='box')
    ramp_b.rotation_x = -18
    ramp_c = _e(model='cube', scale=(10, 1.2, 10), position=(34, 3.0, 58), color=climb_col, collider='box')
    ramp_c.rotation_x = -18
    top_pad = _e(model='cube', scale=(14, 1.0, 14), position=(34, 4.2, 68), color=color.rgb32(30, 170, 150), collider='box')
    _e(model='cube', scale=(1.0, 6, 14), position=(40.5, 3.0, 61), color=color.rgb32(30, 120, 100), collider='box')
    _e(model='cube', scale=(1.0, 6, 14), position=(27.5, 3.0, 61), color=color.rgb32(30, 120, 100), collider='box')
    _e(model='cube', scale=(14, 0.8, 2.0), position=(34, 6.0, 73), color=color.rgb32(80, 200, 170), collider='box')

    # ── Climbing Ladders on Towers ─────────────
    # One ladder on the inner side of each corner tower
    for px, pz in [(24, 24), (-24, 24), (24, -24), (-24, -24)]:
        lx = px - 2.58 if px > 0 else px + 2.58
        lz = pz
        # main ladder frame
        ladder = _e(
            model='cube',
            color=color.rgb32(30, 180, 110),
            scale=(1.2, 9.2, 0.15),
            position=(lx, 4.6, lz),
            collider='box'
        )
        ladder.is_ladder = True
        
        # rungs
        for y_offset in range(12):
            rel_y = -0.5 + (y_offset + 0.5) / 12
            _e(
                parent=ladder,
                model='cube',
                color=color.rgb32(180, 255, 200),
                scale=(0.95, 0.08, 1.5),
                position=(0, rel_y, 0.55)
            )

    return entities
