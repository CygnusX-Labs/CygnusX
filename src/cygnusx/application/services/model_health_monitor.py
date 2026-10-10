"""进程内模型健康快照，用于动态路由的宽松准入与分类器熔断。"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class HealthEventKind(StrEnum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    THROTTLED = "throttled"
    CLIENT_ERROR = "client_error"


@dataclass(frozen=True)
class HealthSnapshot:
    provider_name: str
    healthy: bool
    error_rate: float
    p95_ms: float | None
    throttle_rate: float
    consecutive_failures: int
    last_event_at: datetime | None
    last_probe_at: datetime | None = None
    source: str = "passive"
    vendor: str | None = None
    latency_budget_breach_windows: int = 0


@dataclass(frozen=True)
class _Event:
    at: float
    observed_at: datetime
    kind: HealthEventKind
    duration_ms: float | None


class ModelHealthMonitor:
    def __init__(
        self,
        *,
        window_seconds: float = 300,
        half_life_seconds: float = 600,
        error_rate_threshold: float = 0.2,
        throttle_rate_threshold: float = 0.3,
    ) -> None:
        self.window_seconds = window_seconds
        self.half_life_seconds = half_life_seconds
        self.error_rate_threshold = error_rate_threshold
        self.throttle_rate_threshold = throttle_rate_threshold
        self._events: dict[str, list[_Event]] = {}
        self._snapshots: dict[str, HealthSnapshot] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._probe_failure_rounds = 0
        self._probe_backoff_until = 0.0
        self._probe_retry_names: set[str] = set()

    def record(
        self,
        provider_name: str,
        kind: HealthEventKind,
        duration_ms: float | None = None,
        *,
        source: str = "passive",
        vendor: str | None = None,
        latency_budget_ms: int | None = None,
    ) -> None:
        now = time.monotonic()
        lock = self._locks.setdefault(provider_name, threading.Lock())
        with lock:
            events = [e for e in self._events.get(provider_name, []) if now - e.at <= self.window_seconds]
            events.append(_Event(now, datetime.now(UTC), kind, duration_ms))
            self._events[provider_name] = events
            self._snapshots[provider_name] = self._build_snapshot(
                provider_name, events, now, source, vendor, latency_budget_ms
            )

    def providers_due_for_probe(self, provider_names: list[str]) -> list[str]:
        """Return providers without recent passive traffic or active probes."""
        now = time.monotonic()
        if now < self._probe_backoff_until:
            return []
        due: list[str] = []
        for name in provider_names:
            if name in self._probe_retry_names:
                due.append(name)
                continue
            events = self._events.get(name, [])
            last_event = events[-1].at if events else None
            snapshot = self._snapshots.get(name)
            if last_event is not None and now - last_event < self.window_seconds * 2:
                continue
            if snapshot and snapshot.last_probe_at and (
                datetime.now(UTC) - snapshot.last_probe_at
            ).total_seconds() < 60:
                continue
            due.append(name)
        return due

    def record_probe(
        self,
        provider_name: str,
        kind: HealthEventKind,
        duration_ms: float | None = None,
        *,
        vendor: str | None = None,
        latency_budget_ms: int | None = None,
    ) -> None:
        self.record(
            provider_name,
            kind,
            duration_ms,
            source="active",
            vendor=vendor,
            latency_budget_ms=latency_budget_ms,
        )

    async def probe_once(
        self,
        providers: list[object],
        probe: Callable[[object], Awaitable[float]],
        *,
        timeout_seconds: float = 5.0,
        concurrency: int = 4,
    ) -> None:
        """Run bounded active probes for providers with no recent traffic.

        ``probe`` performs the provider-specific max_tokens=1 request and returns
        its duration. The monitor deliberately does not own HTTP credentials or
        billing, keeping probe calls outside normal usage accounting.
        """
        import asyncio

        names = [str(getattr(item, "name", "")) for item in providers]
        due = set(self.providers_due_for_probe(names))
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def run(item: object) -> bool | None:
            name = str(getattr(item, "name", ""))
            if name not in due:
                return None
            started = time.perf_counter()
            async with semaphore:
                try:
                    duration = await asyncio.wait_for(probe(item), timeout_seconds)
                except TimeoutError:
                    self.record_probe(name, HealthEventKind.TIMEOUT, (time.perf_counter() - started) * 1000)
                    return False
                except Exception:  # noqa: BLE001 - a failed probe must not stop the sweep
                    self.record_probe(name, HealthEventKind.SERVER_ERROR, (time.perf_counter() - started) * 1000)
                    return False
                else:
                    self.record_probe(name, HealthEventKind.SUCCESS, float(duration))
                    return True

        results = await asyncio.gather(*(run(item) for item in providers))
        outcomes = [result for result in results if result is not None]
        if outcomes and all(result is False for result in outcomes):
            self._probe_retry_names.update(name for name in due)
            self._probe_failure_rounds += 1
            if self._probe_failure_rounds >= 3:
                self._probe_backoff_until = time.monotonic() + 300
        elif outcomes:
            self._probe_retry_names.difference_update(name for name in due)
            self._probe_failure_rounds = 0
            self._probe_backoff_until = 0.0

    def snapshot(self, provider_name: str) -> HealthSnapshot | None:
        return self._snapshots.get(provider_name)

    def provider_names(self) -> list[str]:
        """Return providers with observed health state."""
        return list(self._snapshots)

    @property
    def probe_failure_rounds(self) -> int:
        """Number of consecutive probe rounds where every due provider failed."""
        return self._probe_failure_rounds

    @property
    def probe_backoff_active(self) -> bool:
        """Whether active probing is currently paused after repeated failures."""
        return time.monotonic() < self._probe_backoff_until

    def is_healthy(self, provider_name: str) -> bool:
        snapshot = self.snapshot(provider_name)
        return snapshot is None or snapshot.healthy

    def classifier_healthy(self, provider_name: str) -> bool:
        snapshot = self.snapshot(provider_name)
        return snapshot is None or (
            snapshot.consecutive_failures < 1 and snapshot.error_rate <= 0.5
        )

    def _build_snapshot(
        self,
        provider_name: str,
        events: list[_Event],
        now: float,
        source: str,
        vendor: str | None,
        latency_budget_ms: int | None,
    ) -> HealthSnapshot:
        def weight(event: _Event) -> float:
            return math.pow(0.5, max(0.0, now - event.at) / self.half_life_seconds)

        total = sum(weight(event) for event in events) or 1.0
        failures = {HealthEventKind.TIMEOUT, HealthEventKind.SERVER_ERROR, HealthEventKind.CLIENT_ERROR}
        error_rate = sum(weight(e) for e in events if e.kind in failures) / total
        throttle_rate = sum(weight(e) for e in events if e.kind == HealthEventKind.THROTTLED) / total
        durations = sorted(e.duration_ms for e in events if e.kind == HealthEventKind.SUCCESS and e.duration_ms is not None)
        p95 = durations[min(len(durations) - 1, math.ceil(len(durations) * 0.95) - 1)] if durations else None
        consecutive = 0
        for event in reversed(events):
            if event.kind == HealthEventKind.SUCCESS:
                break
            if event.kind in failures or event.kind == HealthEventKind.THROTTLED:
                consecutive += 1
        healthy = (
            consecutive < 3
            and error_rate <= self.error_rate_threshold
            and throttle_rate <= self.throttle_rate_threshold
        )
        if latency_budget_ms is not None and p95 is not None:
            healthy = healthy and p95 <= latency_budget_ms
        latency_breach = latency_budget_ms is not None and p95 is not None and p95 > latency_budget_ms
        previous = self._snapshots.get(provider_name)
        breach_windows = (
            (previous.latency_budget_breach_windows if previous else 0) + 1
            if latency_breach
            else 0
        )
        return HealthSnapshot(
            provider_name=provider_name,
            healthy=healthy,
            error_rate=error_rate,
            p95_ms=p95,
            throttle_rate=throttle_rate,
            consecutive_failures=consecutive,
            last_event_at=events[-1].observed_at if events else None,
            last_probe_at=(
                datetime.now(UTC)
                if source == "active"
                else (previous.last_probe_at if previous else None)
            ),
            source=source,
            vendor=vendor,
            latency_budget_breach_windows=breach_windows,
        )


class NullHealthMonitor(ModelHealthMonitor):
    def record(self, *args: object, **kwargs: object) -> None:
        return

    def snapshot(self, provider_name: str) -> HealthSnapshot | None:
        return None
