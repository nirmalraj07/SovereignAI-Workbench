"""
TOTP verification with replay protection. pyotp's bare `TOTP.verify()`
accepts the same valid code repeatedly for its entire ~30-90s validity
window (checked live against a real backend — see
docs/DEPLOYMENT.md "MFA" section) — a code observed once (shoulder-surf,
compromised client log, MITM before TLS termination, etc.) stays usable
until it naturally expires. This closes that gap: each user tracks the
time-step of their last successfully-used code, and a code matching a
step at or before that is rejected even if it's otherwise a valid code
for the current time window.
"""
from __future__ import annotations
import time
import pyotp


def verify_totp_with_replay_protection(secret: str, code: str, last_used_step: int | None,
                                        valid_window: int = 1, step_seconds: int = 30) -> tuple[bool, int | None]:
    """
    Returns (is_valid, matched_step). On success, the caller MUST persist
    matched_step as the user's new last_used_step — verification alone
    does not have side effects, keeping this function pure and testable.
    """
    totp = pyotp.TOTP(secret, interval=step_seconds)
    current_step = int(time.time()) // step_seconds

    for offset in range(-valid_window, valid_window + 1):
        candidate_step = current_step + offset
        candidate_time = candidate_step * step_seconds
        if totp.at(candidate_time) == code:
            if last_used_step is not None and candidate_step <= last_used_step:
                return False, None  # valid code, but already used — replay rejected
            return True, candidate_step

    return False, None
