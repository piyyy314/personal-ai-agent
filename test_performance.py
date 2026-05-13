import unittest

from performance import PerformanceTunedAgent, PrivacyAwareResponseCache


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


class PerformanceTests(unittest.TestCase):
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
        primary = FakeAgent("primary")
        stealth = FakeAgent("stealth")
        wrapper = PerformanceTunedAgent(
            primary_agent=primary,
            stealth_agent=stealth,
            response_cache=PrivacyAwareResponseCache(max_entries=4, ttl_seconds=60),
        )

        first = wrapper.invoke({"input": "hello"})
        second = wrapper.invoke({"input": "hello"})

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(1, len(primary.calls))

    def test_negative_cache_settings_raise_value_error(self):
        with self.assertRaises(ValueError):
            PrivacyAwareResponseCache(max_entries=-1)
        with self.assertRaises(ValueError):
            PrivacyAwareResponseCache(ttl_seconds=-1)

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
