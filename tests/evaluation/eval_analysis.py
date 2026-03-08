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
import asyncio
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
    groq_known_failure: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class EvalReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    groq_known_failures: int = 0
    field_accuracy: Dict[str, Dict[str, int]] = field(default_factory=dict)
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_avg: float = 0.0
    case_results: List[CaseResult] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    provider_name: str = ""
    model_name: str = ""


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

def build_report(results: List[CaseResult], provider: str = "", model: str = "") -> EvalReport:
    report = EvalReport()
    report.total = len(results)
    report.case_results = results
    report.provider_name = provider
    report.model_name = model

    latencies = []

    for cr in results:
        if cr.error:
            report.errors += 1
        elif cr.groq_known_failure and not cr.passed:
            report.groq_known_failures += 1
        elif cr.passed:
            report.passed += 1
        else:
            report.failed += 1
        latencies.append(cr.latency_ms)
        report.total_input_tokens += cr.input_tokens
        report.total_output_tokens += cr.output_tokens

        # Field-level accuracy tracking (skip groq known failures from stats)
        if not (cr.groq_known_failure and not cr.passed):
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
    header = f"EVALUATION REPORT"
    if report.provider_name:
        header += f" — {report.provider_name}"
        if report.model_name:
            header += f" / {report.model_name}"
    print(f"\n{CYAN}{'=' * 80}{RESET}")
    print(f"{CYAN}{header.center(80)}{RESET}")
    print(f"{CYAN}{'=' * 80}{RESET}\n")

    # Per-case results
    for cr in report.case_results:
        if cr.error:
            status = f"{RED}ERR{RESET}"
        elif cr.passed:
            status = f"{GREEN}OK {RESET}"
        elif cr.groq_known_failure:
            status = f"{YELLOW}KNW{RESET}"  # Known limitation
        else:
            status = f"{RED}FAIL{RESET}"

        latency_str = f"{DIM}{cr.latency_ms:7.0f}ms{RESET}"
        tok_str = f"{DIM}↑{cr.input_tokens}↓{cr.output_tokens}{RESET}" if cr.input_tokens else ""
        print(f"  {status} {latency_str}  {cr.case_id:<38} {tok_str}")

        if not cr.passed and not cr.error:
            if cr.groq_known_failure:
                print(f"         {YELLOW}[known Groq limitation — runtime override handles it]{RESET}")
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
    effective_total = report.total - report.groq_known_failures
    pass_rate = (report.passed / effective_total * 100) if effective_total else 0
    print(f"\n  {BOLD}Results:{RESET}  {report.passed}/{effective_total} passed ({pass_rate:.1f}%)"
          f"  |  {report.failed} failed  |  {report.errors} errors"
          + (f"  |  {YELLOW}{report.groq_known_failures} known{RESET}" if report.groq_known_failures else ""))

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

    # Token usage
    if report.total_input_tokens > 0:
        print(f"\n  {BOLD}Token Usage:{RESET}")
        print(f"    input={report.total_input_tokens:,}  output={report.total_output_tokens:,}  "
              f"total={report.total_input_tokens + report.total_output_tokens:,}")
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
# Direct evaluation (no API required — uses LLMRegistry directly)
# ---------------------------------------------------------------------------

def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base — compatible with all GPT-4 family models)."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text, disallowed_special=()))
    except Exception:
        return len(text) // 4  # rough fallback


