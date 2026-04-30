#!/usr/bin/env python3
"""
Relevance benchmark runner.

Compares the system's top-3 strain recommendations against a labeled relevance
set (`relevance_set.json`). Used to measure regressions / improvements after
pipeline changes — for example, before-vs-after when adding new analyzer
features such as `excluded_feelings` / `excluded_flavors`.

Usage:
    # Verify metrics + report shape with synthetic data, no API needed.
    python tests/evaluation/run_relevance.py --label dry-run --mock --runs 1

    # Capture current system as ground truth (writes back into relevance_set.json).
    python tests/evaluation/run_relevance.py --generate-ground-truth \
        --base-url http://localhost:8001 --per-request-delay 5

    # Real benchmark against running API.
    python tests/evaluation/run_relevance.py --label baseline --runs 1 \
        --base-url http://localhost:8001 --per-request-delay 5 \
        --output tests/evaluation/baseline.json

Inputs:
    tests/evaluation/relevance_set.json — list of cases with `expected_top3_names`.

Outputs:
    JSON report with precision@3, MRR@5, latency p50/p95, and per-case detail.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def precision_at_k(predicted: List[str], expected: List[str], k: int) -> float:
    """Fraction of `expected` items present in the first `k` of `predicted`.

    Range [0, 1]. Returns 0 when either list is empty or k <= 0.
    Comparison is case-insensitive on stripped names.
    """
    if not predicted or not expected or k <= 0:
        return 0.0
    pred_norm = {p.strip().lower() for p in predicted[:k] if p}
    exp_norm = {e.strip().lower() for e in expected if e}
    if not exp_norm:
        return 0.0
    hits = len(pred_norm & exp_norm)
    return hits / min(k, len(exp_norm))


def mrr_at_k(predicted: List[str], expected: List[str], k: int) -> float:
    """Reciprocal rank of the first `expected` hit in `predicted[:k]`.

    Returns 0 when no expected item is found within the top k.
    Range [0, 1].
    """
    if not predicted or not expected or k <= 0:
        return 0.0
    exp_norm = {e.strip().lower() for e in expected if e}
    for idx, name in enumerate(predicted[:k], start=1):
        if name and name.strip().lower() in exp_norm:
            return 1.0 / idx
    return 0.0


def percentile(values: List[float], pct: float) -> float:
    """Return the `pct` percentile (0-100) of `values`. Empty list → 0.0."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


# ---------------------------------------------------------------------------
# Harness protocol — pluggable backend for candidate fetching + reranking
# ---------------------------------------------------------------------------

class RankingHarness(Protocol):
    """Returns ordered top-N strain names for a (query, language).

    The harness is responsible for:
      1. Fetching ~20 candidates from vector search
      2. Applying the configured reranker
      3. Returning the names, in rank order, of the top items
    Latency measurement is owned by the runner, not the harness.
    """

    provider_name: str

    async def rank(self, query: str, language: str, top_k: int) -> List[str]: ...


class MockHarness:
    """Phase 0 stub — returns expected_top3 in shuffled order for control-flow validation.

    Allows running the benchmark end-to-end without DB to verify metric math, JSON
    serialization, CLI arguments, and report shape.
    """

    provider_name = "mock"

    def __init__(self, cases: List[Dict[str, Any]]):
        self._by_query = {c["query"]: c.get("expected_top3_names", []) for c in cases}

    async def rank(self, query: str, language: str, top_k: int) -> List[str]:
        await asyncio.sleep(0)  # yield to loop, mimics async I/O
        names = list(self._by_query.get(query, []))
        # Pad with placeholders so the shape is realistic.
        while len(names) < top_k:
            names.append(f"_filler_{len(names)}")
        return names[:top_k]


