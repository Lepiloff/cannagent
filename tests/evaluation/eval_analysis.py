#!/usr/bin/env python3
"""
Evaluation Pipeline for QueryAnalysis accuracy.

Measures LLM analysis quality by comparing API responses against expected results.
Supports field-level accuracy, result quality metrics, and latency tracking.

Usage:
    # Run full evaluation against running API
    python tests/evaluation/eval_analysis.py

    # Filter by tags
    python tests/evaluation/eval_analysis.py --tags search,en

    # Only run specific test cases
    python tests/evaluation/eval_analysis.py --ids search_indica_simple,greeting_en

    # Multiple runs for latency stats
    python tests/evaluation/eval_analysis.py --runs 3

    # Save report to file
    python tests/evaluation/eval_analysis.py --output eval_report.json
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("EVAL_API_URL", "http://localhost:8001")
API_ENDPOINT = f"{API_BASE_URL}/api/v1/chat/ask/"
TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"
REQUEST_TIMEOUT = 30

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FieldResult:
    field: str
    expected: Any
    actual: Any
    passed: bool


@dataclass
class CaseResult:
    case_id: str
    query: str
    language: str
    tags: List[str]
    passed: bool
    field_results: List[FieldResult] = field(default_factory=list)
    strain_check_passed: Optional[bool] = None
    trait_check_passed: Optional[bool] = None
    filter_check_passed: Optional[bool] = None
    latency_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class EvalReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    field_accuracy: Dict[str, Dict[str, int]] = field(default_factory=dict)
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_avg: float = 0.0
    case_results: List[CaseResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# API interaction
# ---------------------------------------------------------------------------

def send_query(message: str, language: str, session_id: Optional[str] = None) -> Dict:
    payload = {"message": message, "language": language}
    if session_id:
        payload["session_id"] = session_id
    try:
        resp = requests.post(API_ENDPOINT, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------

def check_field(expected_val: Any, actual_val: Any) -> bool:
    """Compare expected vs actual field value with normalization."""
    if expected_val is None:
        return True  # no expectation
    if actual_val is None:
        return False

    # String comparison: case-insensitive
    if isinstance(expected_val, str) and isinstance(actual_val, str):
        return expected_val.lower() == actual_val.lower()

    return expected_val == actual_val


def check_strain_count(expected, actual_count: int) -> bool:
    if expected is None:
        return True
    if expected == ">0":
        return actual_count > 0
    if isinstance(expected, int):
        return actual_count == expected
    return True


def check_result_traits(expected_traits: Dict, strains: List[Dict]) -> bool:
    """Check if at least one returned strain has the expected traits."""
    if not expected_traits or not strains:
        return not expected_traits  # pass if no expectations

    for trait_type, expected_values in expected_traits.items():
        # trait_type is "feelings", "helps_with", etc.
        found_any = False
        for strain in strains:
            strain_values = [
                item["name"].lower()
                for item in strain.get(trait_type, [])
            ]
            if any(ev.lower() in strain_values for ev in expected_values):
                found_any = True
                break
        if not found_any:
            return False
    return True


def check_filters(expected_filters: Dict, actual_filters: Dict) -> bool:
    """Check if filters_applied contains expected filter values."""
    if not expected_filters:
        return True
    for key, expected_val in expected_filters.items():
        actual_val = actual_filters.get(key)
        if not check_field(expected_val, actual_val):
            return False
    return True


def evaluate_case(case: Dict) -> CaseResult:
    """Evaluate a single test case against the API."""
    case_id = case["id"]
    query = case["query"]
    language = case.get("language", "en")
    expected = case.get("expected", {})
    tags = case.get("tags", [])

    start = time.time()
    response = send_query(query, language)
    latency_ms = (time.time() - start) * 1000

    if "error" in response:
        return CaseResult(
            case_id=case_id, query=query, language=language, tags=tags,
            passed=False, latency_ms=latency_ms,
            error=response["error"]
        )

    filters = response.get("filters_applied", {})
    strains = response.get("recommended_strains", [])
    resp_language = response.get("language", "")

    field_results = []

    # --- Check expected analysis fields ---

    # is_search_query
    if "is_search_query" in expected:
        actual = filters.get("is_search_query")
        # For non-search queries, filters_applied may not have is_search_query
        # In that case, check if strains count matches expectation
        if actual is None:
            actual = len(strains) > 0
        fr = FieldResult("is_search_query", expected["is_search_query"], actual,
                         check_field(expected["is_search_query"], actual))
        field_results.append(fr)

    # is_follow_up
    if "is_follow_up" in expected:
        actual = filters.get("is_follow_up", False)
        fr = FieldResult("is_follow_up", expected["is_follow_up"], actual,
                         check_field(expected["is_follow_up"], actual))
        field_results.append(fr)

    # detected_category
    if "detected_category" in expected:
        actual = filters.get("category")
        fr = FieldResult("detected_category", expected["detected_category"], actual,
                         check_field(expected["detected_category"], actual))
        field_results.append(fr)

    # thc_level
    if "thc_level" in expected:
        # Map thc_level to expected min_thc in filters
        thc_map = {"low": ("max_thc", 10), "medium": ("min_thc", 10), "high": ("min_thc", 20)}
        level = expected["thc_level"]
        if level in thc_map:
            filter_key, filter_val = thc_map[level]
            actual = filters.get(filter_key)
            fr = FieldResult("thc_level", f"{filter_key}={filter_val}", f"{filter_key}={actual}",
                             actual == filter_val)
            field_results.append(fr)

    # cbd_level
    if "cbd_level" in expected:
        cbd_map = {"low": ("max_cbd", 3), "medium": ("min_cbd", 3), "high": ("min_cbd", 7)}
        level = expected["cbd_level"]
        if level in cbd_map:
            filter_key, filter_val = cbd_map[level]
            actual = filters.get(filter_key)
            fr = FieldResult("cbd_level", f"{filter_key}={filter_val}", f"{filter_key}={actual}",
                             actual == filter_val)
            field_results.append(fr)

    # detected_language
    if "detected_language" in expected:
        actual = resp_language.lower() if resp_language else None
        fr = FieldResult("detected_language", expected["detected_language"], actual,
                         check_field(expected["detected_language"], actual))
        field_results.append(fr)

    # specific_strain_name
    if "specific_strain_name" in expected:
        expected_name = expected["specific_strain_name"]
        # Check if the expected strain is in results
        found = any(
            s.get("name", "").lower() == expected_name.lower()
            for s in strains
        )
        fr = FieldResult("specific_strain_name", expected_name,
                         strains[0]["name"] if strains else None, found)
        field_results.append(fr)

    # --- Check strain count ---
    expected_strains = case.get("expected_strains")
    strain_check = check_strain_count(expected_strains, len(strains))

    # --- Check result traits (strain quality) ---
    expected_traits = case.get("expected_result_traits")
    trait_check = check_result_traits(expected_traits, strains) if expected_traits else None

    # --- Check expected_filters ---
    expected_filt = case.get("expected_filters")
    filter_check = check_filters(expected_filt, filters) if expected_filt else None

    # Overall pass: all field checks + strain count + traits + filters
    all_fields_pass = all(fr.passed for fr in field_results)
    overall = all_fields_pass and strain_check
    if trait_check is not None:
        overall = overall and trait_check
    if filter_check is not None:
        overall = overall and filter_check

    return CaseResult(
        case_id=case_id, query=query, language=language, tags=tags,
        passed=overall, field_results=field_results,
        strain_check_passed=strain_check,
        trait_check_passed=trait_check,
        filter_check_passed=filter_check,
        latency_ms=latency_ms
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_report(results: List[CaseResult]) -> EvalReport:
    report = EvalReport()
    report.total = len(results)
    report.case_results = results

    latencies = []

    for cr in results:
        if cr.error:
            report.errors += 1
        elif cr.passed:
            report.passed += 1
        else:
            report.failed += 1
        latencies.append(cr.latency_ms)

        # Field-level accuracy tracking
        for fr in cr.field_results:
            if fr.field not in report.field_accuracy:
                report.field_accuracy[fr.field] = {"correct": 0, "total": 0}
            report.field_accuracy[fr.field]["total"] += 1
            if fr.passed:
                report.field_accuracy[fr.field]["correct"] += 1

    if latencies:
        latencies.sort()
        report.latency_avg = sum(latencies) / len(latencies)
        report.latency_p50 = latencies[len(latencies) // 2]
        idx_95 = min(int(len(latencies) * 0.95), len(latencies) - 1)
        report.latency_p95 = latencies[idx_95]

    return report


def print_report(report: EvalReport):
    print(f"\n{CYAN}{'=' * 80}{RESET}")
    print(f"{CYAN}{'EVALUATION REPORT'.center(80)}{RESET}")
    print(f"{CYAN}{'=' * 80}{RESET}\n")

    # Per-case results
    for cr in report.case_results:
        if cr.error:
            status = f"{RED}ERR{RESET}"
        elif cr.passed:
            status = f"{GREEN}OK {RESET}"
        else:
            status = f"{RED}FAIL{RESET}"

        latency_str = f"{DIM}{cr.latency_ms:7.0f}ms{RESET}"
        print(f"  {status} {latency_str}  {cr.case_id:<35} {DIM}{cr.query[:45]}{RESET}")

        if not cr.passed and not cr.error:
            for fr in cr.field_results:
                if not fr.passed:
                    print(f"         {RED}{fr.field}: expected={fr.expected}, got={fr.actual}{RESET}")
            if cr.strain_check_passed is False:
                print(f"         {RED}strain count check failed{RESET}")
            if cr.trait_check_passed is False:
                print(f"         {RED}result trait check failed{RESET}")
            if cr.filter_check_passed is False:
                print(f"         {RED}filter check failed{RESET}")
        if cr.error:
            print(f"         {RED}{cr.error}{RESET}")

    # Summary
    print(f"\n{CYAN}{'─' * 80}{RESET}")
    total = report.total
    pass_rate = (report.passed / total * 100) if total else 0
    print(f"\n  {BOLD}Results:{RESET}  {report.passed}/{total} passed ({pass_rate:.1f}%)"
          f"  |  {report.failed} failed  |  {report.errors} errors")

    # Field accuracy
    if report.field_accuracy:
        print(f"\n  {BOLD}Field Accuracy:{RESET}")
        for fname, stats in sorted(report.field_accuracy.items()):
            acc = stats["correct"] / stats["total"] * 100 if stats["total"] else 0
            color = GREEN if acc >= 90 else YELLOW if acc >= 70 else RED
            print(f"    {fname:<25} {color}{stats['correct']}/{stats['total']} ({acc:.0f}%){RESET}")

    # Latency
    print(f"\n  {BOLD}Latency:{RESET}")
    print(f"    avg={report.latency_avg:.0f}ms  p50={report.latency_p50:.0f}ms  p95={report.latency_p95:.0f}ms")
    print()


def save_report(report: EvalReport, output_path: str):
    data = {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "errors": report.errors,
        "pass_rate": round(report.passed / report.total * 100, 1) if report.total else 0,
        "field_accuracy": {
            fname: {
                **stats,
                "accuracy": round(stats["correct"] / stats["total"] * 100, 1) if stats["total"] else 0
            }
            for fname, stats in report.field_accuracy.items()
        },
        "latency": {
            "avg_ms": round(report.latency_avg, 1),
            "p50_ms": round(report.latency_p50, 1),
            "p95_ms": round(report.latency_p95, 1),
        },
        "cases": [
            {
                "id": cr.case_id,
                "passed": cr.passed,
                "latency_ms": round(cr.latency_ms, 1),
                "error": cr.error,
                "field_results": [
                    {"field": fr.field, "expected": fr.expected,
                     "actual": fr.actual, "passed": fr.passed}
                    for fr in cr.field_results
                ] if not cr.error else []
            }
            for cr in report.case_results
        ]
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Report saved to {output_path}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluation pipeline for QueryAnalysis")
    parser.add_argument("--tags", help="Comma-separated tags to filter test cases")
    parser.add_argument("--ids", help="Comma-separated case IDs to run")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per case (for latency stats)")
    parser.add_argument("--output", help="Save JSON report to file")
    parser.add_argument("--api-url", default=API_BASE_URL, help="API base URL")
    args = parser.parse_args()

    api_base = args.api_url
    # Update module-level endpoint used by send_query
    global API_ENDPOINT
    API_ENDPOINT = f"{api_base}/api/v1/chat/ask/"

    # Check API
    try:
        requests.get(f"{api_base}/", timeout=5)
        print(f"{GREEN}API reachable at {api_base}{RESET}")
    except requests.exceptions.RequestException:
        print(f"{RED}Cannot reach API at {api_base}{RESET}")
        sys.exit(1)

    # Load test cases
    with open(TEST_CASES_PATH) as f:
        data = json.load(f)
    cases = data["cases"]

    # Filter
    if args.ids:
        ids = set(args.ids.split(","))
        cases = [c for c in cases if c["id"] in ids]
    if args.tags:
        tags = set(args.tags.split(","))
        cases = [c for c in cases if tags.intersection(c.get("tags", []))]

    if not cases:
        print(f"{YELLOW}No test cases matched filters{RESET}")
        sys.exit(0)

    print(f"\nRunning {len(cases)} test cases ({args.runs} run(s) each)...\n")

    # Run evaluation
    all_results = []
    for run_idx in range(args.runs):
        if args.runs > 1:
            print(f"{DIM}--- Run {run_idx + 1}/{args.runs} ---{RESET}")
        for case in cases:
            result = evaluate_case(case)
            all_results.append(result)

    report = build_report(all_results)
    print_report(report)

    if args.output:
        save_report(report, args.output)

    sys.exit(0 if report.failed == 0 and report.errors == 0 else 1)


if __name__ == "__main__":
    main()
