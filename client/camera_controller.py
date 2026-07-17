# client/camera_controller.py
# ──────────────────────────────────────────────
# Third-person / First-person camera with proper
# FPP gun models via native Panda3D loader.
# ──────────────────────────────────────────────
import os
import math
from math import sin, cos, radians
from ursina import (Entity, camera, mouse, raycast, Vec3, color,
                    time as ursina_time, held_keys)
from config.settings import (
    CAMERA_DISTANCE, CAMERA_MIN_DISTANCE, CAMERA_HEIGHT,
    MOUSE_SENSITIVITY, NORMAL_FOV, ADS_FOV,
)

# ── Absolute OBJ paths ────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AR_OBJ  = os.path.join(_PROJECT_ROOT, "assest", "noramlgun", "obj", "m4a1_s.obj")
_AR_TEX  = os.path.join(_PROJECT_ROOT, "assest", "noramlgun", "obj", "M4A1-s.tga")
_SR_OBJ  = os.path.join(_PROJECT_ROOT, "assest", "sniper", "scifi_gun.obj")


def _load_np(abs_path, texture_path=None):
    """Load OBJ via native Panda3D loader, optionally applying a texture. Returns NodePath or None."""
    try:
        from panda3d.core import Filename, get_model_path
        # Convert OS absolute path to Panda3D path format (e.g. /c/path/to/model)
        panda_path = Filename.fromOsSpecific(abs_path).getFullpath()
        folder = os.path.dirname(panda_path)
        get_model_path().prepend_path(folder)
        np = base.loader.loadModel(panda_path)
        if np and texture_path:
            tex_panda = Filename.fromOsSpecific(texture_path).getFullpath()
            tex = base.loader.loadTexture(tex_panda)
            if tex:
                np.setTexture(tex, 1)
        return np
    except Exception as e:
        print(f"[Cam] model load failed: {abs_path}: {e}")
        return None


