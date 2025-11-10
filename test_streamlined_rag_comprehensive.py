#!/usr/bin/env python3
"""
Comprehensive Integration Tests for Streamlined RAG v4.0

This test suite covers all major functionalities:
- Intent Detection (search vs non-search queries)
- SQL Pre-filtering (category, THC, CBD)
- Attribute Filtering with Fuzzy Matching (flavors, effects, helps_with)
- Vector Semantic Search
- Bilingual Support (EN/ES)
- Follow-up Query Handling
- Session Management
- Fallback Strategies

Run before removing any legacy code to ensure system stability.

Usage:
    python test_streamlined_rag_comprehensive.py
    # or with pytest:
    pytest test_streamlined_rag_comprehensive.py -v
"""

import requests
import sys
import json
from typing import Dict, List, Optional, Any

# Simple color codes (fallback if colorama not available)
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    # ANSI color codes fallback
    class Fore:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        CYAN = '\033[96m'
        MAGENTA = '\033[95m'
        RESET = '\033[0m'

    class Style:
        RESET_ALL = '\033[0m'

# Test configuration
API_BASE_URL = "http://localhost:8001"
API_ENDPOINT = f"{API_BASE_URL}/api/v1/chat/ask/"

# Test counters
tests_passed = 0
tests_failed = 0
tests_total = 0


class TestResult:
    """Test result container"""
    def __init__(self, name: str, passed: bool, details: str = "", response: Optional[Dict] = None):
        self.name = name
        self.passed = passed
        self.details = details
        self.response = response


def print_header(text: str):
    """Print section header"""
    print(f"\n{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{text.center(80)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 80}{Style.RESET_ALL}\n")


def print_test_result(result: TestResult):
    """Print individual test result"""
    global tests_passed, tests_failed, tests_total

    tests_total += 1

    if result.passed:
        tests_passed += 1
        status = f"{Fore.GREEN}✓ PASS{Style.RESET_ALL}"
    else:
        tests_failed += 1
        status = f"{Fore.RED}✗ FAIL{Style.RESET_ALL}"

    print(f"{status} | {result.name}")
    if result.details:
        print(f"       {Fore.YELLOW}{result.details}{Style.RESET_ALL}")


