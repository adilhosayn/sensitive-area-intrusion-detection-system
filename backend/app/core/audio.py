"""Non-blocking audio alert for weapon detection demo."""
from __future__ import annotations

import sys
import threading
import time

_last_siren_time = 0.0
_lock = threading.Lock()


def trigger_weapon_siren(cooldown_seconds: float = 2.0) -> bool:
    """Triggers an urgent, loud emergency siren asynchronously on Windows. Rate-limited."""
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
            # Trigger native Windows Critical Stop alert sound through mixer
            winsound.MessageBeep(winsound.MB_ICONHAND)

            # High-intensity piercing frequency alternating police siren
            # (2600Hz and 1900Hz are peak resonance for human ear and PC speakers)
            for _ in range(3):
                winsound.Beep(2600, 140)
                time.sleep(0.02)
                winsound.Beep(1900, 140)
                time.sleep(0.02)
        except Exception:
            pass

    thread = threading.Thread(target=_play, daemon=True)
    thread.start()
    return True
