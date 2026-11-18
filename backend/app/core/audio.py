"""Non-blocking audio alert for weapon detection demo."""
from __future__ import annotations

import sys
import threading
import time

_last_siren_time = 0.0
_lock = threading.Lock()


def trigger_weapon_siren(cooldown_seconds: float = 3.0) -> bool:
    """Triggers an emergency siren asynchronously on Windows. Rate-limited."""
    global _last_siren_time
    if sys.platform != "win32":
        return False

    with _lock:
        now = time.monotonic()
        if now - _last_siren_time < cooldown_seconds:
            return False
        _last_siren_time = now

    def _play():
        try:
            import winsound
            # Alternating high/low alert siren
            for _ in range(2):
                winsound.Beep(1600, 140)
                time.sleep(0.04)
                winsound.Beep(900, 140)
                time.sleep(0.04)
        except Exception:
            pass

    thread = threading.Thread(target=_play, daemon=True)
    thread.start()
    return True
