# client/hud.py
# ──────────────────────────────────────────────
# Premium HUD — all elements are camera.ui children
# (screen-space 2D). Glassmorphism panels, dynamic
# crosshair, damage vignette, elimination banner.
# ──────────────────────────────────────────────
import math
from ursina import (Entity, Text, color, camera, destroy,
                    held_keys, time as ursina_time)
from config.settings import PLAYER_MAX_HP, DASH_COOLDOWN, GRENADE_COOLDOWN


# ── Small helper: a flat 2D box on camera.ui ──
def _ui_box(x, y, w, h, col):
    return Entity(parent=camera.ui, model='quad',
                  scale=(w, h), position=(x, y, 0),
                  color=col)


class GameHUD:
    def __init__(self):
        # ─────────────────────────────────────────
        # BOTTOM-LEFT: Health panel
        # ─────────────────────────────────────────
        # Glass background
        _ui_box(-0.56, -0.415, 0.40, 0.095, color.rgba32(8, 12, 22, 200))
        # Top accent line
        _ui_box(-0.56, -0.368, 0.40, 0.004, color.rgba32(0, 180, 255, 200))

        # Bar background
        self.hp_bg  = _ui_box(-0.56, -0.428, 0.375, 0.022, color.rgba32(30, 35, 50, 220))
        self.hp_bar = _ui_box(-0.56, -0.428, 0.375, 0.018, color.rgb32(40, 220, 80))
        self._hp_bar_full_w = 0.375
        self._hp_bar_x      = -0.56

        # HP number
        self.hp_text = Text(parent=camera.ui, text="100",
                            position=(-0.72, -0.387), scale=1.8,
                            color=color.white)
        # "HP" label
        Text(parent=camera.ui, text="HP",
             position=(-0.63, -0.387), scale=1.1,
             color=color.rgba32(140, 200, 255, 180))

        # ─────────────────────────────────────────
        # BOTTOM-RIGHT: Ammo panel
        # ─────────────────────────────────────────
        _ui_box(0.64, -0.415, 0.30, 0.095, color.rgba32(8, 12, 22, 200))
        _ui_box(0.64, -0.368, 0.30, 0.004, color.rgba32(255, 200, 40, 200))

        self.ammo_cur  = Text(parent=camera.ui, text="30",
                              position=(0.575, -0.392), scale=2.6,
                              color=color.rgb32(255, 220, 60))
        self.ammo_sep  = Text(parent=camera.ui, text="/",
                              position=(0.648, -0.400), scale=1.4,
                              color=color.rgba32(180, 180, 180, 180))
        self.ammo_max  = Text(parent=camera.ui, text="30",
                              position=(0.664, -0.408), scale=1.2,
                              color=color.rgba32(180, 180, 180, 200))
        self.weapon_label = Text(parent=camera.ui, text="M4A1",
                                 position=(0.567, -0.375), scale=0.85,
                                 color=color.rgba32(255, 200, 40, 210))

        # ─────────────────────────────────────────
        # K/D counter (above ammo panel)
        # ─────────────────────────────────────────
        self.kd_text = Text(parent=camera.ui, text="K 0  D 0",
                            position=(0.565, -0.355), scale=0.9,
                            color=color.rgba32(160, 175, 200, 210))

        # ─────────────────────────────────────────
        # CROSSHAIR (dynamic)
        # ─────────────────────────────────────────
        cr = color.rgba32(255, 255, 255, 230)
        # left / right / top / bottom lines
        self.ch = [
            Entity(parent=camera.ui, model='quad', scale=(0.016, 0.0018), color=cr),
            Entity(parent=camera.ui, model='quad', scale=(0.016, 0.0018), color=cr),
            Entity(parent=camera.ui, model='quad', scale=(0.0018, 0.016), color=cr),
            Entity(parent=camera.ui, model='quad', scale=(0.0018, 0.016), color=cr),
        ]
        self._ch_gap = 0.008
        self._ch_tgt = 0.008

        # ─────────────────────────────────────────
        # HIT MARKER (white ×)
        # ─────────────────────────────────────────
        self._hm_alpha = 0.0
        self.hm = [
            Entity(parent=camera.ui, model='quad',
                   scale=(0.026, 0.0038), color=color.rgba32(255,255,255,0),
                   rotation_z=45),
            Entity(parent=camera.ui, model='quad',
                   scale=(0.026, 0.0038), color=color.rgba32(255,255,255,0),
                   rotation_z=-45),
        ]

        # ─────────────────────────────────────────
        # DAMAGE VIGNETTE (4 dark-red edge bars)
        # ─────────────────────────────────────────
        self._vig_alpha = 0.0
        self._vigs = [
            _ui_box(0,  0.46,  2.0, 0.18, color.rgba32(180, 15, 15, 0)),
            _ui_box(0, -0.46,  2.0, 0.18, color.rgba32(180, 15, 15, 0)),
            _ui_box(-0.83, 0,  0.14, 2.0, color.rgba32(180, 15, 15, 0)),
            _ui_box( 0.83, 0,  0.14, 2.0, color.rgba32(180, 15, 15, 0)),
        ]

        # ─────────────────────────────────────────
        # DASH FLASH
        # ─────────────────────────────────────────
        self.dash_flash = _ui_box(0, 0, 2, 2, color.rgba32(0, 190, 255, 0))

        # ─────────────────────────────────────────
        # ELIMINATION BANNER
        # ─────────────────────────────────────────
        self.elim_text = Text(parent=camera.ui,
                              text="", origin=(0, 0), y=0.22,
                              scale=2.0, color=color.rgba32(255, 80, 60, 0))
        self._elim_t = 0.0

        # ─────────────────────────────────────────
        # STATUS TEXT (centre screen)
        # ─────────────────────────────────────────
        self.status = Text(parent=camera.ui,
                           text="", origin=(0, 0), y=0.12,
                           scale=2.0, color=color.rgb32(255, 80, 60))

        # ─────────────────────────────────────────
        # KILLS TO WIN mini banner (top centre, auto-hides)
        # ─────────────────────────────────────────
        self._ktw_panel = _ui_box(0, 0.415, 0.30, 0.055, color.rgba32(8, 12, 22, 200))
        _ui_box(0, 0.442, 0.30, 0.003, color.rgba32(255, 200, 40, 200))
        self.ktw_text = Text(parent=camera.ui,
                             text="", origin=(0, 0), y=0.41,
                             scale=1.15, color=color.rgb32(255, 200, 40))
        self._ktw_timer = 0.0   # show for N seconds then hide

        # ─────────────────────────────────────────
        # ABILITY INDICATORS (bottom centre, premium button panels)
        # ─────────────────────────────────────────
        # General background bar
        _ui_box(0, -0.415, 0.32, 0.095, color.rgba32(8, 12, 22, 200))
        _ui_box(0, -0.368, 0.32, 0.004, color.rgba32(100, 100, 100, 150))

        # DASH [F] button frame (Cyan glow)
        self.dash_btn_bg = _ui_box(-0.065, -0.415, 0.09, 0.065, color.rgba32(0, 190, 255, 30))
        self.dash_btn_border = _ui_box(-0.065, -0.415, 0.092, 0.067, color.rgba32(0, 220, 255, 120))
        # Keep border behind background
        self.dash_btn_bg.z = -0.01
        self.dash_icon = Text(parent=camera.ui, text="[F] DASH",
                              origin=(0, 0), position=(-0.065, -0.395),
                              scale=0.9, color=color.rgb32(0, 220, 255))
        self.dash_cd   = Text(parent=camera.ui, text="READY",
                              origin=(0, 0), position=(-0.065, -0.425),
                              scale=0.85, color=color.rgb32(0, 220, 255))

        # GRENADE [G] button frame (Orange glow)
        self.gren_btn_bg = _ui_box(0.065, -0.415, 0.09, 0.065, color.rgba32(255, 130, 20, 30))
        self.gren_btn_border = _ui_box(0.065, -0.415, 0.092, 0.067, color.rgba32(255, 155, 30, 120))
        self.gren_btn_bg.z = -0.01
        self.gren_icon = Text(parent=camera.ui, text="[G] NADE",
                              origin=(0, 0), position=(0.065, -0.395),
                              scale=0.9, color=color.rgb32(255, 155, 30))
        self.gren_cd   = Text(parent=camera.ui, text="READY",
                              origin=(0, 0), position=(0.065, -0.425),
                              scale=0.85, color=color.rgb32(255, 155, 30))

        # ─────────────────────────────────────────
        # PING
        # ─────────────────────────────────────────
        self.ping_text = Text(parent=camera.ui, text="",
                              position=(0.72, 0.47), scale=0.9,
                              color=color.rgba32(140, 140, 155, 200))

        # ─────────────────────────────────────────
        # KILL FEED (top-right)
        # ─────────────────────────────────────────
        self._feed = []   # [(Text, remaining)]

        # ─────────────────────────────────────────
        # SCOREBOARD (TAB)
        # ─────────────────────────────────────────
        self.sb_panel = Entity(parent=camera.ui, model='quad',
                               scale=(0.65, 0.62), position=(-0.15, 0.02),
                               color=color.rgba32(6, 10, 18, 235), enabled=False)
        Entity(parent=self.sb_panel, model='quad',
               scale=(0.92, 0.003), position=(0, 0.45, -0.01),
               color=color.rgba32(0, 180, 255, 160))
        Text(parent=self.sb_panel, text="S C O R E B O A R D",
             origin=(0, 0), y=0.42, scale=2.0,
             color=color.rgb32(60, 200, 255))
        Text(parent=self.sb_panel,
             text="  PLAYER                  KILLS   DEATHS",
             origin=(-0.5, 0), y=0.33, scale=1.25,
             color=color.rgba32(160, 170, 190, 200))
        self._sb_rows = []

        # ─────────────────────────────────────────
        # KEYBINDS (TAB, right side)
        # ─────────────────────────────────────────
        self.kb_panel = Entity(parent=camera.ui, model='quad',
                               scale=(0.26, 0.62), position=(0.54, 0.02),
                               color=color.rgba32(6, 10, 18, 235), enabled=False)
        Entity(parent=self.kb_panel, model='quad',
               scale=(0.92, 0.003), position=(0, 0.45, -0.01),
               color=color.rgba32(255, 180, 40, 160))
        Text(parent=self.kb_panel, text="K E Y S",
             origin=(0, 0), y=0.42, scale=1.8,
             color=color.rgb32(255, 180, 40))
        _binds = [
            ("WASD", "Move"), ("SPACE", "Jump"), ("LMB", "Shoot"),
            ("RMB", "ADS"), ("1 / 2", "Weapon"), ("R", "Reload"),
            ("G", "Grenade"), ("F", "Dash"), ("K", "Respawn"),
            ("V", "FPP/TPP"), ("TAB", "Scores"), ("ESC", "Quit"),
        ]
        for i, (k, a) in enumerate(_binds):
            y = 0.29 - i * 0.066
            Text(parent=self.kb_panel, text=k,
                 origin=(-0.5, 0), x=-0.44, y=y, scale=1.2,
                 color=color.rgb32(60, 210, 255))
            Text(parent=self.kb_panel, text=a,
                 origin=(0.5, 0), x=0.44, y=y, scale=1.2,
                 color=color.rgb32(200, 205, 215))

        # track all owned entities for cleanup
        self._all_ents = []

    # ─── PER-FRAME ────────────────────────────

    def update_tick(self, dt):
        # -- crosshair gap animation --
        self._ch_gap += (self._ch_tgt - self._ch_gap) * min(1.0, 15.0 * dt)
        gap = self._ch_gap
        self.ch[0].position = (-gap - 0.009, 0, 0)
        self.ch[1].position = ( gap + 0.009, 0, 0)
        self.ch[2].position = (0,  gap + 0.009, 0)
        self.ch[3].position = (0, -gap - 0.009, 0)

        # crosshair expansion from movement
        moving = held_keys['w'] or held_keys['s'] or held_keys['a'] or held_keys['d']
        self._ch_tgt = 0.005 if (mouse_right_held() and not moving) else (0.014 if moving else 0.008)

        # -- hit marker fade --
        if self._hm_alpha > 0:
            self._hm_alpha = max(0.0, self._hm_alpha - dt * 6.0)
            a = int(self._hm_alpha * 255)
            for hm in self.hm:
                hm.color = color.rgba32(255, 255, 255, a)

        # -- damage vignette fade --
        if self._vig_alpha > 0:
            self._vig_alpha = max(0.0, self._vig_alpha - dt * 2.5)
            a = int(self._vig_alpha * 190)
            for v in self._vigs:
                v.color = color.rgba32(180, 15, 15, a)

        # -- dash flash fade --
        if self.dash_flash.color.a > 0:
            a = max(0, self.dash_flash.color.a - dt * 5)
            self.dash_flash.color = color.rgba32(0, 190, 255, int(a * 255))

        # -- elimination banner fade --
        if self._elim_t > 0:
            self._elim_t -= dt
            if self._elim_t <= 0:
                self.elim_text.color = color.rgba32(255, 80, 60, 0)
            elif self._elim_t < 0.6:
                fade = int(self._elim_t / 0.6 * 255)
                self.elim_text.color = color.rgba32(255, 80, 60, fade)

        # -- kills-to-win banner auto-hide --
        if self._ktw_timer > 0:
            self._ktw_timer -= dt
            if self._ktw_timer <= 0:
                self.ktw_text.text = ""
                self._ktw_panel.color = color.rgba32(0, 0, 0, 0)

        # -- kill feed --
        alive = []
        for txt, ttl in self._feed:
            ttl -= dt
            if ttl <= 0:
                destroy(txt)
            else:
                alive.append((txt, ttl))
        self._feed = alive
        for i, (t, _) in enumerate(self._feed):
            t.y = 0.44 - i * 0.036

        # -- scoreboard / keybinds toggle --
        tab = bool(held_keys['tab'])
        self.sb_panel.enabled = tab
        self.kb_panel.enabled = tab

    # ─── PUBLIC API ───────────────────────────

    def set_hp(self, hp):
        hp = max(0, min(PLAYER_MAX_HP, hp))
        ratio = hp / PLAYER_MAX_HP
        new_w = self._hp_bar_full_w * ratio
        self.hp_bar.scale_x = new_w
        # anchor left edge
        self.hp_bar.x = self._hp_bar_x - self._hp_bar_full_w * 0.5 * (1 - ratio)
        self.hp_text.text = str(hp)
        if ratio > 0.5:
            self.hp_bar.color = color.rgb32(40, 220, 80)
        elif ratio > 0.25:
            self.hp_bar.color = color.rgb32(240, 175, 30)
        else:
            self.hp_bar.color = color.rgb32(235, 50, 50)

    def set_ammo(self, cur, mx, weapon_name="Assault Rifle"):
        self.ammo_cur.text = str(cur)
        self.ammo_max.text = str(mx)
        if weapon_name == "Assault Rifle":
            self.weapon_label.text = "M4A1"
            self.ammo_cur.color   = color.rgb32(255, 220, 60)
            self.weapon_label.color = color.rgba32(255, 200, 40, 210)
        else:
            self.weapon_label.text = "SNIPER"
            self.ammo_cur.color   = color.rgb32(60, 200, 255)
            self.weapon_label.color = color.rgba32(60, 200, 255, 210)

    def set_kd(self, kills, deaths):
        self.kd_text.text = f"K {kills}  D {deaths}"

    def flash_hit(self):
        self._hm_alpha = 1.0
        for hm in self.hm:
            hm.color = color.rgba32(255, 255, 255, 255)
        self._ch_tgt = 0.022   # expand crosshair

    def expand_crosshair(self):
        self._ch_tgt = 0.022

    def flash_damage(self):
        self._vig_alpha = 1.0

    def flash_dash(self):
        self.dash_flash.color = color.rgba32(0, 190, 255, 45)

    def show_elimination(self, name):
        self.elim_text.text = f"ELIMINATED  {name.upper()}"
        self.elim_text.color = color.rgba32(255, 80, 60, 255)
        self._elim_t = 2.5

    def set_status(self, msg):
        self.status.text = msg

    def show_kills_to_win(self, n):
        """Show 'KILLS TO WIN: N' briefly in the top centre then disappear."""
        self.ktw_text.text = f"KILLS TO WIN: {n}"
        self._ktw_panel.color = color.rgba32(8, 12, 22, 200)
        self._ktw_timer = 4.0   # show for 4 s then vanish

    def set_ping(self, ms):
        self.ping_text.text = f"{ms} ms"

    def update_cooldowns(self, dash_cd, grenade_cd,
                         dash_max=DASH_COOLDOWN, grenade_max=GRENADE_COOLDOWN):
        if dash_cd > 0:
            self.dash_cd.text = f"{dash_cd:.1f}s"
            self.dash_icon.color = color.rgba32(100, 100, 110, 200)
            self.dash_cd.color   = color.rgba32(100, 100, 110, 200)
        else:
            self.dash_cd.text = "READY"
            self.dash_icon.color = color.rgb32(0, 220, 255)
            self.dash_cd.color   = color.rgb32(0, 220, 255)

        if grenade_cd > 0:
            self.gren_cd.text = f"{grenade_cd:.1f}s"
            self.gren_icon.color = color.rgba32(100, 100, 110, 200)
            self.gren_cd.color   = color.rgba32(100, 100, 110, 200)
        else:
            self.gren_cd.text = "READY"
            self.gren_icon.color = color.rgb32(255, 155, 30)
            self.gren_cd.color   = color.rgb32(255, 155, 30)

    def add_feed(self, msg):
        txt = Text(parent=camera.ui,
                   text=f"  {msg}  ",
                   position=(0.56, 0.44), scale=1.0,
                   color=color.white,
                   background=True,
                   background_color=color.rgba32(8, 12, 22, 190))
        self._feed.insert(0, (txt, 5.0))

    def draw_scoreboard(self, players):
        for r in self._sb_rows:
            destroy(r)
        self._sb_rows.clear()
        ranked = sorted(players.values(),
                        key=lambda p: p.get("kills", 0), reverse=True)
        for i, p in enumerate(ranked):
            if i % 2 == 0:
                bg = Entity(parent=self.sb_panel, model='quad',
                            scale=(0.92, 0.052), y=0.24 - i * 0.062,
                            color=color.rgba32(30, 38, 55, 130))
                self._sb_rows.append(bg)
            row = Text(parent=self.sb_panel,
                       text=f"  {p.get('name','?'):<22} {p.get('kills',0):<8}{p.get('deaths',0)}",
                       origin=(-0.5, 0), y=0.24 - i * 0.062,
                       scale=1.2, color=color.white)
            self._sb_rows.append(row)

    def destroy_all(self):
        objs = [self.hp_bg, self.hp_bar, self.hp_text,
                self.ammo_cur, self.ammo_max, self.ammo_sep,
                self.weapon_label, self.kd_text,
                self.dash_icon, self.dash_cd, self.gren_icon, self.gren_cd,
                self.dash_btn_bg, self.dash_btn_border, self.gren_btn_bg, self.gren_btn_border,
                self.dash_flash, self.elim_text, self.status,
                self.ping_text, self.ktw_text, self._ktw_panel,
                self.sb_panel, self.kb_panel]
        for o in objs:
            try:
                destroy(o)
            except Exception:
                pass
        for v in self._vigs:
            try: destroy(v)
            except Exception: pass
        for h in self.hm:
            try: destroy(h)
            except Exception: pass
        for c in self.ch:
            try: destroy(c)
            except Exception: pass
        for txt, _ in self._feed:
            try: destroy(txt)
            except Exception: pass
        for r in self._sb_rows:
            try: destroy(r)
            except Exception: pass


# ── helper: is right mouse held ───────────────
def mouse_right_held():
    try:
        from ursina import mouse as urs_mouse
        return urs_mouse.right
    except Exception:
        return False
