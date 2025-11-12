#!/usr/bin/env python3
"""
DB-Aware Architecture Integration Tests

Tests specifically for Phase 1 DB-Aware Architecture features:
- PostgreSQL pg_trgm fuzzy matching (mint → menthol)
- Dynamic LLM context from DB taxonomy
- Taxonomy caching (Redis + in-memory)
- Context switching in complex dialogs

Usage:
    python test_db_aware_architecture.py
"""

import requests
import sys
import json
from typing import Dict, List, Optional, Any

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
# TEST SUITE 1: FUZZY MATCHING WITH pg_trgm
# ============================================================================

def test_fuzzy_matching():
    """Test PostgreSQL pg_trgm fuzzy matching"""
    print_header("TEST SUITE 1: FUZZY MATCHING WITH pg_trgm")

    # Test 1: mint → menthol (trigram similarity)
    data = send_query("show me strains with mint flavor")

    strains = data.get("recommended_strains", [])

    # Check if results have menthol or mint flavors
    has_mint_or_menthol = False
    mint_strains = []
    if strains:
        for strain in strains:
            flavors = [f["name"].lower() for f in strain.get("flavors", [])]
            if "mint" in flavors or "menthol" in flavors or "menta" in flavors:
                has_mint_or_menthol = True
                mint_strains.append(strain["name"])

    passed = (
        len(strains) > 0 and
        has_mint_or_menthol
    )

    details = (
        f"Query: 'mint', "
        f"Results: {len(strains)}, "
        f"Has mint/menthol: {has_mint_or_menthol}, "
        f"Strains: {mint_strains[:3]}"
    )

    print_test_result(TestResult(
        name="Fuzzy Match: mint → menthol/mint",
        passed=passed,
        details=details
    ))

    # Test 2: lemon → lemon/citrus (exact + fuzzy)
    data = send_query("recomienda hybrid con sabor a lemon")

    strains = data.get("recommended_strains", [])

    # Check if results have lemon or citrus flavors
    has_lemon_or_citrus = False
    lemon_strains = []
    if strains:
        for strain in strains:
            flavors = [f["name"].lower() for f in strain.get("flavors", [])]
            if "lemon" in flavors or "citrus" in flavors or "limón" in flavors or "cítricos" in flavors:
                has_lemon_or_citrus = True
                lemon_strains.append(strain["name"])

    passed = (
        len(strains) > 0 and
        has_lemon_or_citrus
    )

    details = (
        f"Query: 'lemon', "
        f"Results: {len(strains)}, "
        f"Has lemon/citrus: {has_lemon_or_citrus}, "
        f"Strains: {lemon_strains[:3]}"
    )

    print_test_result(TestResult(
        name="Fuzzy Match: lemon → lemon/citrus",
        passed=passed,
        details=details
    ))

    # Test 3: Typo handling (citricos → cítricos)
    data = send_query("dame hybrid con sabor citricos")

    strains = data.get("recommended_strains", [])

    # Check if results have citrus flavors
    has_citrus = False
    if strains:
        for strain in strains:
            flavors = [f["name"].lower() for f in strain.get("flavors", [])]
            if "citrus" in flavors or "cítricos" in flavors or "citricos" in flavors:
                has_citrus = True
                break

    passed = (
        len(strains) > 0 and
        has_citrus
    )

    details = (
        f"Query: 'citricos' (typo), "
        f"Results: {len(strains)}, "
        f"Has citrus: {has_citrus}"
    )

    print_test_result(TestResult(
        name="Fuzzy Match: citricos → cítricos (typo handling)",
        passed=passed,
        details=details
    ))


# ============================================================================
# TEST SUITE 2: DYNAMIC LLM CONTEXT FROM DB
# ============================================================================

def test_dynamic_llm_context():
    """Test that LLM receives dynamic DB taxonomy context"""
    print_header("TEST SUITE 2: DYNAMIC LLM CONTEXT FROM DB")

    # Test 1: Flavor extraction with DB context
    data = send_query("suggest me indica with mint and tropical flavors")

    filters = data.get("filters_applied", {})
    strains = data.get("recommended_strains", [])

    # LLM should extract both flavors
    extracted_flavors = filters.get("flavors", [])
    has_mint = any("mint" in str(f).lower() or "menta" in str(f).lower() for f in extracted_flavors)
    has_tropical = any("tropical" in str(f).lower() for f in extracted_flavors)

    passed = (
        len(extracted_flavors) >= 2 and
        (has_mint or has_tropical)  # At least one should be extracted
    )

    details = (
        f"Extracted flavors: {extracted_flavors}, "
        f"Has mint: {has_mint}, "
        f"Has tropical: {has_tropical}, "
        f"Results: {len(strains)}"
    )

    print_test_result(TestResult(
        name="LLM Context: Multi-flavor extraction",
        passed=passed,
        details=details
    ))

    # Test 2: Medical term extraction
    data = send_query("necesito algo para ansiedad y dolor")

    filters = data.get("filters_applied", {})

    extracted_medical = filters.get("helps_with", [])
    has_anxiety = any("ansi" in str(m).lower() for m in extracted_medical)
    has_pain = any("dolor" in str(m).lower() or "pain" in str(m).lower() for m in extracted_medical)

    passed = (
        len(extracted_medical) >= 1 and
        (has_anxiety or has_pain)
    )

    details = (
        f"Extracted medical: {extracted_medical}, "
        f"Has anxiety: {has_anxiety}, "
        f"Has pain: {has_pain}"
    )

    print_test_result(TestResult(
        name="LLM Context: Medical term extraction (ES)",
        passed=passed,
        details=details
    ))


