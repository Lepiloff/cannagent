"""
Load Simulation: 3 concurrent clients with realistic multi-turn conversations.

Each client runs a full conversation scenario with follow-up queries,
simulating real user behavior against the live API.

Usage:
    docker compose exec api pytest tests/test_load_simulation.py -v -s
"""

import concurrent.futures
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests

API_BASE = "http://localhost:8000"
CHAT_URL = f"{API_BASE}/api/v1/chat/ask/"
REQUEST_TIMEOUT = 60


@dataclass
class Turn:
    message: str
    language: str = "en"
    expect_strains: bool = True
    description: str = ""


@dataclass
class TurnResult:
    turn_index: int
    message: str
    status_code: int
    strain_count: int
    session_id: Optional[str]
    elapsed: float
    response_snippet: str
    error: Optional[str] = None


@dataclass
class SessionResult:
    client_name: str
    turns: List[TurnResult] = field(default_factory=list)
    total_elapsed: float = 0.0
    success: bool = True
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# 3 realistic conversation scenarios
# ---------------------------------------------------------------------------

CLIENT_A_TURNS = [
    Turn(
        message="I have chronic insomnia and need something to help me sleep deeply",
        language="en",
        description="Medical: insomnia search",
    ),
    Turn(
        message="Which of these has the highest THC content?",
        language="en",
        description="Follow-up: sort by THC desc",
    ),
    Turn(
        message="Does it have any negative side effects I should worry about?",
        language="en",
        description="Follow-up: side effects detail",
    ),
    Turn(
        message="Show me something milder with fewer side effects",
        language="en",
        description="Follow-up: filter milder alternative",
    ),
]

CLIENT_B_TURNS = [
    Turn(
        message="Necesito algo para la ansiedad que no me deje muy sedado",
        language="es",
        description="Medical ES: anxiety without sedation",
    ),
    Turn(
        message="¿Cuál tiene más CBD de esos?",
        language="es",
        description="Follow-up ES: highest CBD",
    ),
    Turn(
        message="¿Hay alguna opción híbrida entre esas?",
        language="es",
        description="Follow-up ES: hybrid filter",
    ),
    Turn(
        message="Recomiéndame la mejor para usar durante el día",
        language="es",
        description="Follow-up ES: daytime use",
    ),
]

CLIENT_C_TURNS = [
    Turn(
        message="I want a creative sativa for music production, something energizing",
        language="en",
        description="Recreational: creativity + energy",
    ),
    Turn(
        message="Compare the top two options for me",
        language="en",
        description="Follow-up: comparison",
    ),
    Turn(
        message="Actually I also get mild anxiety, anything from the list that helps with that too?",
        language="en",
        description="Follow-up: add medical constraint",
    ),
]

