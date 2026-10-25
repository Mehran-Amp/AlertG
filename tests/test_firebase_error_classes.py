"""Phase 3C-1: pin firebase-admin==7.7.0 and lock the error classes that
app/notifier/fcm.py depends on, so a future upgrade cannot silently break
the UNREGISTERED / FCM_AUTH_ERROR classification.

Reality check on 7.7.0 (verified on both the dev machine and the server):
  * firebase_admin.exceptions.ThirdPartyAuthError does NOT exist (moved to
    firebase_admin.messaging.ThirdPartyAuthError).
  * firebase_admin.messaging.ApiCallError does NOT exist.
fcm.py already tolerates both with getattr(..., None) + `if t is not None`,
so the classification stays correct. These tests lock that behaviour: the
8 classes that MUST exist are asserted to exist; the 2 that do not are
asserted to be safely skipped without breaking the auth/unreg tuples.
"""
import pytest

from firebase_admin import exceptions as fb_exceptions
from firebase_admin import messaging

from app.notifier import fcm as fcm_module


# Classes that MUST exist in firebase-admin 7.7.0.
# fcm.py depends on every one of them for a distinct error path.
MUST_EXIST = [
    ("PermissionDeniedError", fb_exceptions),   # -> FCM_AUTH_ERROR
    ("ThirdPartyAuthError", messaging),          # -> FCM_AUTH_ERROR (messaging-side)
    ("InvalidArgumentError", fb_exceptions),    # -> INVALID_PAYLOAD
    ("UnavailableError", fb_exceptions),        # -> transient retry
    ("InternalError", fb_exceptions),           # -> transient retry
    ("UnregisteredError", messaging),           # -> UNREGISTERED
    ("SenderIdMismatchError", messaging),       # -> UNREGISTERED
    ("QuotaExceededError", messaging),          # -> transient retry
]

# Classes that fcm.py probes with getattr(..., None) and does NOT require.
# If a future upgrade re-adds them, fcm.py picks them up automatically;
# if they stay absent, the tuples stay smaller but still classify correctly.
ABSENT_IN_7_7_0 = [
    ("ThirdPartyAuthError", fb_exceptions),
    ("ApiCallError", messaging),
]


class TestFirebaseErrorClassesExist:
    """3C-1 / test 1: the 8 classes fcm.py actually relies on must exist."""

    @pytest.mark.parametrize("name,module", MUST_EXIST)
    def test_required_error_class_exists(self, name, module):
        assert hasattr(module, name), (
            f"firebase-admin 7.7.0 is missing {module.__name__}.{name}; "
            "app/notifier/fcm.py would silently misclassify errors."
        )


class TestAbsentClassesAreTolerated:
    """3C-1 / test 2: the 2 classes missing in 7.7.0 must be probed with
    getattr(..., None) and skipped, never crashing the import of fcm.py."""

    @pytest.mark.parametrize("name,module", ABSENT_IN_7_7_0)
    def test_absent_class_is_tolerated(self, name, module):
        # fcm.py builds its tuples at call time with getattr(..., None).
        # The classifier must be importable and callable even when this
        # class is gone.
        assert callable(fcm_module._send_fcm_sync)
        # And the getattr probe must return None (not raise AttributeError).
        assert getattr(module, name, None) is None, (
            f"{module.__name__}.{name} unexpectedly exists in 7.7.0; "
            "update ABSENT_IN_7_7_0 and re-verify fcm.py's tuple logic."
        )


class TestErrorClassification:
    """3C-1 / test 3: UNREGISTERED must never be swallowed by FCM_AUTH_ERROR,
    and PermissionDeniedError must be caught by the auth tuple."""

    def test_unregistered_is_not_auth_error(self):
        exc = messaging.UnregisteredError("unregistered")
        auth_types = tuple(t for t in (
            getattr(fb_exceptions, "PermissionDeniedError", None),
            getattr(fb_exceptions, "ThirdPartyAuthError", None),
            getattr(messaging, "ThirdPartyAuthError", None),
        ) if t is not None)
        unreg_types = tuple(t for t in (
            getattr(messaging, "UnregisteredError", None),
            getattr(messaging, "SenderIdMismatchError", None),
        ) if t is not None)
        assert unreg_types, "unreg_types is empty; fcm.py cannot classify dead tokens"
        assert auth_types, "auth_types is empty; fcm.py cannot classify auth errors"
        assert isinstance(exc, unreg_types)
        assert not isinstance(exc, auth_types), (
            "UnregisteredError must not be caught by auth_types, "
            "otherwise fcm.py returns FCM_AUTH_ERROR instead of UNREGISTERED."
        )

    def test_permission_denied_is_auth_error(self):
        exc = fb_exceptions.PermissionDeniedError("permission denied")
        auth_types = tuple(t for t in (
            getattr(fb_exceptions, "PermissionDeniedError", None),
            getattr(fb_exceptions, "ThirdPartyAuthError", None),
            getattr(messaging, "ThirdPartyAuthError", None),
        ) if t is not None)
        assert isinstance(exc, auth_types)