async def evaluate_case_direct(case: Dict, analyzer, system_prompt: str = "") -> CaseResult:
    """Evaluate a single case by calling StreamlinedQueryAnalyzer directly.

    Only checks analysis fields (is_search_query, detected_category, etc.).
    Skips strain count / result trait / filter checks (those need the DB pipeline).
    """
    case_id = case["id"]
    query = case["query"]
    language = case.get("language", "en")
    expected = case.get("expected", {})
    tags = case.get("tags", [])
    session_context = case.get("session_context")
    groq_known = case.get("groq_known_failure", False)

    start = time.time()
    try:
        analysis = await analyzer.aanalyze_query(
            user_query=query,
            session_context=session_context,
            explicit_language=language,
        )
        latency_ms = (time.time() - start) * 1000
    except Exception as e:
        return CaseResult(
            case_id=case_id, query=query, language=language, tags=tags,
            passed=False, latency_ms=(time.time() - start) * 1000,
            error=str(e), groq_known_failure=groq_known
        )

    # Token estimation
    user_prompt_approx = f'USER QUERY: "{query}"\nTARGET LANGUAGE: {language}\nRECOMMENDED STRAINS: {session_context}\n'
    input_toks = _count_tokens(system_prompt) + _count_tokens(user_prompt_approx) if system_prompt else 0
    output_toks = _count_tokens(analysis.model_dump_json()) if input_toks else 0

    direct_fields = [
        "is_search_query", "is_follow_up", "detected_language",
        "detected_category", "thc_level", "cbd_level", "specific_strain_name",
    ]
    field_results = []
    for fname in direct_fields:
        if fname in expected:
            actual = getattr(analysis, fname, None)
            fr = FieldResult(fname, expected[fname], actual,
                             check_field(expected[fname], actual))
            field_results.append(fr)

    overall = all(fr.passed for fr in field_results)
    return CaseResult(
        case_id=case_id, query=query, language=language, tags=tags,
        passed=overall, field_results=field_results,
        latency_ms=latency_ms, groq_known_failure=groq_known,
        input_tokens=input_toks, output_tokens=output_toks
    )