class ThirdPersonCamera(Entity):
    def __init__(self, target, **kwargs):
        super().__init__(**kwargs)
        self.target = target

        self._recoil_offset = 0.0
        self._sway_time     = 0.0
        self._sway_x        = 0.0
        self._sway_y        = 0.0
        self._bob_time      = 0.0
        self._ads_blend     = 0.0

        self.gun_pivot  = None
        self._np_ar     = None
        self._np_sr     = None
        self._fpp_built = False
        self._weapon_name = "Assault Rifle"  # track for scope hide

        self.yaw   = 0.0
        self.pitch = 0.0
        self.distance    = CAMERA_DISTANCE
        self._fov        = float(NORMAL_FOV)
        self.camera_mode = "tpp"

        if getattr(target, "is_local", False):
            self._build_fpp()

    # ── Build FPP geometry ────────────────────
    def _build_fpp(self):
        """
        gun_pivot parents to 'camera' so it follows the view.
        In FPP mode we enable it; in TPP we hide it.
        Barrel points into screen with setHpr(180, 0, 0):
          the model's +Y (barrel) → camera -Y (into screen).
        """
        skin  = color.rgb32(188, 150, 120)
        glove = color.rgb32(38, 40, 46)

        # Pivot on the right side of view (standard FPS)
        self.gun_pivot = Entity(parent=camera,
                                position=(0.30, -0.28, 0.50),
                                rotation=(0, 0, 0))

        # ── Right arm ─────────────────────────────────────────────
        Entity(parent=self.gun_pivot, model='cube', color=skin,
               scale=(0.055, 0.18, 0.055),
               position=(0.11, 0.03, 0.00),
               rotation=(38, 0, -12))
        Entity(parent=self.gun_pivot, model='cube', color=skin,
               scale=(0.07, 0.08, 0.10),
               position=(0.08, -0.04, 0.12),
               rotation=(10, 0, -5))
        Entity(parent=self.gun_pivot, model='cube', color=glove,
               scale=(0.065, 0.030, 0.085),
               position=(0.08, -0.09, 0.175))

        # ── Left arm ──────────────────────────────────────────────
        Entity(parent=self.gun_pivot, model='cube', color=skin,
               scale=(0.055, 0.18, 0.055),
               position=(-0.21, 0.06, 0.07),
               rotation=(28, 0, 16))
        Entity(parent=self.gun_pivot, model='cube', color=skin,
               scale=(0.07, 0.08, 0.10),
               position=(-0.16, -0.02, 0.19),
               rotation=(7, 0, 5))
        Entity(parent=self.gun_pivot, model='cube', color=glove,
               scale=(0.065, 0.030, 0.085),
               position=(-0.16, -0.07, 0.245))

        # ── Load gun NodePaths ─────────────────────────────────────
        # H=180: model's +Y barrel → camera -Y (INTO screen). Right-side up.
        ar = _load_np(_AR_OBJ, _AR_TEX)
        if ar:
            ar.reparentTo(self.gun_pivot)
            ar.setScale(0.016)
            # Position gun toward right hand
            ar.setPos(0.06, -0.02, 0.14)
            ar.setHpr(0, -10, 45)
            self._np_ar = ar
        else:
            self._np_ar = Entity(parent=self.gun_pivot, model='cube',
                                  color=color.rgb32(70, 72, 80),
                                  scale=(0.042, 0.048, 0.38),
                                  position=(0.02, -0.01, 0.22))

        # Sniper: same H=180; scaled slightly larger, dark metallic tint
        sr = _load_np(_SR_OBJ)
        if sr:
            sr.reparentTo(self.gun_pivot)
            sr.setScale(0.010)
            sr.setPos(0.06, -0.02, 0.14)
            sr.setHpr(0, -10, 45)
            sr.setColorScale(0.35, 0.38, 0.45, 1)
            sr.hide()
            self._np_sr = sr
        else:
            self._np_sr = Entity(parent=self.gun_pivot, model='cube',
                                  color=color.rgb32(40, 115, 200),
                                  scale=(0.038, 0.044, 0.46),
                                  position=(0.02, -0.01, 0.26),
                                  enabled=False)

        self.gun_pivot.enabled = False   # hidden until FPP
        self._fpp_built = True

    # ── Public API ────────────────────────────

    def add_recoil(self, amount):
        self._recoil_offset = min(1.0, self._recoil_offset + amount * 0.28)

    def switch_weapon_model(self, weapon_name):
        if not self._np_ar or not self._np_sr:
            return
        self._weapon_name = weapon_name  # track for scope hide
        is_sr = (weapon_name == "Sniper Rifle")
        self._toggle_np(self._np_ar, not is_sr)
        # Sniper shown only when NOT scoped (managed in _animate_fpp)
        if is_sr:
            self._toggle_np(self._np_sr, True)
        else:
            self._toggle_np(self._np_sr, False)

    def _toggle_np(self, np, show):
        try:
            if show:
                np.show() if hasattr(np, 'show') else setattr(np, 'enabled', True)
            else:
                np.hide() if hasattr(np, 'hide') else setattr(np, 'enabled', False)
        except Exception:
            pass

    def _set_fpp_visible(self, v):
        if self.gun_pivot:
            self.gun_pivot.enabled = v

    def input(self, key):
        if key in ('v', 'c'):
            self.camera_mode = "fpp" if self.camera_mode == "tpp" else "tpp"
            self._set_fpp_visible(self.camera_mode == "fpp" and
                                   getattr(self.target, 'alive', True))
        elif key == 'scroll up':
            if self.camera_mode == "tpp":
                self.distance = max(CAMERA_MIN_DISTANCE, self.distance - 0.5)
                if self.distance <= CAMERA_MIN_DISTANCE:
                    self.camera_mode = "fpp"
                    self._set_fpp_visible(getattr(self.target, 'alive', True))
        elif key == 'scroll down':
            if self.camera_mode == "fpp":
                self.camera_mode = "tpp"
                self._set_fpp_visible(False)
                self.distance = CAMERA_MIN_DISTANCE
            else:
                self.distance = min(CAMERA_DISTANCE * 2, self.distance + 0.5)

    def update(self):
        if not self.target:
            return
        dt = ursina_time.dt

        # ── Mouse look ────────────────────────
        self.yaw   += mouse.velocity[0] * MOUSE_SENSITIVITY
        self.pitch -= mouse.velocity[1] * MOUSE_SENSITIVITY
        self.pitch  = max(-50.0, min(70.0, self.pitch))
        self.target.rotation_y = self.yaw

        # ── FOV ───────────────────────────────
        if hasattr(self.target, 'weapon') and self.target.weapon:
            goal_fov = (self.target.weapon.current_config["ads_fov"]
                        if mouse.right else NORMAL_FOV)
        else:
            goal_fov = ADS_FOV if mouse.right else NORMAL_FOV
        if getattr(self.target, '_dash_timer', 0.0) > 0.0:
            goal_fov += 12.0
        self._fov += (goal_fov - self._fov) * min(1.0, 14.0 * dt)
        camera.fov = self._fov

        # ── ADS blend ─────────────────────────
        ads_t = 1.0 if mouse.right else 0.0
        self._ads_blend += (ads_t - self._ads_blend) * min(1.0, 12.0 * dt)

        # ── Recoil recovery ───────────────────
        if self._recoil_offset > 0:
            self._recoil_offset = max(0.0, self._recoil_offset - dt * 7.0)

        head = self.target.position + Vec3(0, CAMERA_HEIGHT, 0)

        if self.camera_mode == "fpp":
            # Hide body in FPP
            if self.target.visible:
                self.target.visible = False
            # Show/hide gun pivot based on alive state
            alive = getattr(self.target, 'alive', True)
            self._set_fpp_visible(alive)
            camera.position = head
            camera.rotation_x = self.pitch
            camera.rotation_y = self.yaw
            camera.rotation_z = 0
            if self._fpp_built and alive:
                self._animate_fpp(dt)
        else:
            if not self.target.visible:
                self.target.visible = True
            self._set_fpp_visible(False)

            yaw_r   = radians(self.yaw)
            pitch_r = radians(self.pitch)
            dx =  -sin(yaw_r) * cos(pitch_r)
            dy =   sin(pitch_r)
            dz =  -cos(yaw_r) * cos(pitch_r)
            orbit = Vec3(dx, dy, dz)

            ignore = [self.target] + list(self.target.children)
            ray = raycast(head, orbit.normalized(), distance=self.distance,
                          ignore=ignore)
            cam_dist = max(CAMERA_MIN_DISTANCE, ray.distance - 0.3) \
                       if ray.hit else self.distance
            camera.position = head + orbit.normalized() * cam_dist
            camera.rotation_x = self.pitch
            camera.rotation_y = self.yaw
            camera.rotation_z = 0

    # ── FPP procedural animation ─────────────
    def _animate_fpp(self, dt):
        moving  = held_keys['w'] or held_keys['s'] or \
                  held_keys['a'] or held_keys['d']
        sprint  = held_keys['left shift'] and moving

        # sway
        self._sway_time += dt * (0.9 if not moving else 0.4)
        si = 0.0020 * (1.0 - self._ads_blend * 0.85)
        tx = math.sin(self._sway_time * 1.25) * si
        ty = math.cos(self._sway_time * 0.85) * si * 0.55
        self._sway_x += (tx - self._sway_x) * min(1.0, 8.0 * dt)
        self._sway_y += (ty - self._sway_y) * min(1.0, 8.0 * dt)

        # bob
        bx = by = 0.0
        if moving:
            spd = 13.0 if sprint else 9.5
            amt = 0.009 if sprint else 0.005
            amt *= (1.0 - self._ads_blend * 0.7)
            self._bob_time += dt * spd
            bx = math.sin(self._bob_time) * amt * 0.45
            by = abs(math.cos(self._bob_time)) * amt
        else:
            self._bob_time = 0.0

        rz = -self._recoil_offset * 0.06
        ry =  self._recoil_offset * 0.012
        rx_rot = self._recoil_offset * 4.0

        # Hip = right-side hold; ADS = centered
        hip = Vec3( 0.30, -0.28, 0.50)
        ads = Vec3( 0.00, -0.16, 0.36)
        bp  = hip + (ads - hip) * self._ads_blend

        self.gun_pivot.position = Vec3(
            bp.x + self._sway_x + bx,
            bp.y + self._sway_y + by + ry,
            bp.z + rz)
        self.gun_pivot.rotation_x = rx_rot
        self.gun_pivot.rotation_y = 0
        self.gun_pivot.rotation_z = 0

        # ── Sniper scope: hide mesh when ADS so view is clean ─────
        if self._np_sr and getattr(self, '_weapon_name', '') == "Sniper Rifle":
            scoped = self._ads_blend > 0.35
            try:
                if scoped:
                    self._np_sr.hide()
                else:
                    self._np_sr.show()
            except Exception:
                pass