SCENARIOS = {
    "Client-A (EN insomnia)": CLIENT_A_TURNS,
    "Client-B (ES anxiety)":  CLIENT_B_TURNS,
    "Client-C (EN creative)": CLIENT_C_TURNS,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_session(client_name: str, turns: List[Turn]) -> SessionResult:
    """Execute a full multi-turn conversation, reusing the session_id."""
    result = SessionResult(client_name=client_name)
    session_id = None
    session_start = time.time()

    for i, turn in enumerate(turns):
        payload = {
            "message": turn.message,
            "language": turn.language,
        }
        if session_id:
            payload["session_id"] = session_id

        t0 = time.time()
        try:
            resp = requests.post(CHAT_URL, json=payload, timeout=REQUEST_TIMEOUT)
            elapsed = time.time() - t0
            data = resp.json()

            turn_session_id = data.get("session_id")
            if turn_session_id:
                session_id = turn_session_id

            strains = data.get("recommended_strains", [])
            snippet = data.get("response", "")[:120]

            tr = TurnResult(
                turn_index=i,
                message=turn.message[:60],
                status_code=resp.status_code,
                strain_count=len(strains),
                session_id=session_id,
                elapsed=elapsed,
                response_snippet=snippet,
            )

            if resp.status_code != 200:
                tr.error = f"HTTP {resp.status_code}"
                result.success = False

        except Exception as exc:
            elapsed = time.time() - t0
            tr = TurnResult(
                turn_index=i,
                message=turn.message[:60],
                status_code=0,
                strain_count=0,
                session_id=session_id,
                elapsed=elapsed,
                response_snippet="",
                error=str(exc),
            )
            result.success = False

        result.turns.append(tr)

    result.total_elapsed = time.time() - session_start
    return result


# ---------------------------------------------------------------------------
# Pretty report
# ---------------------------------------------------------------------------

def print_report(results: List[SessionResult], wall_time: float):
    print("\n" + "=" * 90)
    print("  LOAD SIMULATION REPORT — 3 concurrent clients")
    print("=" * 90)

    all_turns = []
    for sr in results:
        print(f"\n{'─' * 90}")
        print(f"  {sr.client_name}  |  session total: {sr.total_elapsed:.1f}s  |  "
              f"{'OK' if sr.success else 'FAILED'}")
        print(f"{'─' * 90}")
        for tr in sr.turns:
            status = "✓" if tr.status_code == 200 else "✗"
            print(f"  {status} Turn {tr.turn_index + 1}  [{tr.elapsed:5.1f}s]  "
                  f"strains={tr.strain_count:<3}  {tr.message}")
            if tr.error:
                print(f"       ERROR: {tr.error}")
            all_turns.append(tr)

    # Summary
    total_requests = len(all_turns)
    ok_requests = sum(1 for t in all_turns if t.status_code == 200)
    total_api_time = sum(t.elapsed for t in all_turns)
    avg_latency = total_api_time / total_requests if total_requests else 0

    print(f"\n{'=' * 90}")
    print(f"  SUMMARY")
    print(f"{'=' * 90}")
    print(f"  Wall time (all clients parallel) : {wall_time:.1f}s")
    print(f"  Sum of all request times         : {total_api_time:.1f}s")
    print(f"  Concurrency gain                 : {total_api_time / wall_time:.1f}x" if wall_time else "")
    print(f"  Requests: {ok_requests}/{total_requests} succeeded")
    print(f"  Avg latency per request          : {avg_latency:.1f}s")
    print(f"  Sessions maintained correctly     : "
          f"{sum(1 for sr in results if all(t.session_id for t in sr.turns[1:]))}/{len(results)}")
    print(f"{'=' * 90}\n")


# ---------------------------------------------------------------------------
# Test entry point
# ---------------------------------------------------------------------------

def test_load_simulation():
    """Run 3 concurrent multi-turn client sessions against the API."""

    wall_start = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(run_session, name, turns): name
            for name, turns in SCENARIOS.items()
        }
        results = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result(timeout=300))

    wall_time = time.time() - wall_start

    # Sort by client name for stable output
    results.sort(key=lambda r: r.client_name)
    print_report(results, wall_time)

    # ── Assertions ──

    # 1. All requests succeeded
    for sr in results:
        for tr in sr.turns:
            assert tr.status_code == 200, (
                f"{sr.client_name} turn {tr.turn_index + 1} failed: "
                f"HTTP {tr.status_code} — {tr.error}"
            )

    # 2. First turn of each session must return strains
    for sr in results:
        first = sr.turns[0]
        assert first.strain_count > 0, (
            f"{sr.client_name} first turn returned 0 strains"
        )

    # 3. Session ID is reused across all follow-up turns
    for sr in results:
        first_sid = sr.turns[0].session_id
        assert first_sid, f"{sr.client_name} got no session_id on first turn"
        for tr in sr.turns[1:]:
            assert tr.session_id == first_sid, (
                f"{sr.client_name} turn {tr.turn_index + 1}: session_id changed "
                f"from {first_sid} to {tr.session_id}"
            )

    # 4. Concurrency: wall time should be less than sum of all session times
    #    (i.e. sessions overlapped)
    sum_session_times = sum(sr.total_elapsed for sr in results)
    assert wall_time < sum_session_times * 0.85, (
        f"Sessions appear sequential: wall={wall_time:.1f}s, "
        f"sum={sum_session_times:.1f}s"
    )
