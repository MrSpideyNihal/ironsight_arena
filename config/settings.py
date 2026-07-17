# config/settings.py
# ──────────────────────────────────────────────
# All tunable game constants in one place
# ──────────────────────────────────────────────

# ── Network ───────────────────────────────────
SERVER_PORT       = 7777
DISCOVERY_PORT    = 7778
TICK_RATE         = 30            # server updates per second
TICK_INTERVAL     = 1.0 / TICK_RATE

# ── Player Physics ────────────────────────────
MOVE_SPEED        = 10.0
SPRINT_SPEED      = 14.0
GRAVITY           = 28.0
JUMP_FORCE        = 10.0
GROUND_RAY_DIST   = 2.5           # raycast distance for ground detection
PLAYER_MAX_HP     = 100
RESPAWN_TIME      = 3.0          # seconds before respawn
KILLS_TO_WIN_DEFAULT = 10

# ── Health Pickup ─────────────────────────────
HEAL_PICKUP_HEAL_AMOUNT = 35
HEAL_PICKUP_LIFETIME    = 12.0
HEAL_PICKUP_RADIUS      = 2.0

# ── Grenade ───────────────────────────────────
GRENADE_COOLDOWN        = 4.0
GRENADE_FUSE            = 1.6
GRENADE_SPEED           = 18.0
GRENADE_UPWARD_VELOCITY = 8.0
GRENADE_RADIUS          = 6.0
GRENADE_DAMAGE          = 45

# ── Dash ──────────────────────────────────────
DASH_DURATION           = 0.25
DASH_COOLDOWN           = 1.3
DASH_SPEED_MULTIPLIER   = 2.5

# ── Weapon ────────────────────────────────────
WEAPON_DAMAGE         = 25
WEAPON_HEADSHOT_MULT  = 2.0
WEAPON_AMMO_CAPACITY  = 30
WEAPON_RELOAD_TIME    = 1.6      # seconds
WEAPON_FIRE_RATE      = 0.11     # seconds between shots
WEAPON_SPREAD         = 0.012
WEAPON_ADS_SPREAD     = 0.004
WEAPON_RECOIL_FORCE   = 0.6

# ── Camera ────────────────────────────────────
CAMERA_DISTANCE       = 5.0
CAMERA_MIN_DISTANCE   = 1.5
CAMERA_HEIGHT         = 2.0
MOUSE_SENSITIVITY     = 40.0
NORMAL_FOV            = 90
ADS_FOV               = 50

# ── Spawn Points ──────────────────────────────
SPAWN_POINTS = [
    # N/S/E/W open lanes — well clear of all obstacles
    (  0,  5.0,  38),   # north lane
    (  0,  5.0, -38),   # south lane
    ( 38,  5.0,   0),   # east lane
    (-38,  5.0,   0),   # west lane
    # diagonal open corners (between towers, no crates nearby)
    ( 32,  5.0,  32),   # NE open
    (-32,  5.0,  32),   # NW open
    ( 32,  5.0, -32),   # SE open
    (-32,  5.0, -32),   # SW open
    # mid-lane flanks (open space beside cover walls)
    ( 10,  5.0,  32),   # N-flank right
    (-10,  5.0, -32),   # S-flank left
]

# ── Selectable Colors ─────────────────────────
PLAYER_COLORS = [
    (50, 160, 220),   # Light Blue (Default)
    (220, 60, 60),    # Red
    (60, 220, 80),    # Green
    (240, 200, 30),   # Yellow
    (200, 60, 220),   # Magenta
    (240, 120, 30)    # Orange
]

# ── Weapon Configurations ─────────────────────
WEAPON_CONFIGS = {
    "Assault Rifle": {
        "max_ammo": 30,
        "reload_time": 1.6,
        "fire_rate": 0.11,
        "spread": 0.012,
        "ads_spread": 0.004,
        "recoil": 0.6,
        "damage": 25,
        "ads_fov": 50,
        "model_scale": 0.25,
        "color_r": 255, "color_g": 230, "color_b": 80,
        "trace_r": 255, "trace_g": 200, "trace_b": 60, "trace_a": 180,
        "muzzle_pos": (0.35, 0.7, 0.9)
    },
    "Sniper Rifle": {
        "max_ammo": 5,
        "reload_time": 2.5,
        "fire_rate": 1.2,
        "spread": 0.04,
        "ads_spread": 0.0,
        "recoil": 3.0,
        "damage": 100,  # 1-hit kill
        "ads_fov": 15,   # very high zoom
        "model_scale": 0.35,
        "color_r": 50, "color_g": 150, "color_b": 255,
        "trace_r": 50, "trace_g": 200, "trace_b": 255, "trace_a": 220,
        "muzzle_pos": (0.35, 0.7, 1.2)
    }
}


