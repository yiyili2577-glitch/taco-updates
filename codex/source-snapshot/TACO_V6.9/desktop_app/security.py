from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


OFFLINE_GRACE = timedelta(hours=72)
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)


class AccessDenied(PermissionError):
    pass


class PermissionService:
    def __init__(self, grants: dict[str, set[str]], readonly: bool = False):
        self.grants = grants
        self.readonly = readonly

    def require(self, actor: str, permission: str) -> None:
        if self.readonly and permission.startswith(("inventory.", "finance.", "masterdata.")):
            raise AccessDenied("系統目前為唯讀模式")
        if permission not in self.grants.get(actor, set()):
            raise AccessDenied("權限不足")


@dataclass(frozen=True)
class LicenseState:
    last_verified_at: datetime
    last_wall_clock: datetime
    revoked: bool = False
    license_version: str = "2.0"
    expires_on: date | None = None
    maintenance_until: date | None = None
    update_channel: str = "stable"


@dataclass(frozen=True)
class LicenseDecision:
    mode: str
    reason: str
    offline_remaining: timedelta


def evaluate_license(state: LicenseState, now: datetime | None = None) -> LicenseDecision:
    now = _utc(now or datetime.now(timezone.utc))
    verified = _utc(state.last_verified_at)
    last_clock = _utc(state.last_wall_clock)
    if state.license_version != "2.0":
        return LicenseDecision("readonly", "unsupported_license_version", timedelta())
    if state.revoked:
        return LicenseDecision("readonly", "revoked", timedelta())
    if now + CLOCK_SKEW_TOLERANCE < last_clock:
        return LicenseDecision("readonly", "clock_rollback", timedelta())
    if state.expires_on and now.date() > state.expires_on:
        return LicenseDecision("readonly", "license_expired", timedelta())
    elapsed = max(now - verified, timedelta())
    remaining = max(OFFLINE_GRACE - elapsed, timedelta())
    if elapsed <= OFFLINE_GRACE:
        return LicenseDecision("active", "verified_or_offline_grace", remaining)
    return LicenseDecision("readonly", "offline_grace_expired", timedelta())


def license_mode(state: LicenseState, now: datetime | None = None) -> str:
    return evaluate_license(state, now).mode


def maintenance_allows_update(state: LicenseState, published_on: date) -> bool:
    return state.maintenance_until is None or published_on <= state.maintenance_until


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