def send_query(message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Send chat query to API"""
    payload = {"message": message}
    if session_id:
        payload["session_id"] = session_id

    try:
        response = requests.post(API_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


# ============================================================================
# TEST SUITE 1: INTENT DETECTION
# ============================================================================

def test_intent_detection():
    """Test query intent detection (search vs non-search)"""
    print_header("TEST SUITE 1: INTENT DETECTION")

    test_cases = [
        # Non-search queries (should return 0 strains)
        {
            "query": "hey, how can you help me",
            "expected_search": False,
            "expected_strains": 0,
            "description": "Greeting query"
        },
        {
            "query": "thank you!",
            "expected_search": False,
            "expected_strains": 0,
            "description": "Thank you message"
        },
        {
            "query": "hola, ¿qué puedes hacer?",
            "expected_search": False,
            "expected_strains": 0,
            "description": "Spanish greeting"
        },
        {
            "query": "what is cannabis?",
            "expected_search": False,
            "expected_strains": 0,
            "description": "General question"
        },

        # Search queries (should return strains)
        {
            "query": "suggest me indica",
            "expected_search": True,
            "expected_strains": ">0",
            "description": "Simple search query"
        },
        {
            "query": "necesito algo para dormir",
            "expected_search": True,
            "expected_strains": ">0",
            "description": "Spanish medical query"
        },
    ]

    for case in test_cases:
        data = send_query(case["query"])

        if "error" in data:
            print_test_result(TestResult(
                name=f"Intent: {case['description']}",
                passed=False,
                details=f"API Error: {data['error']}"
            ))
            continue

        is_search = data.get("filters_applied", {}).get("is_search_query")
        num_strains = len(data.get("recommended_strains", []))

        # Validate expectations
        passed = True
        details_parts = []

        # Check is_search_query flag
        if is_search is not None and is_search != case["expected_search"]:
            passed = False
            details_parts.append(f"is_search_query={is_search} (expected {case['expected_search']})")

        # Check strain count
        if case["expected_strains"] == 0:
            if num_strains != 0:
                passed = False
                details_parts.append(f"returned {num_strains} strains (expected 0)")
        elif case["expected_strains"] == ">0":
            if num_strains == 0:
                passed = False
                details_parts.append(f"returned 0 strains (expected >0)")

        details = "; ".join(details_parts) if details_parts else f"Strains: {num_strains}"

        print_test_result(TestResult(
            name=f"Intent: {case['description']} - '{case['query'][:40]}...'",
            passed=passed,
            details=details,
            response=data
        ))


# ============================================================================
# TEST SUITE 2: ATTRIBUTE FILTERING
# ============================================================================

def test_attribute_filtering():
    """Test SQL pre-filtering with fuzzy matching"""
    print_header("TEST SUITE 2: ATTRIBUTE FILTERING")

    # Test 1: Exact flavor match
    data = send_query("suggest me indica with tropical flavor and high thc")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    passed = (
        filters.get("category") == "Indica" and
        "tropical" in filters.get("flavors", []) and
        filters.get("min_thc") == 20 and
        len(strains) > 0
    )

    # Check if returned strains actually have tropical flavor
    has_tropical = False
    if strains:
        for strain in strains:
            flavors = [f["name"].lower() for f in strain.get("flavors", [])]
            if "tropical" in flavors:
                has_tropical = True
                break

    passed = passed and has_tropical

    details = (
        f"Category: {filters.get('category')}, "
        f"Flavors: {filters.get('flavors')}, "
        f"THC: {filters.get('min_thc')}, "
        f"Results: {len(strains)}, "
        f"Has tropical: {has_tropical}"
    )

    print_test_result(TestResult(
        name="Flavor Filter: Exact match (tropical)",
        passed=passed,
        details=details
    ))

    # Test 2: Fuzzy matching (typo)
    data = send_query("suggest me indica with tropicas flavor and high thc")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    # Should still find "tropical" despite typo "tropicas"
    has_tropical = False
    if strains:
        for strain in strains:
            flavors = [f["name"].lower() for f in strain.get("flavors", [])]
            if "tropical" in flavors:
                has_tropical = True
                break

    passed = (
        "tropicas" in filters.get("flavors", []) and  # Fuzzy input preserved
        len(strains) > 0 and
        has_tropical  # But found "tropical"
    )

    details = (
        f"Input: 'tropicas' (typo), "
        f"Found: {len(strains)} strains with 'tropical', "
        f"Fuzzy match: {'✓' if has_tropical else '✗'}"
    )

    print_test_result(TestResult(
        name="Flavor Filter: Fuzzy matching (tropicas → tropical)",
        passed=passed,
        details=details
    ))

    # Test 3: Effects filtering
    data = send_query("dame algo relajado para dormir con alto thc")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    # Check that results have relaxed/sleepy effects
    has_relaxed = False
    if strains:
        for strain in strains:
            effects = [f["name"].lower() for f in strain.get("feelings", [])]
            if "relaxed" in effects or "sleepy" in effects:
                has_relaxed = True
                break

    passed = (
        filters.get("category") == "Indica" and
        len(strains) > 0 and
        has_relaxed
    )

    details = (
        f"Language: ES, "
        f"Effects filter: {filters.get('effects')}, "
        f"Results: {len(strains)}, "
        f"Has relaxed/sleepy: {has_relaxed}"
    )

    print_test_result(TestResult(
        name="Effects Filter: Spanish + bilingual (relajado → relaxed)",
        passed=passed,
        details=details
    ))

    # Test 4: Medical use (helps_with)
    data = send_query("which strains help with pain and anxiety")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    # Check that results help with pain or anxiety
    helps_with_match = False
    if strains:
        for strain in strains:
            helps = [h["name"].lower() for h in strain.get("helps_with", [])]
            if "pain" in helps or "anxiety" in helps:
                helps_with_match = True
                break

    passed = (
        len(strains) > 0 and
        helps_with_match
    )

    details = (
        f"Helps_with filter: {filters.get('helps_with')}, "
        f"Results: {len(strains)}, "
        f"Match found: {helps_with_match}"
    )

    print_test_result(TestResult(
        name="Medical Filter: helps_with (pain/anxiety)",
        passed=passed,
        details=details
    ))


# ============================================================================
# TEST SUITE 3: SQL PRE-FILTERING
# ============================================================================

def test_sql_prefiltering():
    """Test category and THC/CBD SQL filters"""
    print_header("TEST SUITE 3: SQL PRE-FILTERING")

    # Test 1: Category filter
    data = send_query("show me sativa strains")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    # All results should be Sativa
    all_sativa = all(s["category"] == "Sativa" for s in strains) if strains else False

    passed = (
        filters.get("category") == "Sativa" and
        len(strains) > 0 and
        all_sativa
    )

    details = (
        f"Category: {filters.get('category')}, "
        f"Results: {len(strains)}, "
        f"All Sativa: {all_sativa}"
    )

    print_test_result(TestResult(
        name="Category Filter: Sativa only",
        passed=passed,
        details=details
    ))

    # Test 2: High THC filter
    data = send_query("show me high thc strains")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    # Check that results have high THC (>= 20%)
    high_thc_count = 0
    if strains:
        for strain in strains:
            thc = float(strain.get("thc", 0) or 0)
            if thc >= 20:
                high_thc_count += 1

    passed = (
        filters.get("min_thc") == 20 and
        len(strains) > 0 and
        high_thc_count > 0
    )

    details = (
        f"THC filter: min={filters.get('min_thc')}, "
        f"Results: {len(strains)}, "
        f"High THC strains: {high_thc_count}/{len(strains)}"
    )

    print_test_result(TestResult(
        name="THC Filter: High THC (>= 20%)",
        passed=passed,
        details=details
    ))

    # Test 3: Combined filters
    data = send_query("show me indica with high thc")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    # Check category AND THC
    correct_results = 0
    if strains:
        for strain in strains:
            thc = float(strain.get("thc", 0) or 0)
            if strain["category"] == "Indica" and thc >= 20:
                correct_results += 1

    passed = (
        filters.get("category") == "Indica" and
        filters.get("min_thc") == 20 and
        len(strains) > 0 and
        correct_results > 0
    )

    details = (
        f"Category: {filters.get('category')}, "
        f"THC: min={filters.get('min_thc')}, "
        f"Correct results: {correct_results}/{len(strains)}"
    )

    print_test_result(TestResult(
        name="Combined Filter: Indica + High THC",
        passed=passed,
        details=details
    ))


# ============================================================================
# TEST SUITE 4: BILINGUAL SUPPORT
# ============================================================================

def test_bilingual_support():
    """Test English and Spanish query support"""
    print_header("TEST SUITE 4: BILINGUAL SUPPORT")

    test_cases = [
        {
            "query": "necesito algo para dormir",
            "expected_lang": "es",
            "description": "Spanish sleep query"
        },
        {
            "query": "I need something for sleep",
            "expected_lang": "en",
            "description": "English sleep query"
        },
        {
            "query": "muéstrame sativas energéticas",
            "expected_lang": "es",
            "description": "Spanish energy query"
        },
        {
            "query": "show me energetic sativas",
            "expected_lang": "en",
            "description": "English energy query"
        },
    ]

    for case in test_cases:
        data = send_query(case["query"])

        detected_lang = data.get("language", "").lower()
        strains = data.get("recommended_strains", [])

        passed = (
            detected_lang == case["expected_lang"] and
            len(strains) > 0
        )

        details = (
            f"Detected: {detected_lang}, "
            f"Expected: {case['expected_lang']}, "
            f"Results: {len(strains)}"
        )

        print_test_result(TestResult(
            name=f"Language: {case['description']}",
            passed=passed,
            details=details
        ))


# ============================================================================
# TEST SUITE 5: FOLLOW-UP QUERIES
# ============================================================================

def test_followup_queries():
    """Test context-aware follow-up query handling"""
    print_header("TEST SUITE 5: FOLLOW-UP QUERIES")

    # Step 1: Initial search
    data1 = send_query("suggest me indica with high thc")
    session_id = data1.get("session_id")
    strains1 = data1.get("recommended_strains", [])

    if not session_id or not strains1:
        print_test_result(TestResult(
            name="Follow-up: Initial search",
            passed=False,
            details="Failed to get session_id or strains from initial query"
        ))
        return

    print_test_result(TestResult(
        name="Follow-up: Initial search",
        passed=True,
        details=f"Session: {session_id[:20]}..., Strains: {len(strains1)}"
    ))

    # Step 2: Follow-up query
    data2 = send_query("which one has the lowest thc", session_id=session_id)

    filters2 = data2.get("filters_applied", {})
    strains2 = data2.get("recommended_strains", [])

    # Should be marked as follow-up
    is_followup = filters2.get("is_follow_up", False)

    # Should return same or subset of strains from initial search
    strain_ids1 = {s["id"] for s in strains1}
    strain_ids2 = {s["id"] for s in strains2}
    same_context = strain_ids2.issubset(strain_ids1) or strain_ids2 == strain_ids1

    passed = (
        is_followup and
        len(strains2) > 0 and
        same_context
    )

    details = (
        f"is_follow_up: {is_followup}, "
        f"Same context: {same_context}, "
        f"Results: {len(strains2)}"
    )

    print_test_result(TestResult(
        name="Follow-up: Context preservation",
        passed=passed,
        details=details
    ))


# ============================================================================
# TEST SUITE 6: FALLBACK STRATEGIES
# ============================================================================

def test_fallback_strategies():
    """Test fallback when exact matches not found"""
    print_header("TEST SUITE 6: FALLBACK STRATEGIES")

    # Test: Very specific query that might have 0 exact matches
    data = send_query("indica with cbd over 15%")

    strains = data.get("recommended_strains", [])
    response_text = data.get("response", "")

    # System should return SOMETHING (fallback to closest matches)
    # Check for fallback notice in response
    has_fallback_notice = (
        "no encontré" in response_text.lower() or
        "no exact" in response_text.lower() or
        "closest" in response_text.lower() or
        "más cercanas" in response_text.lower()
    )

    passed = len(strains) > 0  # Should always return something

    details = (
        f"Results: {len(strains)}, "
        f"Fallback notice: {has_fallback_notice}"
    )

    print_test_result(TestResult(
        name="Fallback: High CBD threshold (graceful degradation)",
        passed=passed,
        details=details
    ))


# ============================================================================
# TEST SUITE 7: VECTOR SEARCH
# ============================================================================

def test_vector_search():
    """Test semantic vector search functionality"""
    print_header("TEST SUITE 7: VECTOR SEARCH")

    # Semantic query (no exact keywords)
    data = send_query("I want something to relax after work")

    strains = data.get("recommended_strains", [])
    filters = data.get("filters_applied", {})

    # Should understand "relax after work" → Indica/Hybrid with relaxing effects
    has_relaxing = False
    if strains:
        for strain in strains:
            effects = [f["name"].lower() for f in strain.get("feelings", [])]
            if "relaxed" in effects or "sleepy" in effects or "calm" in effects:
                has_relaxing = True
                break

    passed = (
        len(strains) > 0 and
        has_relaxing
    )

    details = (
        f"Semantic query, "
        f"Results: {len(strains)}, "
        f"Has relaxing effects: {has_relaxing}"
    )

    print_test_result(TestResult(
        name="Vector Search: Semantic understanding",
        passed=passed,
        details=details
    ))


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def print_summary():
    """Print test summary"""
    print_header("TEST SUMMARY")

    print(f"Total Tests: {tests_total}")
    print(f"{Fore.GREEN}Passed: {tests_passed}{Style.RESET_ALL}")
    print(f"{Fore.RED}Failed: {tests_failed}{Style.RESET_ALL}")

    success_rate = (tests_passed / tests_total * 100) if tests_total > 0 else 0

    if success_rate == 100:
        print(f"\n{Fore.GREEN}{'🎉 ALL TESTS PASSED! 🎉'.center(80)}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'System is stable and ready for code cleanup.'.center(80)}{Style.RESET_ALL}")
    elif success_rate >= 90:
        print(f"\n{Fore.YELLOW}{'⚠️  MOSTLY PASSING ({:.1f}%)'.format(success_rate).center(80)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{'Review failed tests before cleanup.'.center(80)}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.RED}{'❌ MULTIPLE FAILURES ({:.1f}%)'.format(success_rate).center(80)}{Style.RESET_ALL}")
        print(f"{Fore.RED}{'DO NOT proceed with code cleanup!'.center(80)}{Style.RESET_ALL}")

    print()


def main():
    """Run all test suites"""
    print(f"\n{Fore.MAGENTA}{'*' * 80}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'STREAMLINED RAG v4.0 - COMPREHENSIVE INTEGRATION TESTS'.center(80)}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'*' * 80}{Style.RESET_ALL}")

    # Check API availability
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        print(f"{Fore.GREEN}✓ API is reachable at {API_BASE_URL}{Style.RESET_ALL}")
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}✗ Cannot reach API at {API_BASE_URL}{Style.RESET_ALL}")
        print(f"{Fore.RED}  Error: {e}{Style.RESET_ALL}")
        print(f"\n{Fore.YELLOW}Make sure the API is running: docker compose up -d{Style.RESET_ALL}")
        sys.exit(1)

    # Run all test suites
    try:
        test_intent_detection()
        test_attribute_filtering()
        test_sql_prefiltering()
        test_bilingual_support()
        test_followup_queries()
        test_fallback_strategies()
        test_vector_search()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Tests interrupted by user{Style.RESET_ALL}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Fore.RED}Unexpected error: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Print summary
    print_summary()

    # Exit code
    sys.exit(0 if tests_failed == 0 else 1)


if __name__ == "__main__":
    main()
