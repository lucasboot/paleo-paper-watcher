from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

import main
from src.sources import base


class SourceHelpersTests(unittest.TestCase):
    def test_openalex_params_include_api_key_when_present(self) -> None:
        with patch.dict(os.environ, {"OPENALEX_API_KEY": "abc123"}, clear=False):
            self.assertEqual(base.openalex_params(), {"api_key": "abc123"})

    def test_openalex_params_omit_api_key_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(base.openalex_params(), {})

    def test_semantic_scholar_headers_include_api_key(self) -> None:
        with patch.dict(os.environ, {"SEMANTIC_SCHOLAR_API_KEY": "secret"}, clear=False):
            headers = base.semantic_scholar_headers()

        self.assertEqual(headers["x-api-key"], "secret")
        self.assertIn("User-Agent", headers)

    def test_crossref_mailto_is_used_in_params_and_user_agent(self) -> None:
        with patch.dict(os.environ, {"CROSSREF_MAILTO": "me@example.com"}, clear=False):
            params = base.crossref_params()
            headers = base.crossref_headers()

        self.assertEqual(params, {"mailto": "me@example.com"})
        self.assertIn("mailto:me@example.com", headers["User-Agent"])

    def test_source_concurrency_is_conservative_for_three_live_sources(self) -> None:
        self.assertEqual(main.SOURCE_CONCURRENCY["openalex"], 1)
        self.assertEqual(main.SOURCE_CONCURRENCY["crossref"], 1)
        self.assertEqual(main.SOURCE_CONCURRENCY["semantic_scholar"], 1)


class FetchPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        base._THROTTLE_STATES.clear()

    async def test_retry_after_header_is_respected(self) -> None:
        request = httpx.Request("GET", "https://example.org")
        responses = [
            httpx.Response(429, headers={"Retry-After": "3"}, request=request),
            httpx.Response(200, json={"ok": True}, request=request),
        ]

        client = AsyncMock()
        client.get = AsyncMock(side_effect=responses)

        with patch("src.sources.base.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            payload = await base.fetch_json_with_policy(
                client=client,
                policy=base.OPENALEX_POLICY,
                url="https://example.org",
                params={},
            )

        self.assertEqual(payload, {"ok": True})
        sleep_mock.assert_any_await(3.0)

    async def test_backoff_is_used_for_429_without_retry_after(self) -> None:
        request = httpx.Request("GET", "https://example.org")
        responses = [
            httpx.Response(429, request=request),
            httpx.Response(200, json={"ok": True}, request=request),
        ]

        client = AsyncMock()
        client.get = AsyncMock(side_effect=responses)

        with patch("src.sources.base.random.uniform", return_value=0.0), patch(
            "src.sources.base.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            await base.fetch_json_with_policy(
                client=client,
                policy=base.OPENALEX_POLICY,
                url="https://example.org",
                params={},
            )

        sleep_mock.assert_any_await(1.0)

    async def test_server_errors_retry_until_success(self) -> None:
        request = httpx.Request("GET", "https://example.org")
        responses = [
            httpx.Response(503, request=request),
            httpx.Response(200, json={"ok": True}, request=request),
        ]

        client = AsyncMock()
        client.get = AsyncMock(side_effect=responses)

        with patch("src.sources.base.random.uniform", return_value=0.0), patch(
            "src.sources.base.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            payload = await base.fetch_json_with_policy(
                client=client,
                policy=base.CROSSREF_POLICY,
                url="https://example.org",
                params={},
            )

        self.assertEqual(payload, {"ok": True})
        sleep_mock.assert_any_await(1.0)
        self.assertEqual(client.get.await_count, 2)

    async def test_non_retryable_4xx_is_raised_immediately(self) -> None:
        request = httpx.Request("GET", "https://example.org")
        client = AsyncMock()
        client.get = AsyncMock(side_effect=[httpx.Response(404, request=request)])

        with patch("src.sources.base.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            with self.assertRaises(httpx.HTTPStatusError):
                await base.fetch_json_with_policy(
                    client=client,
                    policy=base.CROSSREF_POLICY,
                    url="https://example.org",
                    params={},
                )

        sleep_mock.assert_not_awaited()
        self.assertEqual(client.get.await_count, 1)

    async def test_network_errors_retry(self) -> None:
        request = httpx.Request("GET", "https://example.org")
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=[
                httpx.ConnectTimeout("boom"),
                httpx.Response(200, json={"ok": True}, request=request),
            ]
        )

        with patch("src.sources.base.random.uniform", return_value=0.0), patch(
            "src.sources.base.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock:
            payload = await base.fetch_json_with_policy(
                client=client,
                policy=base.SEMANTIC_SCHOLAR_POLICY,
                url="https://example.org",
                params={},
            )

        self.assertEqual(payload, {"ok": True})
        sleep_mock.assert_any_await(1.0)

    async def test_throttle_waits_between_requests(self) -> None:
        request = httpx.Request("GET", "https://example.org")
        client = AsyncMock()
        client.get = AsyncMock(
            side_effect=[
                httpx.Response(200, json={"ok": 1}, request=request),
                httpx.Response(200, json={"ok": 2}, request=request),
            ]
        )

        monotonic_values = iter([0.0, 0.0, 0.1, 0.1])
        sleep_mock = AsyncMock()

        with patch("src.sources.base.time.monotonic", side_effect=lambda: next(monotonic_values)), patch(
            "src.sources.base.asyncio.sleep",
            new=sleep_mock,
        ):
            await base.fetch_json_with_policy(
                client=client,
                policy=base.OPENALEX_POLICY,
                url="https://example.org",
                params={},
            )
            await base.fetch_json_with_policy(
                client=client,
                policy=base.OPENALEX_POLICY,
                url="https://example.org",
                params={},
            )

        sleep_mock.assert_any_await(0.15)

    async def test_parallel_requests_are_serialized_by_throttle(self) -> None:
        request = httpx.Request("GET", "https://example.org")
        call_order: list[str] = []
        gate = asyncio.Event()
        release = asyncio.Event()

        async def fake_get(url: str, params: dict[str, str]) -> httpx.Response:
            call_order.append("start")
            gate.set()
            await release.wait()
            return httpx.Response(200, json={"ok": True}, request=request)

        client = AsyncMock()
        client.get = AsyncMock(side_effect=fake_get)

        task1 = asyncio.create_task(
            base.fetch_json_with_policy(
                client=client,
                policy=base.CROSSREF_POLICY,
                url="https://example.org",
                params={},
            )
        )
        await gate.wait()
        task2 = asyncio.create_task(
            base.fetch_json_with_policy(
                client=client,
                policy=base.CROSSREF_POLICY,
                url="https://example.org",
                params={},
            )
        )
        await asyncio.sleep(0)
        self.assertEqual(client.get.await_count, 1)
        release.set()
        await asyncio.gather(task1, task2)


if __name__ == "__main__":
    unittest.main()
