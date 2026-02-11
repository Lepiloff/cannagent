"""
Async Concurrency Integration Tests

Verifies that the async architecture works correctly:
- Event loop is not blocked during request processing
- Concurrent requests with different sessions run in parallel
- Same-session requests are serialized via distributed lock
- Session data integrity is preserved under concurrency

Requires a running API server (docker compose up).

Usage:
    docker compose exec api pytest tests/test_async_concurrency.py -v
"""

import concurrent.futures
import time

import requests

API_BASE = "http://localhost:8000"
CHAT_URL = f"{API_BASE}/api/v1/chat/ask/"
HEALTH_URL = f"{API_BASE}/api/v1/ping/"


def _chat(message, session_id=None, timeout=30):
    """Send a chat request and return (status, json, elapsed_seconds)."""
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id
    start = time.time()
    r = requests.post(CHAT_URL, json=payload, timeout=timeout)
    elapsed = time.time() - start
    return r.status_code, r.json(), elapsed


# ------------------------------------------------------------------
# 1. Event loop is NOT blocked
# ------------------------------------------------------------------

def test_event_loop_not_blocked():
    """Health endpoint responds quickly while a slow chat request is in progress."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        # Launch a heavy chat request in background
        chat_future = pool.submit(_chat, "recommend indica strains for deep sleep")

        # Give the chat request a moment to start processing
        time.sleep(0.5)

        # Health ping should respond quickly (< 2s) even while chat is running
        start = time.time()
        health = requests.get(HEALTH_URL, timeout=5)
        health_elapsed = time.time() - start

        assert health.status_code == 200, f"Health returned {health.status_code}"
        assert health_elapsed < 2.0, (
            f"Health took {health_elapsed:.1f}s — event loop is likely blocked"
        )

        # Wait for chat to finish (don't leave dangling)
        chat_status, _, _ = chat_future.result(timeout=60)
        assert chat_status == 200


# ------------------------------------------------------------------
# 2. Concurrent requests with DIFFERENT sessions run in parallel
# ------------------------------------------------------------------

def test_concurrent_different_sessions():
    """Three parallel requests (new sessions) all succeed and overlap in time."""
    messages = [
        "recommend sativa for energy",
        "indica for pain relief",
        "hybrid for creativity",
    ]

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(_chat, msg) for msg in messages]
        results = [f.result(timeout=60) for f in futures]
    total_elapsed = time.time() - start

    individual_sum = sum(r[2] for r in results)

    for i, (status, data, elapsed) in enumerate(results):
        assert status == 200, f"Request {i} returned {status}"
        strains = data.get("recommended_strains", [])
        assert len(strains) > 0, f"Request {i} returned 0 strains"

    # If requests ran in parallel, total time should be significantly less
    # than the sum of individual times.
    assert total_elapsed < individual_sum * 0.85, (
        f"Requests appear sequential: total={total_elapsed:.1f}s, "
        f"sum={individual_sum:.1f}s"
    )


# ------------------------------------------------------------------
# 3. Same-session requests are SERIALIZED by distributed lock
# ------------------------------------------------------------------

def test_concurrent_same_session_lock():
    """Two parallel requests with the same session_id are serialized by lock."""
    # Step 1: create a session
    status, data, _ = _chat("recommend indica for sleep")
    assert status == 200
    session_id = data.get("session_id")
    assert session_id, "No session_id in first response"

    # Step 2: fire two concurrent follow-ups with the same session
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_chat, "show the strongest one", session_id)
        f2 = pool.submit(_chat, "show the mildest one", session_id)

        s1, d1, t1 = f1.result(timeout=60)
        s2, d2, t2 = f2.result(timeout=60)

    assert s1 == 200, f"Request 1 returned {s1}"
    assert s2 == 200, f"Request 2 returned {s2}"

    # Lock serialization: one request had to wait for the other,
    # so the times should differ by at least 1 second.
    delta = abs(t1 - t2)
    assert delta > 1.0, (
        f"Requests finished too close together (delta={delta:.1f}s) — "
        f"lock may not be working"
    )


# ------------------------------------------------------------------
# 4. Session data integrity across sequential requests
# ------------------------------------------------------------------

def test_session_data_integrity():
    """Session context is preserved across multiple sequential requests."""
    # Request 1: new search
    s1, d1, _ = _chat("recommend indica for sleep")
    assert s1 == 200
    session_id = d1.get("session_id")
    assert session_id
    strains_1 = d1.get("recommended_strains", [])
    assert len(strains_1) > 0, "First request returned 0 strains"

    # Request 2: follow-up using same session
    s2, d2, _ = _chat("show the strongest one", session_id)
    assert s2 == 200
    assert d2.get("session_id") == session_id, "Session ID changed unexpectedly"

    # Request 3: another follow-up
    s3, d3, _ = _chat("any with less side effects?", session_id)
    assert s3 == 200
    assert d3.get("session_id") == session_id, "Session ID changed unexpectedly"
