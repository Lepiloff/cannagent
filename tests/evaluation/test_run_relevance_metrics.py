"""Unit tests for benchmark metric functions in run_relevance.py.

Validates precision@k, mrr@k, percentile, and the end-to-end MockHarness loop
without requiring DB / running API.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

# Make tests/evaluation/ importable as a sibling module path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_relevance import (  # noqa: E402
    MockHarness,
    percentile,
    precision_at_k,
    mrr_at_k,
    run_benchmark,
)


# ---------------------------------------------------------------------------
# precision_at_k
# ---------------------------------------------------------------------------

def test_precision_full_match():
    assert precision_at_k(["A", "B", "C"], ["A", "B", "C"], k=3) == 1.0


def test_precision_partial_match():
    # 2 of expected ["A", "B", "C"] in top-3 ["A", "X", "B"] → 2/3
    assert precision_at_k(["A", "X", "B"], ["A", "B", "C"], k=3) == pytest.approx(2 / 3)


def test_precision_no_match():
    assert precision_at_k(["X", "Y", "Z"], ["A", "B", "C"], k=3) == 0.0


def test_precision_case_insensitive():
    assert precision_at_k(["northern lights"], ["Northern Lights"], k=1) == 1.0


def test_precision_strips_whitespace():
    assert precision_at_k(["  A  "], ["A"], k=1) == 1.0


def test_precision_k_zero():
    assert precision_at_k(["A"], ["A"], k=0) == 0.0


def test_precision_empty_predicted():
    assert precision_at_k([], ["A"], k=3) == 0.0


def test_precision_empty_expected():
    assert precision_at_k(["A"], [], k=3) == 0.0


def test_precision_top_k_truncation():
    # Predicted has the right answer at position 4, but k=3 → not counted
    assert precision_at_k(["X", "Y", "Z", "A"], ["A"], k=3) == 0.0


def test_precision_normalizes_by_min_k_expected():
    # Expected has 2 items, predicted top-3 contains both → 2/2 = 1.0
    assert precision_at_k(["A", "B", "X"], ["A", "B"], k=3) == 1.0


# ---------------------------------------------------------------------------
# mrr_at_k
# ---------------------------------------------------------------------------

def test_mrr_first_position():
    assert mrr_at_k(["A", "B", "C"], ["A"], k=5) == 1.0


def test_mrr_third_position():
    assert mrr_at_k(["X", "Y", "A"], ["A"], k=5) == pytest.approx(1 / 3)


def test_mrr_no_hit_in_top_k():
    assert mrr_at_k(["X", "Y", "Z"], ["A"], k=5) == 0.0


def test_mrr_hit_beyond_k_returns_zero():
    assert mrr_at_k(["X", "Y", "Z", "A"], ["A"], k=3) == 0.0


def test_mrr_first_of_multiple_expected():
    # Expected has B and C; top-5 ["X","C","Y","B","Z"] → first hit at idx 2 (C) → 1/2
    assert mrr_at_k(["X", "C", "Y", "B", "Z"], ["B", "C"], k=5) == 0.5


def test_mrr_case_insensitive():
    assert mrr_at_k(["northern lights"], ["Northern Lights"], k=5) == 1.0


def test_mrr_k_zero_returns_zero():
    assert mrr_at_k(["A"], ["A"], k=0) == 0.0


# ---------------------------------------------------------------------------
# percentile
# ---------------------------------------------------------------------------

def test_percentile_empty_returns_zero():
    assert percentile([], 50) == 0.0


def test_percentile_single_value():
    assert percentile([42.0], 50) == 42.0


def test_percentile_p50_of_sorted():
    assert percentile([10, 20, 30, 40, 50], 50) == 30


def test_percentile_p95():
    # 100 values, p95 should be ≈ 95
    vals = list(range(1, 101))
    assert percentile(vals, 95) == pytest.approx(95.05, rel=0.01)


def test_percentile_handles_unsorted_input():
    assert percentile([50, 10, 30, 20, 40], 50) == 30


# ---------------------------------------------------------------------------
# End-to-end with MockHarness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_harness_runs_full_benchmark_loop():
    cases = [
        {
            "id": "case1",
            "query": "test query",
            "language": "en",
            "expected_top3_names": ["A", "B", "C"],
        },
        {
            "id": "case2",
            "query": "another query",
            "language": "es",
            "expected_top3_names": ["X", "Y", "Z"],
        },
    ]
    harness = MockHarness(cases)
    report = await run_benchmark(cases, harness, runs=2)

    assert report.provider == "mock"
    assert report.runs_per_case == 2
    assert len(report.cases) == 2
    # Mock returns expected names in order → precision@3 should be 1.0
    assert report.aggregate["precision_at_3_mean"] == pytest.approx(1.0)
    assert report.aggregate["mrr_at_5_mean"] == pytest.approx(1.0)
    assert report.aggregate["n_errors"] == 0


@pytest.mark.asyncio
async def test_run_benchmark_records_error_for_missing_expected():
    cases = [{"id": "bad", "query": "q", "language": "en"}]  # no expected_top3_names
    harness = MockHarness(cases)
    report = await run_benchmark(cases, harness, runs=1)
    assert report.aggregate["n_errors"] == 1
    assert "missing" in (report.cases[0].error or "").lower()


@pytest.mark.asyncio
async def test_per_language_breakdown_in_aggregate():
    cases = [
        {"id": "en1", "query": "q1", "language": "en", "expected_top3_names": ["A"]},
        {"id": "en2", "query": "q2", "language": "en", "expected_top3_names": ["B"]},
        {"id": "es1", "query": "q3", "language": "es", "expected_top3_names": ["C"]},
    ]
    harness = MockHarness(cases)
    report = await run_benchmark(cases, harness, runs=1)
    # MockHarness returns expected names exactly for each query → all 1.0
    assert report.aggregate["precision_at_3_en"] == pytest.approx(1.0)
    assert report.aggregate["precision_at_3_es"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Relevance set file structure
# ---------------------------------------------------------------------------

def test_relevance_set_file_is_valid_json():
    path = Path(__file__).parent / "relevance_set.json"
    with open(path) as f:
        data = json.load(f)
    assert "cases" in data
    assert isinstance(data["cases"], list)
    assert len(data["cases"]) >= 1
    for case in data["cases"]:
        assert "id" in case
        assert "query" in case
        assert "language" in case
        assert "expected_top3_names" in case
        assert case["language"] in ("en", "es")


# ---------------------------------------------------------------------------
# load_cases — filtering and TODO skipping
# ---------------------------------------------------------------------------

def test_load_cases_filters_by_ids(tmp_path):
    data = {
        "cases": [
            {"id": "a", "query": "q1", "language": "en", "expected_top3_names": ["X"]},
            {"id": "b", "query": "q2", "language": "en", "expected_top3_names": ["Y"]},
            {"id": "c", "query": "q3", "language": "es", "expected_top3_names": ["Z"]},
        ]
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data))

    from run_relevance import load_cases

    filtered = load_cases(str(path), "a,c", skip_todo=False)
    assert {c["id"] for c in filtered} == {"a", "c"}


def test_load_cases_skips_todo_placeholders(tmp_path):
    data = {
        "cases": [
            {"id": "real", "query": "q", "language": "en", "expected_top3_names": ["A", "B", "C"]},
            {"id": "todo", "query": "q", "language": "en", "expected_top3_names": ["TODO", "TODO", "TODO"]},
            {"id": "partial", "query": "q", "language": "en", "expected_top3_names": ["A", "TODO", "C"]},
        ]
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(data))

    from run_relevance import load_cases

    filtered = load_cases(str(path), None, skip_todo=True)
    assert {c["id"] for c in filtered} == {"real"}


# ---------------------------------------------------------------------------
# LiveHTTPHarness — uses a mocked `requests.post` so no server is required
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_live_http_harness_extracts_strain_names(monkeypatch):
    from run_relevance import LiveHTTPHarness
    import requests

    class _StubResponse:
        def __init__(self, body, status=200):
            self._body = body
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"status {self.status_code}")

        def json(self):
            return self._body

    captured = {}

    def stub_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return _StubResponse(
            body={
                "recommended_strains": [
                    {"name": "Northern Lights"},
                    {"name": "Blue Dream"},
                    {"name": "OG Kush"},
                    {"name": "Skywalker"},
                    {"name": "Pineapple Express"},
                ]
            }
        )

    monkeypatch.setattr(requests, "post", stub_post)

    harness = LiveHTTPHarness(provider_name="noop", base_url="http://api:8001")
    names = await harness.rank("indica with citrus", "en", top_k=3)

    assert names == ["Northern Lights", "Blue Dream", "OG Kush"]
    assert captured["url"] == "http://api:8001/api/v1/chat/ask/"
    assert captured["payload"] == {"message": "indica with citrus", "language": "en"}


@pytest.mark.asyncio
async def test_live_http_harness_handles_missing_recommended_strains(monkeypatch):
    from run_relevance import LiveHTTPHarness
    import requests

    class _StubResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {}  # no recommended_strains field

    monkeypatch.setattr(
        requests, "post", lambda *a, **kw: _StubResponse()
    )

    harness = LiveHTTPHarness(provider_name="groq")
    names = await harness.rank("q", "en", top_k=5)
    assert names == []


@pytest.mark.asyncio
async def test_live_http_harness_propagates_http_errors_into_run_case(monkeypatch):
    """Per-case HTTP errors are caught by run_case and recorded as case errors,
    not propagated up to crash the whole benchmark."""
    from run_relevance import LiveHTTPHarness, run_case
    import requests

    def boom(*a, **kw):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(requests, "post", boom)

    harness = LiveHTTPHarness(provider_name="cohere")
    case = {
        "id": "x",
        "query": "q",
        "language": "en",
        "expected_top3_names": ["A", "B", "C"],
    }
    result = await run_case(harness, case, runs=1)
    assert result.error is not None
    assert "RequestException" in result.error or "connection refused" in result.error.lower()