async def run_direct(cases: List[Dict], runs: int) -> tuple:
    """Run all cases directly against the analyzer (no API).
    Returns (results, provider_name, model_name).
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    # Load .env so OPENAI_API_KEY / GROQ_API_KEY are available
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass

    from app.core.llm_registry import get_llm_registry
    from app.core.streamlined_analyzer import StreamlinedQueryAnalyzer

    registry = get_llm_registry()
    analyzer = StreamlinedQueryAnalyzer(
        registry.get_default_llm(),
        analysis_provider=registry.get_analysis_provider(),
        response_provider=registry.get_response_provider(),
        prompt_strategy=registry.get_prompt_strategy(),
    )

    provider_env = (os.getenv("ANALYSIS_LLM_PROVIDER") or "").strip().lower()
    provider_name = provider_env if provider_env in {"groq", "openai"} else "openai"
    model = os.getenv("GROQ_ANALYSIS_MODEL" if provider_name == "groq" else "OPENAI_AGENT_MODEL",
                      "llama-3.3-70b-versatile" if provider_name == "groq" else "gpt-4o-mini")
    print(f"{GREEN}Direct mode — provider: {provider_name}, model: {model}, "
          f"strategy: {type(analyzer._prompt_strategy).__name__}{RESET}")

    # Build sample system prompt once for token estimation
    sample_context = {"user_query": "test", "has_session": False, "conversation_summary": "",
                      "previous_language": "en", "target_language": "en", "fallback_note": "",
                      "recommended_strains": "None"}
    try:
        db_section = analyzer._build_db_context_section(sample_context, "en")
        system_prompt = analyzer._prompt_strategy.get_system_prompt_template().format(db_context=db_section)
    except Exception:
        system_prompt = ""

    all_results = []
    for run_idx in range(runs):
        if runs > 1:
            print(f"{DIM}--- Run {run_idx + 1}/{runs} ---{RESET}")
        for case in cases:
            result = await evaluate_case_direct(case, analyzer, system_prompt)
            all_results.append(result)
    return all_results, provider_name, model


# ---------------------------------------------------------------------------
# Cost comparison
# ---------------------------------------------------------------------------

# Pricing per 1M tokens (USD, as of 2025-Q2)
MODEL_PRICING = {
    "gpt-4o-mini":    {"input": 0.15,  "output": 0.60,  "note": "current production"},
    "gpt-4.1-mini":   {"input": 0.40,  "output": 1.60,  "note": "newer, ~2.7x cost"},
    "gpt-4.1-nano":   {"input": 0.10,  "output": 0.40,  "note": "cheapest OpenAI"},
    "gpt-4o":         {"input": 2.50,  "output": 10.00, "note": "full model"},
    "gpt-4.1":        {"input": 2.00,  "output": 8.00,  "note": "newer full model"},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79, "note": "Groq, fastest"},
}
REQUESTS_PER_MONTH = 10_000  # assumed monthly volume for scaling


def print_cost_comparison(report: EvalReport):
    if report.total_input_tokens == 0:
        return

    n = report.total  # cases run
    avg_input  = report.total_input_tokens  / max(n, 1)
    avg_output = report.total_output_tokens / max(n, 1)

    print(f"\n{CYAN}{'─' * 80}{RESET}")
    print(f"\n  {BOLD}Cost Comparison (analysis LLM only){RESET}")
    print(f"  Measured: avg {avg_input:.0f} input + {avg_output:.0f} output tokens/request")
    print(f"  Scale: {REQUESTS_PER_MONTH:,} requests/month\n")
    print(f"  {'Model':<30} {'$/1k req':>9}  {'$/month':>10}  {'vs 4o-mini':>10}  Note")
    print(f"  {'-'*30} {'-'*9}  {'-'*10}  {'-'*10}  {'-'*25}")

    base_cost = None
    for model_id, pricing in MODEL_PRICING.items():
        cost_per_req = (avg_input / 1e6 * pricing["input"]
                        + avg_output / 1e6 * pricing["output"])
        cost_per_month = cost_per_req * REQUESTS_PER_MONTH
        cost_per_1k = cost_per_req * 1000

        if model_id == "gpt-4o-mini":
            base_cost = cost_per_month

        ratio = f"{cost_per_month / base_cost:.1f}x" if base_cost else "—"
        highlight = BOLD if model_id == report.model_name else ""
        marker = " ◀ current" if model_id == report.model_name else ""
        print(f"  {highlight}{model_id:<30}{RESET} ${cost_per_1k:>7.4f}  ${cost_per_month:>9.2f}  "
              f"{ratio:>10}  {DIM}{pricing['note']}{marker}{RESET}")

    print()


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
    parser.add_argument("--direct", action="store_true",
                        help="Run without API: call analyzer directly (set ANALYSIS_LLM_PROVIDER + GROQ_API_KEY for Groq)")
    parser.add_argument("--costs", action="store_true",
                        help="Show cost comparison across models (direct mode only)")
    args = parser.parse_args()

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

    if args.direct:
        all_results, provider_name, model_name = asyncio.run(run_direct(cases, args.runs))
    else:
        provider_name, model_name = "api", ""
        api_base = args.api_url
        global API_ENDPOINT
        API_ENDPOINT = f"{api_base}/api/v1/chat/ask/"

        try:
            requests.get(f"{api_base}/", timeout=5)
            print(f"{GREEN}API reachable at {api_base}{RESET}")
        except requests.exceptions.RequestException:
            print(f"{RED}Cannot reach API at {api_base}{RESET}")
            sys.exit(1)

        all_results = []
        for run_idx in range(args.runs):
            if args.runs > 1:
                print(f"{DIM}--- Run {run_idx + 1}/{args.runs} ---{RESET}")
            for case in cases:
                all_results.append(evaluate_case(case))

    report = build_report(all_results, provider=provider_name, model=model_name)
    print_report(report)

    if args.direct and (args.costs or report.total_input_tokens > 0):
        print_cost_comparison(report)

    if args.output:
        save_report(report, args.output)

    sys.exit(0 if report.failed == 0 and report.errors == 0 else 1)


if __name__ == "__main__":
    main()