class LiveHTTPHarness:
    """Hits the running API at `base_url/api/v1/chat/ask/` and returns the names
    of `recommended_strains` from the response.

    Production-realistic harness — exercises the full pipeline (analyzer, SQL
    filter, attribute filter, vector search, response generation). To compare
    a `before` vs `after` configuration, run the harness against each system
    state and diff the JSON reports.
    """

    def __init__(
        self,
        provider_name: str,
        base_url: str = "http://localhost:8001",
        timeout_s: int = 30,
        per_request_delay_s: float = 4.0,
        max_retries_on_429: int = 3,
    ):
        # Lazy import so unit tests don't pull in `requests` if not installed.
        import requests  # noqa: F401 — module-level import deferred for test isolation

        self.provider_name = provider_name
        self._endpoint = f"{base_url.rstrip('/')}/api/v1/chat/ask/"
        self._timeout = timeout_s
        self._per_request_delay = max(per_request_delay_s, 0.0)
        self._max_retries = max(max_retries_on_429, 0)

    async def rank(self, query: str, language: str, top_k: int) -> List[str]:
        # NOTE: pacing (per_request_delay) is applied OUTSIDE this method by the
        # runner (see run_case) so the sleep does not count toward `latency_ms`.
        return await asyncio.to_thread(self._post_and_extract, query, language, top_k)

    @property
    def per_request_delay(self) -> float:
        return self._per_request_delay

    def _post_and_extract(self, query: str, language: str, top_k: int) -> List[str]:
        import requests

        payload = {"message": query, "language": language}
        backoff_s = 5.0
        for attempt in range(self._max_retries + 1):
            resp = requests.post(self._endpoint, json=payload, timeout=self._timeout)
            if resp.status_code == 429 and attempt < self._max_retries:
                # Rate limited — back off and retry.
                time.sleep(backoff_s)
                backoff_s *= 2
                continue
            resp.raise_for_status()
            break
        body = resp.json()
        strains = body.get("recommended_strains") or []
        names = [s.get("name") for s in strains if isinstance(s, dict) and s.get("name")]
        return names[:top_k]


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class CaseRunResult:
    case_id: str
    query: str
    language: str
    expected_top3_names: List[str]
    predicted_top5_names: List[str] = field(default_factory=list)
    precision_at_3: float = 0.0
    mrr_at_5: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class ProviderReport:
    provider: str
    runs_per_case: int
    cases: List[CaseRunResult] = field(default_factory=list)
    aggregate: Dict[str, Any] = field(default_factory=dict)

    def compute_aggregate(self) -> None:
        precs = [c.precision_at_3 for c in self.cases if c.error is None]
        mrrs = [c.mrr_at_5 for c in self.cases if c.error is None]
        latencies = [c.latency_ms for c in self.cases if c.error is None]
        en_precs = [
            c.precision_at_3
            for c in self.cases
            if c.error is None and c.language == "en"
        ]
        es_precs = [
            c.precision_at_3
            for c in self.cases
            if c.error is None and c.language == "es"
        ]
        self.aggregate = {
            "n_cases": len(self.cases),
            "n_errors": sum(1 for c in self.cases if c.error is not None),
            "precision_at_3_mean": statistics.fmean(precs) if precs else 0.0,
            "precision_at_3_en": statistics.fmean(en_precs) if en_precs else 0.0,
            "precision_at_3_es": statistics.fmean(es_precs) if es_precs else 0.0,
            "mrr_at_5_mean": statistics.fmean(mrrs) if mrrs else 0.0,
            "latency_ms_p50": percentile(latencies, 50),
            "latency_ms_p95": percentile(latencies, 95),
        }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_case(
    harness: RankingHarness,
    case: Dict[str, Any],
    runs: int,
) -> CaseRunResult:
    """Execute a single case `runs` times. Latency = median across runs."""
    case_id = case["id"]
    query = case["query"]
    language = case.get("language", "en")
    expected = case.get("expected_top3_names", [])
    if not expected:
        return CaseRunResult(
            case_id=case_id,
            query=query,
            language=language,
            expected_top3_names=expected,
            error="expected_top3_names missing — cannot score",
        )

    latencies: List[float] = []
    last_predicted: List[str] = []
    last_error: Optional[str] = None
    # Pull throttle from harness if it exposes per_request_delay; otherwise no pacing.
    pre_sleep_s = float(getattr(harness, "per_request_delay", 0.0) or 0.0)

    for run_idx in range(runs):
        try:
            # Pacing: sleep BEFORE starting the timer so it doesn't pollute latency.
            if pre_sleep_s > 0:
                await asyncio.sleep(pre_sleep_s)
            t0 = time.perf_counter()
            predicted = await harness.rank(query, language, top_k=5)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            last_predicted = predicted
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            break

    if last_error is not None:
        return CaseRunResult(
            case_id=case_id,
            query=query,
            language=language,
            expected_top3_names=expected,
            error=last_error,
        )

    median_latency = statistics.median(latencies) if latencies else 0.0
    return CaseRunResult(
        case_id=case_id,
        query=query,
        language=language,
        expected_top3_names=expected,
        predicted_top5_names=last_predicted,
        precision_at_3=precision_at_k(last_predicted, expected, k=3),
        mrr_at_5=mrr_at_k(last_predicted, expected, k=5),
        latency_ms=median_latency,
    )


async def run_benchmark(
    cases: List[Dict[str, Any]],
    harness: RankingHarness,
    runs: int,
) -> ProviderReport:
    report = ProviderReport(provider=harness.provider_name, runs_per_case=runs)
    for case in cases:
        result = await run_case(harness, case, runs=runs)
        report.cases.append(result)
    report.compute_aggregate()
    return report


# ---------------------------------------------------------------------------
# Harness construction (Phase 0: only mock; Phase 4: live harness)
# ---------------------------------------------------------------------------

