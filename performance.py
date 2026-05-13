#!/usr/bin/env python3
"""
Performance helpers for privacy-aware caching and low-footprint query execution.
"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from threading import RLock
from typing import Any, Callable, Dict, Optional


CacheEventCallback = Callable[[str, str], None]
CacheSizeCallback = Callable[[int], None]
StealthCallback = Callable[[], None]
AgentFactory = Callable[[], Any]


def normalize_prompt(prompt: str) -> str:
    return " ".join(prompt.split())


class PrivacyAwareResponseCache:
    def __init__(
        self,
        max_entries: int = 128,
        ttl_seconds: int = 300,
        clock: Callable[[], float] = time.monotonic,
        on_event: Optional[CacheEventCallback] = None,
        on_size_change: Optional[CacheSizeCallback] = None,
    ) -> None:
        if max_entries < 0:
            raise ValueError("max_entries must be >= 0")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._on_event = on_event
        self._on_size_change = on_size_change
        self._entries: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._lock = RLock()

    def _mode(self, stealth: bool) -> str:
        return "stealth" if stealth else "standard"

    def _emit_event(self, outcome: str, stealth: bool) -> None:
        if self._on_event:
            self._on_event(outcome, self._mode(stealth))

    def _emit_size(self) -> None:
        if self._on_size_change:
            self._on_size_change(len(self._entries))

    def _cache_key(self, prompt: str, stealth: bool) -> str:
        normalized = normalize_prompt(prompt)
        digest = hashlib.sha256(
            f"{self._mode(stealth)}:{normalized}".encode("utf-8")
        ).hexdigest()
        return digest

    def _enabled(self) -> bool:
        return self.max_entries > 0 and self.ttl_seconds > 0

    def get(self, prompt: str, stealth: bool = False) -> Optional[str]:
        if not self._enabled():
            self._emit_event("disabled", stealth)
            return None

        key = self._cache_key(prompt, stealth)
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                self._emit_event("miss", stealth)
                return None
            if entry["expires_at"] <= self._clock():
                self._entries.pop(key, None)
                self._emit_size()
                self._emit_event("expired", stealth)
                return None
            self._entries.move_to_end(key)
            self._emit_event("hit", stealth)
            return entry["response"]

    def set(self, prompt: str, response: str, stealth: bool = False) -> None:
        normalized = normalize_prompt(prompt)
        if not normalized or not response or not self._enabled():
            return

        key = self._cache_key(prompt, stealth)
        with self._lock:
            self._entries[key] = {
                "response": response,
                "expires_at": self._clock() + self.ttl_seconds,
            }
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            self._emit_size()


class PerformanceTunedAgent:
    def __init__(
        self,
        primary_agent: Any,
        stealth_agent: Optional[Any] = None,
        stealth_agent_factory: Optional[AgentFactory] = None,
        response_cache: Optional[PrivacyAwareResponseCache] = None,
        on_cache_event: Optional[CacheEventCallback] = None,
        on_stealth_request: Optional[StealthCallback] = None,
    ) -> None:
        self._primary_agent = primary_agent
        self._stealth_agent = stealth_agent
        self._stealth_agent_factory = stealth_agent_factory
        self._response_cache = response_cache
        self._on_cache_event = on_cache_event
        self._on_stealth_request = on_stealth_request

    def _resolve_agent(self, stealth: bool) -> Any:
        if not stealth:
            return self._primary_agent
        if self._stealth_agent is None and self._stealth_agent_factory is not None:
            self._stealth_agent = self._stealth_agent_factory()
        return self._stealth_agent or self._primary_agent

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = dict(payload)
        prompt = str(request.get("input", ""))
        stealth = bool(request.pop("stealth", False))
        use_cache = bool(request.pop("use_cache", True))
        mode = "stealth" if stealth else "standard"

        if stealth and self._on_stealth_request:
            self._on_stealth_request()

        if use_cache and self._response_cache:
            cached = self._response_cache.get(prompt, stealth=stealth)
            if cached is not None:
                return {"output": cached, "cache_hit": True, "stealth": stealth}
        elif self._on_cache_event:
            self._on_cache_event("bypass", mode)

        agent = self._resolve_agent(stealth)
        result = agent.invoke(request)
        output = result["output"] if isinstance(result, dict) else result
        if use_cache and self._response_cache and isinstance(output, str):
            self._response_cache.set(prompt, output, stealth=stealth)

        if isinstance(result, dict):
            wrapped = dict(result)
            wrapped["cache_hit"] = False
            wrapped["stealth"] = stealth
            return wrapped
        return {"output": output, "cache_hit": False, "stealth": stealth}
