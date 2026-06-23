"""HTTP data collector for Korean Lotto 6/45 results."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import requests

from .models import Draw
from .validator import validate_draw_numbers


class CollectionError(Exception):
    """Raised when data collection fails."""


def _fetch_raw(draw_no: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Fetch raw JSON for a single draw number with retry logic."""
    url = cfg["data"]["api_url"]
    method = cfg["data"]["api_method"]
    max_retries: int = cfg["collection"]["max_retries"]
    backoff_base: float = cfg["collection"]["retry_backoff_base"]
    timeout: int = cfg["collection"]["request_timeout"]

    params = {"method": method, "drwNo": draw_no}

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            if data.get("returnValue") == "success":
                return data
            raise CollectionError(
                f"API returned non-success for draw {draw_no}: {data.get('returnValue')}"
            )
        except (requests.RequestException, CollectionError) as exc:
            if attempt < max_retries - 1:
                wait = backoff_base ** attempt
                time.sleep(wait)
            else:
                raise CollectionError(
                    f"Failed to fetch draw {draw_no} after {max_retries} attempts: {exc}"
                ) from exc
    # Should not reach here
    raise CollectionError(f"Failed to fetch draw {draw_no}")


def _parse_draw(data: dict[str, Any]) -> Draw:
    """Parse raw API JSON into a Draw object."""
    draw_no = int(data["drwNo"])
    draw_date = date.fromisoformat(data["drwNoDate"])
    numbers = sorted([
        int(data["drwtNo1"]),
        int(data["drwtNo2"]),
        int(data["drwtNo3"]),
        int(data["drwtNo4"]),
        int(data["drwtNo5"]),
        int(data["drwtNo6"]),
    ])
    bonus = int(data["bnusNo"])
    total_sales = int(data.get("totSellamnt", 0))
    first_winners = int(data.get("firstPrzwnerCo", 0))
    first_amount = int(data.get("firstWinamnt", 0))

    validate_draw_numbers(numbers, bonus)

    return Draw(
        draw_no=draw_no,
        draw_date=draw_date,
        numbers=numbers,
        bonus=bonus,
        total_sales=total_sales,
        first_winners=first_winners,
        first_amount=first_amount,
    )


def fetch_draw(draw_no: int, cfg: dict[str, Any]) -> Draw:
    """Fetch and parse a single draw."""
    raw = _fetch_raw(draw_no, cfg)
    return _parse_draw(raw)


def detect_latest_draw_no(cfg: dict[str, Any]) -> int:
    """Binary-search-style detection of the latest draw number."""
    # Start with a known recent draw (lotto started at 1 in 2002-12-07).
    # We probe from a high estimate downward.
    # As of 2024 the draw number is around 1160+; give extra headroom.
    low, high = 1, 2000
    latest = 1

    # First, find an upper bound that doesn't exist yet
    try:
        _fetch_raw(high, cfg)
        # If this succeeds, we need to search higher — rare edge case
        while True:
            high *= 2
            try:
                _fetch_raw(high, cfg)
            except CollectionError:
                break
    except CollectionError:
        pass

    # Binary search for the latest valid draw
    while low <= high:
        mid = (low + high) // 2
        try:
            _fetch_raw(mid, cfg)
            latest = mid
            low = mid + 1
        except CollectionError:
            high = mid - 1

    return latest


def collect_all_draws(
    cfg: dict[str, Any],
    start: int = 1,
    end: int | None = None,
    progress_callback: Any = None,
) -> list[Draw]:
    """Collect all draws from start to end (inclusive)."""
    if end is None:
        end = detect_latest_draw_no(cfg)

    draws: list[Draw] = []
    for draw_no in range(start, end + 1):
        try:
            draw = fetch_draw(draw_no, cfg)
            draws.append(draw)
            if progress_callback:
                progress_callback(draw_no, end)
        except CollectionError as exc:
            # Some draw numbers may be skipped (holidays etc.); warn and continue
            print(f"Warning: could not fetch draw {draw_no}: {exc}")

    return draws
