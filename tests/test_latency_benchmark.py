#!/usr/bin/env python3
"""
Latency Benchmark Tests for Prompt Caching & Streaming Optimizations

Measures:
1. Response latency per query (total round-trip)
2. Prompt caching effect (2nd+ requests should be faster)
3. Streaming endpoint (time-to-first-byte vs total)
4. Comparison across query types (search, non-search, follow-up, specific strain)

Usage:
    python tests/test_latency_benchmark.py
    python tests/test_latency_benchmark.py --runs 5    # 5 runs per query (default: 3)
    python tests/test_latency_benchmark.py --streaming  # also test /ask/stream
"""

import argparse
import json
import requests
import statistics
import sys
import time
from typing import Dict, List, Optional, Any, Tuple

# Simple color codes
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        CYAN = '\033[96m'
        MAGENTA = '\033[95m'
        WHITE = '\033[97m'
        RESET = '\033[0m'

    class Style:
        RESET_ALL = '\033[0m'
        BRIGHT = '\033[1m'

# Config
API_BASE_URL = "http://localhost:8001"
API_ENDPOINT = f"{API_BASE_URL}/api/v1/chat/ask/"
STREAM_ENDPOINT = f"{API_BASE_URL}/api/v1/chat/ask/stream"


def print_header(text: str):
    print(f"\n{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{text.center(80)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")


def send_query_timed(message: str, session_id: Optional[str] = None,
                     language: str = "en") -> Tuple[Dict[str, Any], float]:
    """Send query and return (response_data, latency_ms)."""
    payload = {"message": message, "language": language}
    if session_id:
        payload["session_id"] = session_id

    start = time.perf_counter()
    try:
        response = requests.post(API_ENDPOINT, json=payload, timeout=60)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        return response.json(), elapsed_ms
    except requests.exceptions.RequestException as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"error": str(e)}, elapsed_ms


def send_stream_timed(message: str, session_id: Optional[str] = None,
                      language: str = "en") -> Tuple[Dict[str, Any], float, float]:
    """Send streaming query. Returns (aggregated_data, time_to_first_chunk_ms, total_ms)."""
    payload = {"message": message, "language": language}
    if session_id:
        payload["session_id"] = session_id

    start = time.perf_counter()
    first_chunk_time = None
    chunks = []

    try:
        with requests.post(STREAM_ENDPOINT, json=payload, timeout=60, stream=True) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    if first_chunk_time is None:
                        first_chunk_time = (time.perf_counter() - start) * 1000
                    try:
                        chunk = json.loads(line[6:])
                        chunks.append(chunk)
                    except json.JSONDecodeError:
                        pass

        total_ms = (time.perf_counter() - start) * 1000
        if first_chunk_time is None:
            first_chunk_time = total_ms

        # Aggregate chunks into a response-like dict
        aggregated: Dict[str, Any] = {}
        response_text = ""
        for chunk in chunks:
            ctype = chunk.get("type")
            if ctype == "metadata":
                aggregated = chunk.get("data", {})
            elif ctype == "response_chunk":
                response_text += chunk.get("text", "")
            elif ctype == "error":
                aggregated["error"] = chunk.get("message", "Unknown streaming error")

        aggregated["response"] = response_text
        aggregated["_chunk_count"] = len(chunks)

        return aggregated, first_chunk_time, total_ms

    except requests.exceptions.RequestException as e:
        total_ms = (time.perf_counter() - start) * 1000
        return {"error": str(e)}, total_ms, total_ms


# ============================================================================
# BENCHMARK QUERIES
# ============================================================================

BENCHMARK_QUERIES = [
    # (name, message, language, query_type)
    ("EN: Search indica sleep", "suggest me indica strains for sleep", "en", "search"),
    ("EN: Search sativa energy", "show me sativa strains for energy and creativity", "en", "search"),
    ("EN: Search high THC", "find strains with high thc and tropical flavor", "en", "search"),
    ("EN: Medical query", "which strains help with pain and anxiety", "en", "search"),
    ("EN: Specific strain", "tell me about Northern Lights", "en", "specific"),
    ("EN: Non-search greeting", "hey, how can you help me", "en", "non-search"),
    ("EN: Non-search general", "what is cannabis", "en", "non-search"),
    ("ES: Search indica", "recomiendame indica para dormir", "es", "search"),
    ("ES: Search sativa", "dame sativa para creatividad", "es", "search"),
    ("ES: Non-search", "hola, que puedes hacer", "es", "non-search"),
]


