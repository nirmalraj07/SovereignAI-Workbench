"""
Deterministic unit tests for TOTP replay protection
(security/mfa.py::verify_totp_with_replay_protection). Uses pyotp's `at()`
to generate codes for specific historical/future time-steps instead of
sleeping through real TOTP windows, so this runs in milliseconds.

This function was added after a real vulnerability check (Objective:
"Replay attack protection" in the auth security remediation pass) found
that bare `pyotp.TOTP.verify()` accepts the same valid code repeatedly for
its entire validity window — confirmed live against a running backend
(see the manual verification transcript in ARCHITECTURE.md) before this
test suite was written to lock the fix in place.
Run: pytest backend/tests/test_mfa_replay_protection.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyotp
from app.security.mfa import verify_totp_with_replay_protection

SECRET = pyotp.random_base32()
STEP_SECONDS = 30


def _code_for_step(step: int) -> str:
    totp = pyotp.TOTP(SECRET, interval=STEP_SECONDS)
    return totp.at(step * STEP_SECONDS)


class TestFirstUseAccepted:
    def test_valid_code_with_no_prior_use_is_accepted(self):
        import time
        current_step = int(time.time()) // STEP_SECONDS
        code = _code_for_step(current_step)
        is_valid, matched_step = verify_totp_with_replay_protection(SECRET, code, last_used_step=None)
        assert is_valid is True
        assert matched_step == current_step

    def test_wrong_code_is_rejected(self):
        is_valid, matched_step = verify_totp_with_replay_protection(SECRET, "000000", last_used_step=None)
        assert is_valid is False
        assert matched_step is None


class TestReplayProtection:
    def test_reusing_the_last_used_step_exactly_is_rejected(self):
        import time
        current_step = int(time.time()) // STEP_SECONDS
        code = _code_for_step(current_step)
        is_valid, _ = verify_totp_with_replay_protection(SECRET, code, last_used_step=current_step)
        assert is_valid is False

    def test_reusing_a_step_before_last_used_is_rejected(self):
        import time
        current_step = int(time.time()) // STEP_SECONDS
        old_code = _code_for_step(current_step - 1)
        # last_used_step is ahead of the code being presented — an
        # out-of-order/stale replay attempt.
        is_valid, _ = verify_totp_with_replay_protection(SECRET, old_code, last_used_step=current_step)
        assert is_valid is False

    def test_a_genuinely_new_later_step_is_accepted(self):
        import time
        current_step = int(time.time()) // STEP_SECONDS
        new_code = _code_for_step(current_step)
        is_valid, matched_step = verify_totp_with_replay_protection(
            SECRET, new_code, last_used_step=current_step - 5
        )
        assert is_valid is True
        assert matched_step == current_step


class TestClockDriftWindow:
    def test_code_from_one_step_ahead_accepted_within_valid_window(self):
        import time
        current_step = int(time.time()) // STEP_SECONDS
        future_code = _code_for_step(current_step + 1)
        is_valid, matched_step = verify_totp_with_replay_protection(
            SECRET, future_code, last_used_step=None, valid_window=1
        )
        assert is_valid is True
        assert matched_step == current_step + 1

    def test_code_two_steps_ahead_rejected_outside_default_window(self):
        import time
        current_step = int(time.time()) // STEP_SECONDS
        far_future_code = _code_for_step(current_step + 2)
        is_valid, _ = verify_totp_with_replay_protection(
            SECRET, far_future_code, last_used_step=None, valid_window=1
        )
        assert is_valid is False


class TestSequentialLogins:
    def test_two_logins_in_different_windows_both_succeed_and_advance_state(self):
        import time
        current_step = int(time.time()) // STEP_SECONDS

        code_a = _code_for_step(current_step)
        valid_a, step_a = verify_totp_with_replay_protection(SECRET, code_a, last_used_step=None)
        assert valid_a is True

        # Simulate persisting step_a, then a later login in the next window
        code_b = _code_for_step(current_step + 1)
        valid_b, step_b = verify_totp_with_replay_protection(SECRET, code_b, last_used_step=step_a)
        assert valid_b is True
        assert step_b > step_a
