from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_USER_AGENT = "paleo-paper-watcher/0.1 (+https://github.com/actions)"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class SourceRequestPolicy:
    name: str
    min_interval_seconds: float
    max_retries: int = 5
    retry_status_codes: frozenset[int] = RETRYABLE_STATUS_CODES


@dataclass
class SourceThrottleState:
    lock: asyncio.Lock
    last_request_started_at: float = 0.0


OPENALEX_POLICY = SourceRequestPolicy(name="openalex", min_interval_seconds=0.25)
CROSSREF_POLICY = SourceRequestPolicy(name="crossref", min_interval_seconds=1.0)
SEMANTIC_SCHOLAR_POLICY = SourceRequestPolicy(name="semantic_scholar", min_interval_seconds=1.0)
ARXIV_POLICY = SourceRequestPolicy(name="arxiv", min_interval_seconds=0.5)

_THROTTLE_STATES: dict[str, SourceThrottleState] = {}


def common_headers() -> dict[str, str]:
    return {"User-Agent": DEFAULT_USER_AGENT}


def crossref_headers() -> dict[str, str]:
    headers = common_headers()
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        headers["User-Agent"] = f"{DEFAULT_USER_AGENT} (mailto:{mailto})"
    return headers


def openalex_params() -> dict[str, str]:
    api_key = os.getenv("OPENALEX_API_KEY", "").strip()
    return {"api_key": api_key} if api_key else {}


def semantic_scholar_headers() -> dict[str, str]:
    headers = common_headers()
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def crossref_params() -> dict[str, str]:
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    return {"mailto": mailto} if mailto else {}


def _get_throttle_state(policy: SourceRequestPolicy) -> SourceThrottleState:
    state = _THROTTLE_STATES.get(policy.name)
    if state is None:
        state = SourceThrottleState(lock=asyncio.Lock())
        _THROTTLE_STATES[policy.name] = state
    return state


async def _apply_throttle(policy: SourceRequestPolicy) -> None:
    state = _get_throttle_state(policy)
    async with state.lock:
        now = time.monotonic()
        wait_seconds = max(0.0, policy.min_interval_seconds - (now - state.last_request_started_at))
        if wait_seconds > 0:
            LOGGER.info("source=%s throttle_wait=%.2fs", policy.name, wait_seconds)
            await asyncio.sleep(wait_seconds)
        state.last_request_started_at = time.monotonic()


def _compute_backoff_seconds(attempt: int) -> float:
    base_seconds = float(2**attempt)
    jitter = random.uniform(0.0, 0.25)
    return base_seconds + jitter


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    try:
        retry_dt = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None

    if retry_dt.tzinfo is None:
        retry_dt = retry_dt.replace(tzinfo=UTC)

    seconds = (retry_dt - datetime.now(UTC)).total_seconds()
    return max(0.0, seconds)


def _should_retry_response(response: httpx.Response, policy: SourceRequestPolicy) -> bool:
    return response.status_code in policy.retry_status_codes


def _should_retry_exception(exc: Exception) -> bool:
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


async def fetch_json_with_policy(
    *,
    client: httpx.AsyncClient,
    policy: SourceRequestPolicy,
    url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    response = await fetch_response_with_policy(
        client=client,
        policy=policy,
        url=url,
        params=params,
    )
    return response.json()


async def fetch_response_with_policy(
    *,
    client: httpx.AsyncClient,
    policy: SourceRequestPolicy,
    url: str,
    params: dict[str, Any],
) -> httpx.Response:
    for attempt in range(policy.max_retries):
        await _apply_throttle(policy)
        try:
            response = await client.get(url, params=params)
        except Exception as exc:
            if not _should_retry_exception(exc) or attempt == policy.max_retries - 1:
                raise

            wait_seconds = _compute_backoff_seconds(attempt)
            LOGGER.warning(
                "source=%s attempt=%s network_error=%s retry_in=%.2fs",
                policy.name,
                attempt + 1,
                exc.__class__.__name__,
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
            continue

        if response.status_code < 400:
            _log_rate_limit_headers(policy.name, response)
            return response

        if not _should_retry_response(response, policy) or attempt == policy.max_retries - 1:
            response.raise_for_status()

        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        wait_seconds = retry_after if retry_after is not None else _compute_backoff_seconds(attempt)
        LOGGER.warning(
            "source=%s attempt=%s status=%s retry_in=%.2fs",
            policy.name,
            attempt + 1,
            response.status_code,
            wait_seconds,
        )
        await asyncio.sleep(wait_seconds)

    raise RuntimeError(f"source={policy.name} exhausted retries")


def _log_rate_limit_headers(source_name: str, response: httpx.Response) -> None:
    remaining = response.headers.get("X-RateLimit-Remaining")
    limit = response.headers.get("X-RateLimit-Limit")
    reset = response.headers.get("X-RateLimit-Reset")
    credits = response.headers.get("X-RateLimit-Credits-Used")
    if remaining or limit or reset or credits:
        LOGGER.info(
            "source=%s rate_limit_limit=%s remaining=%s reset=%s credits=%s",
            source_name,
            limit,
            remaining,
            reset,
            credits,
        )


def log_missing_source_configuration() -> None:
    if not os.getenv("OPENALEX_API_KEY", "").strip():
        LOGGER.warning("OPENALEX_API_KEY nao configurada; OpenAlex usara limite diario reduzido.")
    if not os.getenv("CROSSREF_MAILTO", "").strip():
        LOGGER.warning("CROSSREF_MAILTO nao configurado; Crossref ficara sem identificacao recomendada.")
    if not os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip():
        LOGGER.warning("SEMANTIC_SCHOLAR_API_KEY nao configurada; Semantic Scholar pode sofrer throttling compartilhado.")


def cutoff_date_for(lookback_days: int) -> date:
    return datetime.now(UTC).date() - timedelta(days=lookback_days)


def parse_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        if len(text) == 4 and text.isdigit():
            return date(int(text), 1, 1)

        try:
            return date.fromisoformat(text)
        except ValueError:
            pass

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None

    return None


def parse_crossref_date_parts(value: Any) -> date | None:
    if not isinstance(value, dict):
        return None

    parts = value.get("date-parts")
    if not parts or not isinstance(parts, list):
        return None

    first = parts[0]
    if not isinstance(first, list) or not first:
        return None

    year = first[0]
    month = first[1] if len(first) > 1 else 1
    day = first[2] if len(first) > 2 else 1

    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break

    normalized = normalized.strip()
    return normalized or None


def filter_recent_papers(papers: list, lookback_days: int) -> list:
    cutoff = cutoff_date_for(lookback_days)
    today = datetime.now(UTC).date()
    filtered = []
    for paper in papers:
        if paper.published_date is None:
            filtered.append(paper)
            continue

        if cutoff <= paper.published_date <= today:
            filtered.append(paper)
    return filtered


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None