def run_benchmark(runs: int = 3, test_streaming: bool = False):
    """Run the full latency benchmark."""

    print_header("LATENCY BENCHMARK")
    print(f"  Runs per query: {runs}")
    print(f"  Streaming test: {'Yes' if test_streaming else 'No'}")
    print(f"  Queries: {len(BENCHMARK_QUERIES)}")
    print()

    all_results: List[Dict[str, Any]] = []

    for name, message, language, qtype in BENCHMARK_QUERIES:
        latencies = []
        errors = 0

        for run_idx in range(runs):
            data, latency = send_query_timed(message, language=language)
            if "error" in data:
                errors += 1
                print(f"  {Fore.RED}[{name}] Run {run_idx+1}: ERROR - {data['error']}{Style.RESET_ALL}")
            else:
                latencies.append(latency)
                num_strains = len(data.get("recommended_strains", []))
                cache_note = ""
                # First run is a cache miss, subsequent should be hits
                if run_idx == 0:
                    cache_note = " (cache cold)"
                elif run_idx == 1:
                    cache_note = " (cache warm?)"

                print(f"  [{name}] Run {run_idx+1}: {latency:.0f}ms, strains={num_strains}{cache_note}")

        if not latencies:
            all_results.append({
                "name": name, "type": qtype, "language": language,
                "runs": runs, "errors": errors,
                "avg": 0, "median": 0, "min": 0, "max": 0, "p90": 0,
                "first": 0, "rest_avg": 0,
            })
            continue

        avg = statistics.mean(latencies)
        median = statistics.median(latencies)
        p90 = sorted(latencies)[int(len(latencies) * 0.9)] if len(latencies) > 1 else latencies[0]
        first_run = latencies[0]
        rest_avg = statistics.mean(latencies[1:]) if len(latencies) > 1 else 0

        all_results.append({
            "name": name, "type": qtype, "language": language,
            "runs": runs, "errors": errors,
            "avg": avg, "median": median,
            "min": min(latencies), "max": max(latencies),
            "p90": p90,
            "first": first_run, "rest_avg": rest_avg,
            "latencies": latencies,
        })

    # Print results table
    print_header("RESULTS: /ask/ ENDPOINT")
    print(f"  {'Query':<35} {'Avg':>8} {'Med':>8} {'Min':>8} {'Max':>8} {'1st':>8} {'2nd+':>8} {'Err':>4}")
    print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*4}")

    for r in all_results:
        color = Fore.GREEN if r["avg"] < 5000 else (Fore.YELLOW if r["avg"] < 7000 else Fore.RED)
        cache_improvement = ""
        if r["first"] > 0 and r["rest_avg"] > 0:
            pct = (1 - r["rest_avg"] / r["first"]) * 100
            if pct > 5:
                cache_improvement = f" ({pct:+.0f}%)"

        print(
            f"  {r['name']:<35} "
            f"{color}{r['avg']:>7.0f}ms{Style.RESET_ALL} "
            f"{r['median']:>7.0f}ms "
            f"{r['min']:>7.0f}ms "
            f"{r['max']:>7.0f}ms "
            f"{r['first']:>7.0f}ms "
            f"{r['rest_avg']:>7.0f}ms{cache_improvement} "
            f"{r['errors']:>3}"
        )

    # Summary by type
    print_header("SUMMARY BY QUERY TYPE")
    for qtype in ["search", "specific", "non-search"]:
        type_results = [r for r in all_results if r["type"] == qtype and r["avg"] > 0]
        if not type_results:
            continue
        avgs = [r["avg"] for r in type_results]
        firsts = [r["first"] for r in type_results]
        rests = [r["rest_avg"] for r in type_results if r["rest_avg"] > 0]

        avg_all = statistics.mean(avgs)
        avg_first = statistics.mean(firsts)
        avg_rest = statistics.mean(rests) if rests else 0

        color = Fore.GREEN if avg_all < 5000 else (Fore.YELLOW if avg_all < 7000 else Fore.RED)
        cache_note = ""
        if avg_first > 0 and avg_rest > 0:
            pct = (1 - avg_rest / avg_first) * 100
            cache_note = f" | Cache effect: {pct:+.1f}%"

        print(f"  {qtype.upper():<15} Avg: {color}{avg_all:.0f}ms{Style.RESET_ALL} | "
              f"1st: {avg_first:.0f}ms | 2nd+: {avg_rest:.0f}ms{cache_note}")

    # Overall
    all_avgs = [r["avg"] for r in all_results if r["avg"] > 0]
    if all_avgs:
        overall = statistics.mean(all_avgs)
        color = Fore.GREEN if overall < 5000 else (Fore.YELLOW if overall < 7000 else Fore.RED)
        print(f"\n  {'OVERALL':<15} Avg: {color}{overall:.0f}ms{Style.RESET_ALL}")

    # Streaming benchmark
    if test_streaming:
        run_streaming_benchmark(runs)