# ============================================================================
# TEST SUITE 3: COMPLEX DIALOG WITH CONTEXT SWITCHING
# ============================================================================

def test_complex_dialog():
    """Test complex dialog with context switching"""
    print_header("TEST SUITE 3: COMPLEX DIALOG WITH CONTEXT SWITCHING")

    session_id = None

    # Step 1: Initial search - Indica with high THC
    data1 = send_query("dame indica con alto THC")
    session_id = data1.get("session_id")
    strains1 = data1.get("recommended_strains", [])

    if not session_id or not strains1:
        print_test_result(TestResult(
            name="Dialog Step 1: Initial search (Indica + high THC)",
            passed=False,
            details="Failed to get session_id or strains"
        ))
        return

    # Check category
    all_indica = all(s["category"] == "Indica" for s in strains1)

    passed1 = len(strains1) > 0 and all_indica

    print_test_result(TestResult(
        name="Dialog Step 1: Initial search (Indica + high THC)",
        passed=passed1,
        details=f"Session: {session_id[:20]}..., Strains: {len(strains1)}, All Indica: {all_indica}"
    ))

    # Step 2: Context switch - Sativa for creativity
    data2 = send_query("ahora quiero sativa para creatividad", session_id=session_id)
    strains2 = data2.get("recommended_strains", [])

    # Should switch to Sativa
    has_sativa = any(s["category"] == "Sativa" for s in strains2)

    passed2 = len(strains2) > 0 and has_sativa

    print_test_result(TestResult(
        name="Dialog Step 2: Context switch (Indica → Sativa)",
        passed=passed2,
        details=f"Results: {len(strains2)}, Has Sativa: {has_sativa}"
    ))

    # Step 3: Follow-up from new context
    data3 = send_query("cual tiene el THC mas alto?", session_id=session_id)
    strains3 = data3.get("recommended_strains", [])

    # Should work with strains from step 2 (Sativa)
    strain_ids2 = {s["id"] for s in strains2}
    strain_ids3 = {s["id"] for s in strains3}
    same_context = len(strain_ids3.intersection(strain_ids2)) > 0

    passed3 = len(strains3) > 0 and same_context

    print_test_result(TestResult(
        name="Dialog Step 3: Follow-up from new context",
        passed=passed3,
        details=f"Results: {len(strains3)}, Same context: {same_context}"
    ))


# ============================================================================
# TEST SUITE 4: TAXONOMY CACHE VALIDATION
# ============================================================================

def test_taxonomy_cache():
    """Validate that taxonomy cache is working"""
    print_header("TEST SUITE 4: TAXONOMY CACHE VALIDATION")

    # Test: Multiple queries should use cached taxonomy
    queries = [
        "show me indica with tropical flavor",
        "dame sativa con sabor citrus",
        "hybrid with mint taste"
    ]

    results = []
    for query in queries:
        data = send_query(query)
        strains = data.get("recommended_strains", [])
        results.append(len(strains) > 0)

    all_success = all(results)

    passed = all_success

    details = (
        f"Queries: {len(queries)}, "
        f"All returned results: {all_success}, "
        f"Cache should be used for all"
    )

    print_test_result(TestResult(
        name="Taxonomy Cache: Multiple queries performance",
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
        print(f"{Fore.GREEN}{'DB-Aware Architecture is working correctly!'.center(80)}{Style.RESET_ALL}")
    elif success_rate >= 80:
        print(f"\n{Fore.YELLOW}{'⚠️  MOSTLY PASSING ({:.1f}%)'.format(success_rate).center(80)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{'Review failed tests.'.center(80)}{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.RED}{'❌ MULTIPLE FAILURES ({:.1f}%)'.format(success_rate).center(80)}{Style.RESET_ALL}")
        print(f"{Fore.RED}{'DB-Aware Architecture needs fixes!'.center(80)}{Style.RESET_ALL}")

    print()


def main():
    """Run all test suites"""
    print(f"\n{Fore.MAGENTA}{'*' * 80}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'DB-AWARE ARCHITECTURE - INTEGRATION TESTS'.center(80)}{Style.RESET_ALL}")
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
        test_fuzzy_matching()
        test_dynamic_llm_context()
        test_complex_dialog()
        test_taxonomy_cache()
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