# ── Server-side Static Colliders for Grenade Physics ──
# List of AABB boxes: each box is {"min": [x, y, z], "max": [x, y, z]}
# (Matches the static obstacles in maps/arena_01.py)
STATIC_COLLIDERS = [
    # Center platform bottom
    {"min": [-6.0, 0.0, -6.0], "max": [6.0, 1.8, 6.0]},
    # Center platform top pillar
    {"min": [-1.25, 1.8, -1.25], "max": [1.25, 5.7, 1.25]},
    
    # Mid Cover Walls
    {"min": [-7.5, 0.0, 21.1], "max": [7.5, 3.0, 22.9]},
    {"min": [-7.5, 0.0, -22.9], "max": [7.5, 3.0, -21.1]},
    {"min": [21.1, 0.0, -7.5], "max": [22.9, 3.0, 7.5]},
    {"min": [-22.9, 0.0, -7.5], "max": [-21.1, 3.0, 7.5]},
    
    # Side Bunkers (sx * 33, sx * 36)
    # sx = 1
    {"min": [30.0, 0.0, 15.0], "max": [36.0, 4.0, 17.0]},
    {"min": [35.0, 0.0, 5.8], "max": [37.0, 4.0, 11.8]},
    {"min": [30.0, 0.0, -17.0], "max": [36.0, 4.0, -15.0]},
    {"min": [35.0, 0.0, -11.8], "max": [37.0, 4.0, -5.8]},
    # sx = -1
    {"min": [-36.0, 0.0, 15.0], "max": [-30.0, 4.0, 17.0]},
    {"min": [-37.0, 0.0, 5.8], "max": [-35.0, 4.0, 11.8]},
    {"min": [-36.0, 0.0, -17.0], "max": [-30.0, 4.0, -15.0]},
    {"min": [-37.0, 0.0, -11.8], "max": [-35.0, 4.0, -5.8]},
]

# Add corner towers & roofs
for px, pz in [(24, 24), (-24, 24), (24, -24), (-24, -24)]:
    # Tower: scale=(5, 9, 5) position=(px, 4.5, pz)
    STATIC_COLLIDERS.append({"min": [px - 2.5, 0.0, pz - 2.5], "max": [px + 2.5, 9.0, pz + 2.5]})
    # Roof: scale=(7, 0.4, 7) position=(px, 9.2, pz)
    STATIC_COLLIDERS.append({"min": [px - 3.5, 9.0, pz - 3.5], "max": [px + 3.5, 9.4, pz + 3.5]})

# Add crate clusters
for cx, cz in [(15, 33), (-15, 33), (15, -33), (-15, -33), (33, 15), (-33, 15), (33, -15), (-33, -15)]:
    # Crate 1: scale=(1.6, 1.6, 1.6) position=(cx, 0.8, cz)
    STATIC_COLLIDERS.append({"min": [cx - 0.8, 0.0, cz - 0.8], "max": [cx + 0.8, 1.6, cz + 0.8]})
    # Crate 2: scale=(1.2, 1.2, 1.2) position=(cx+2.2, 0.6, cz+1.8)
    STATIC_COLLIDERS.append({"min": [cx + 2.2 - 0.6, 0.0, cz + 1.8 - 0.6], "max": [cx + 2.2 + 0.6, 1.2, cz + 1.8 + 0.6]})

# Add climb route platform details
# top_pad: scale=(14, 1.0, 14), position=(34, 4.2, 68)
STATIC_COLLIDERS.append({"min": [27.0, 3.7, 61.0], "max": [41.0, 4.7, 75.0]})
STATIC_COLLIDERS.append({"min": [40.0, 0.0, 54.0], "max": [41.0, 6.0, 68.0]})
STATIC_COLLIDERS.append({"min": [27.0, 0.0, 54.0], "max": [28.0, 6.0, 68.0]})