def build_harness(
    label: str,
    mock: bool,
    cases: List[Dict[str, Any]],
    base_url: str,
    timeout_s: int,
    per_request_delay_s: float = 4.0,
) -> RankingHarness:
    if mock:
        return MockHarness(cases)
    return LiveHTTPHarness(
        provider_name=label,
        base_url=base_url,
        timeout_s=timeout_s,
        per_request_delay_s=per_request_delay_s,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reranker relevance benchmark")
    parser.add_argument(
        "--label",
        default="baseline",
        help="Free-form label for the report (e.g., 'baseline', 'with-excluded-feelings')",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per case; latency = median across runs",
    )
    parser.add_argument(
        "--input",
        default=str(Path(__file__).parent / "relevance_set.json"),
        help="Path to relevance set JSON",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write JSON report here (default: stdout only)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockHarness (Phase 0 control-flow validation, no DB)",
    )
    parser.add_argument(
        "--ids",
        default=None,
        help="Comma-separated case IDs to include (default: all)",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("EVAL_API_URL", "http://localhost:8001"),
        help="Base URL for the running API (live harness only)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-request HTTP timeout in seconds (live harness only)",
    )
    parser.add_argument(
        "--skip-todo",
        action="store_true",
        help="Skip cases whose expected_top3_names contains 'TODO' placeholders",
    )
    parser.add_argument(
        "--generate-ground-truth",
        action="store_true",
        help=(
            "Run each query against the API once and write top-3 strain names back "
            "into the relevance set as `expected_top3_names`. Use this when running "
            "with RERANKER_PROVIDER=noop to snapshot current-system answers as the "
            "reference baseline. WARNING: this overwrites the input file in place."
        ),
    )
    parser.add_argument(
        "--per-request-delay",
        type=float,
        default=4.0,
        help=(
            "Seconds to wait before each HTTP request, to stay under the chat "
            "endpoint rate limit (3 req / 10s). Default: 4."
        ),
    )
    return parser.parse_args()


def load_cases(
    path: str,
    ids_filter: Optional[str],
    skip_todo: bool = False,
) -> List[Dict[str, Any]]:
    with open(path) as f:
        data = json.load(f)
    cases = data.get("cases", [])
    if ids_filter:
        wanted = {i.strip() for i in ids_filter.split(",")}
        cases = [c for c in cases if c.get("id") in wanted]
    if skip_todo:
        cases = [
            c for c in cases
            if not any("TODO" in n for n in c.get("expected_top3_names", []))
        ]
    return cases


def render_summary(report: ProviderReport) -> str:
    a = report.aggregate
    return (
        f"\n=== Relevance benchmark — label={report.provider} ===\n"
        f"  cases: {a.get('n_cases', 0)} (errors: {a.get('n_errors', 0)})\n"
        f"  precision@3 mean: {a.get('precision_at_3_mean', 0):.3f}"
        f"  (en: {a.get('precision_at_3_en', 0):.3f},"
        f" es: {a.get('precision_at_3_es', 0):.3f})\n"
        f"  MRR@5: {a.get('mrr_at_5_mean', 0):.3f}\n"
        f"  latency ms — p50: {a.get('latency_ms_p50', 0):.1f},"
        f" p95: {a.get('latency_ms_p95', 0):.1f}\n"
    )


async def generate_ground_truth(
    input_path: str,
    base_url: str,
    timeout_s: int,
    ids_filter: Optional[str],
    per_request_delay_s: float = 4.0,
) -> int:
    """Hit the running API for each case and save its top-3 names as ground truth.

    Run this once against the current production system to snapshot a reference set,
    then run the benchmark normally before/after a pipeline change to measure
    divergence and quality regressions.
    """
    with open(input_path) as f:
        data = json.load(f)

    all_cases: List[Dict[str, Any]] = data.get("cases", [])
    if ids_filter:
        wanted = {i.strip() for i in ids_filter.split(",")}
        target_ids = wanted
    else:
        target_ids = {c["id"] for c in all_cases}

    harness = LiveHTTPHarness(
        provider_name="ground-truth-capture",
        base_url=base_url,
        timeout_s=timeout_s,
        per_request_delay_s=per_request_delay_s,
    )

    updated = 0
    skipped = 0
    failed = 0
    for case in all_cases:
        if case["id"] not in target_ids:
            skipped += 1
            continue
        try:
            top3 = await harness.rank(case["query"], case.get("language", "en"), top_k=3)
        except Exception as exc:
            print(f"  ✗ {case['id']}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failed += 1
            continue
        if not top3:
            print(f"  ✗ {case['id']}: API returned no recommended_strains", file=sys.stderr)
            failed += 1
            continue
        case["expected_top3_names"] = top3
        print(f"  ✓ {case['id']}: {top3}")
        updated += 1

    with open(input_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(
        f"\nGround truth generated: {updated} updated, "
        f"{failed} failed, {skipped} skipped. Saved to {input_path}."
    )
    return 0 if failed == 0 else 1


async def main_async() -> int:
    args = parse_args()

    if args.generate_ground_truth:
        return await generate_ground_truth(
            input_path=args.input,
            base_url=args.base_url,
            timeout_s=args.timeout,
            ids_filter=args.ids,
            per_request_delay_s=args.per_request_delay,
        )

    cases = load_cases(args.input, args.ids, skip_todo=args.skip_todo)
    if not cases:
        print(f"No cases loaded from {args.input}", file=sys.stderr)
        return 2

    harness = build_harness(
        args.label,
        mock=args.mock,
        cases=cases,
        base_url=args.base_url,
        timeout_s=args.timeout,
        per_request_delay_s=args.per_request_delay,
    )
    report = await run_benchmark(cases, harness, runs=args.runs)

    print(render_summary(report))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)
        print(f"Report written to {args.output}")

    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