def run_streaming_benchmark(runs: int = 3):
    """Benchmark the streaming /ask/stream endpoint."""
    print_header("RESULTS: /ask/stream ENDPOINT (SSE)")

    stream_queries = [
        ("EN: Search indica", "suggest me indica for sleep", "en"),
        ("EN: Search sativa", "show me sativa for energy", "en"),
        ("ES: Search indica", "recomiendame indica para dormir", "es"),
    ]

    print(f"  {'Query':<35} {'TTFB':>8} {'Total':>8} {'Chunks':>7} {'Savings':>8}")
    print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*7} {'-'*8}")

    for name, message, language in stream_queries:
        ttfbs = []
        totals = []
        chunk_counts = []

        for run_idx in range(runs):
            data, ttfb, total = send_stream_timed(message, language=language)
            if "error" in data:
                print(f"  {Fore.RED}[{name}] Run {run_idx+1}: ERROR - {data['error']}{Style.RESET_ALL}")
                continue
            ttfbs.append(ttfb)
            totals.append(total)
            chunk_counts.append(data.get("_chunk_count", 0))

        if not ttfbs:
            continue

        avg_ttfb = statistics.mean(ttfbs)
        avg_total = statistics.mean(totals)
        avg_chunks = statistics.mean(chunk_counts)
        savings_pct = (1 - avg_ttfb / avg_total) * 100 if avg_total > 0 else 0

        color = Fore.GREEN if avg_ttfb < 4000 else (Fore.YELLOW if avg_ttfb < 6000 else Fore.RED)
        print(
            f"  {name:<35} "
            f"{color}{avg_ttfb:>7.0f}ms{Style.RESET_ALL} "
            f"{avg_total:>7.0f}ms "
            f"{avg_chunks:>6.0f} "
            f"{savings_pct:>7.0f}%"
        )

    print(f"\n  TTFB = Time To First Byte (perceived latency)")
    print(f"  Savings = how much faster user sees first content vs waiting for full response")


# ============================================================================
# FOLLOW-UP BENCHMARK (measures session-aware queries)
# ============================================================================

def run_followup_benchmark(runs: int = 2):
    """Benchmark follow-up query latency."""
    print_header("FOLLOW-UP QUERY BENCHMARK")

    for run_idx in range(runs):
        print(f"\n  --- Run {run_idx + 1} ---")

        # Step 1: Initial search
        data1, lat1 = send_query_timed("suggest me indica with high thc", language="en")
        session_id = data1.get("session_id")
        n1 = len(data1.get("recommended_strains", []))
        print(f"  Initial search: {lat1:.0f}ms (strains={n1})")

        if not session_id:
            print(f"  {Fore.RED}No session_id — skipping follow-ups{Style.RESET_ALL}")
            continue

        # Step 2: Follow-up (compare)
        data2, lat2 = send_query_timed("which one has the lowest thc",
                                        session_id=session_id, language="en")
        n2 = len(data2.get("recommended_strains", []))
        is_fu = data2.get("filters_applied", {}).get("is_follow_up", False)
        print(f"  Follow-up (compare): {lat2:.0f}ms (strains={n2}, is_follow_up={is_fu})")

        # Step 3: New search (context switch)
        data3, lat3 = send_query_timed("now show me sativa for creativity",
                                        session_id=session_id, language="en")
        n3 = len(data3.get("recommended_strains", []))
        print(f"  Context switch: {lat3:.0f}ms (strains={n3})")


def main():
    parser = argparse.ArgumentParser(description="Latency benchmark for canagent")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per query (default: 3)")
    parser.add_argument("--streaming", action="store_true", help="Also benchmark streaming endpoint")
    parser.add_argument("--followup", action="store_true", help="Also benchmark follow-up queries")
    args = parser.parse_args()

    print(f"\n{Fore.MAGENTA}{'*' * 80}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'CANAGENT LATENCY BENCHMARK'.center(80)}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'*' * 80}{Style.RESET_ALL}")

    # Check API availability
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        print(f"{Fore.GREEN}API is reachable at {API_BASE_URL}{Style.RESET_ALL}")
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}Cannot reach API at {API_BASE_URL}{Style.RESET_ALL}")
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Make sure the API is running: docker compose up -d{Style.RESET_ALL}")
        sys.exit(1)

    try:
        run_benchmark(runs=args.runs, test_streaming=args.streaming)
        if args.followup:
            run_followup_benchmark(runs=min(args.runs, 2))
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Benchmark interrupted{Style.RESET_ALL}")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
