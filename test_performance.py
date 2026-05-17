import unittest
from unittest.mock import patch

from performance import (
    PerformanceTunedAgent,
    PrivacyAwareResponseCache,
    get_validated_env_int,
    normalize_prompt,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class FakeAgent:
    def __init__(self, prefix):
        self.prefix = prefix
        self.calls = []

    def invoke(self, payload):
        self.calls.append(dict(payload))
        return {"output": f"{self.prefix}:{payload['input']}"}


class BrokenAgent:
    def invoke(self, payload):
        return {"output": 123}


class PerformanceTests(unittest.TestCase):
    def test_normalize_prompt_collapses_extra_whitespace(self):
        self.assertEqual("sensitive prompt", normalize_prompt(" sensitive   prompt "))

    def test_cache_uses_hashed_privacy_preserving_keys(self):
        clock = FakeClock()
        cache = PrivacyAwareResponseCache(max_entries=2, ttl_seconds=60, clock=clock)

        prompt = "sensitive   prompt"
        cache.set(prompt, "cached", stealth=True)

        self.assertEqual("cached", cache.get("sensitive prompt", stealth=True))
        self.assertIsNone(cache.get("sensitive prompt", stealth=False))
        stored_key = next(iter(cache._entries))
        self.assertNotEqual(prompt, stored_key)
        self.assertEqual(64, len(stored_key))

    def test_cached_replies_skip_repeat_primary_agent_work(self):
        """Cache hits are only allowed for stealth (stateless) requests.

        Standard requests use conversation memory, so the same prompt can
        produce different answers depending on conversation state.  Caching
        standard responses would serve stale, context-specific answers.
        """
        primary = FakeAgent("primary")
        stealth = FakeAgent("stealth")
        wrapper = PerformanceTunedAgent(
            primary_agent=primary,
            stealth_agent=stealth,
            response_cache=PrivacyAwareResponseCache(max_entries=4, ttl_seconds=60),
        )

        # Stealth requests are stateless and should be cached.
        first_stealth = wrapper.invoke({"input": "hello", "stealth": True})
        second_stealth = wrapper.invoke({"input": "hello", "stealth": True})
        self.assertFalse(first_stealth["cache_hit"])
        self.assertTrue(second_stealth["cache_hit"])
        self.assertEqual(1, len(stealth.calls))

        # Standard requests are NOT cached to avoid serving stale memory-dependent responses.
        first_std = wrapper.invoke({"input": "hello", "stealth": False})
        second_std = wrapper.invoke({"input": "hello", "stealth": False})
        self.assertFalse(first_std["cache_hit"])
        self.assertFalse(second_std["cache_hit"])

    def test_negative_cache_settings_raise_value_error(self):
        with self.assertRaises(ValueError):
            PrivacyAwareResponseCache(max_entries=-1)
        with self.assertRaises(ValueError):
            PrivacyAwareResponseCache(ttl_seconds=-1)

    def test_invalid_memory_window_env_raises_value_error(self):
        with patch.dict("os.environ", {"AGENT_MEMORY_WINDOW": "-1"}, clear=False):
            with self.assertRaises(ValueError):
                get_validated_env_int("AGENT_MEMORY_WINDOW", 6, minimum=1)

    def test_invalid_agent_output_raises_type_error(self):
        wrapper = PerformanceTunedAgent(primary_agent=BrokenAgent())

        with self.assertRaises(TypeError):
            wrapper.invoke({"input": "hello"})

    def test_stealth_requests_use_stateless_agent_path(self):
        primary = FakeAgent("primary")
        stealth = FakeAgent("stealth")
        wrapper = PerformanceTunedAgent(
            primary_agent=primary,
            stealth_agent=stealth,
            response_cache=PrivacyAwareResponseCache(max_entries=4, ttl_seconds=60),
        )

        response = wrapper.invoke({"input": "hello", "stealth": True})

        self.assertEqual("stealth:hello", response["output"])
        self.assertTrue(response["stealth"])
        self.assertEqual(0, len(primary.calls))
        self.assertEqual(1, len(stealth.calls))


if __name__ == "__main__":
    unittest.main()
