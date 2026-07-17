# main.py
# ──────────────────────────────────────────────
# Entry point for Ironsight Arena.
# Shows the menu, optionally starts a server
# thread if hosting, then runs the Ursina loop.
# ──────────────────────────────────────────────
import sys
import os
import threading
import time as std_time

# ── CRITICAL: set working directory to the folder
#    containing main.py, so that all relative imports
#    and Ursina asset lookups work regardless of how
#    the script is launched ─────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(_THIS_DIR)
sys.path.insert(0, _THIS_DIR)

# PyInstaller onefile support
if getattr(sys, '_MEIPASS', None):
    sys.path.insert(0, sys._MEIPASS)

from ursina import Ursina, window, color, camera, scene

from server.server import ArenaServer 
from client.client import GameClient

client = None
_server = None


def update():
    if client:
        try:
            client.update()
        except Exception as e:
            print(f"[Update Error] {e}")


def _start_server(nickname, server_name=None, speed_mult=1.0, ammo_mult=1.0, kills_to_win=10):
    global _server
    srv_name = server_name if server_name else f"{nickname}'s Server"
    _server = ArenaServer(host_name=srv_name, speed_mult=speed_mult, ammo_mult=ammo_mult, kills_to_win=kills_to_win)
    _server.start()


def _add_firewall_rules():
    import ctypes
    import sys
    import os

    # Only run on Windows
    if os.name != 'nt':
        return

    try:
        # Check if already running with admin privileges
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False

    exe_path = os.path.abspath(sys.executable)

    # Inline powershell script to configure firewall rules (clears old rules first)
    ps_commands = (
        f"Remove-NetFirewallRule -DisplayName 'Ironsight Arena UDP' -ErrorAction SilentlyContinue; "
        f"Remove-NetFirewallRule -DisplayName 'Ironsight Arena Executable' -ErrorAction SilentlyContinue; "
        f"New-NetFirewallRule -DisplayName 'Ironsight Arena UDP' -Direction Inbound -Protocol UDP -LocalPort 7777-7787 -Action Allow -Profile Any -ErrorAction SilentlyContinue; "
        f"New-NetFirewallRule -DisplayName 'Ironsight Arena Executable' -Direction Inbound -Program '{exe_path}' -Action Allow -Profile Any -ErrorAction SilentlyContinue"
    )

    if is_admin:
        import subprocess
        try:
            subprocess.run(['powershell', '-ExecutionPolicy', 'Bypass', '-Command', ps_commands], capture_output=True, creationflags=0x08000000)
        except Exception:
            pass
    else:
        # Check if we already asked / tried to elevate during this execution (prevent infinite prompt loops)
        if not getattr(sys, '_firewall_prompted', False):
            sys._firewall_prompted = True
            try:
                # Trigger Windows UAC prompt to run powershell with bypass
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "powershell.exe",
                    f"-ExecutionPolicy Bypass -Command \"{ps_commands}\"",
                    None,
                    0 # Hide console window
                )
                print("[System] Windows UAC prompt requested to configure Firewall rules (Profile: Any, Ports: 7777-7787) for UDP multiplayer.", flush=True)
            except Exception as e:
                print(f"[System] Failed to prompt for firewall rule: {e}", flush=True)


def main():
    global client
    _add_firewall_rules()
    app = Ursina(
        title="Ironsight Arena",
        borderless=False,
        fullscreen=False,
        show_ursina_logo=False,
        development_mode=False,
    )
    window.fps_counter.enabled = False
    window.cog_button.enabled = False
    window.exit_button.enabled = True
    window.color = color.rgb32(18, 20, 28)       # window clear color (dark)
    camera.orthographic = False

    client = GameClient()

    # ── wrap menu callbacks so we can inject
    #    the server thread when hosting ────────
    _original_host = client.host_game

    def on_host(nickname, server_name, speed_mult=1.0, ammo_mult=1.0, color_idx=0, kills_to_win=10):
        _start_server(nickname, server_name, speed_mult, ammo_mult, kills_to_win)
        client.selected_color_idx = color_idx
        std_time.sleep(0.3)
        actual_port = _server.port if _server else 5555
        _original_host(nickname, port=actual_port)

    if client.menu:
        client.menu.on_host_cb = on_host

    app.run()

    # cleanup
    if client:
        client.shutdown()
    if _server:
        _server.stop()


if __name__ == "__main__":
    main()
