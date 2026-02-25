#!/usr/bin/env python3
"""
Conversation Quality Evaluation — LLM-as-Judge

Simulates real user conversations across 10 diverse scenarios and evaluates
response quality on 5 dimensions (1-5 scale each):
  - Relevance   : strains actually match what user asked
  - Language    : response in correct language, consistent with query
  - Helpfulness : response helps user make a decision
  - Naturalness : sounds like a knowledgeable budtender, not robotic
  - Accuracy    : correctly refers to returned strain names/details

Usage:
    python tests/test_conversation_quality.py
    python tests/test_conversation_quality.py --no-judge   # skip LLM judge, only rule checks
    python tests/test_conversation_quality.py --scenario 3 # run one scenario
    python tests/test_conversation_quality.py --verbose     # show full responses
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = '\033[92m'; RED = '\033[91m'; YELLOW = '\033[93m'
        CYAN = '\033[96m'; MAGENTA = '\033[95m'; WHITE = '\033[97m'; BLUE = '\033[94m'
    class Style:
        RESET_ALL = '\033[0m'; BRIGHT = '\033[1m'

API_BASE = "http://localhost:8001"
ASK_URL  = f"{API_BASE}/api/v1/chat/ask/"


# ─────────────────────────────────────────────────────────────────
# DATA TYPES
# ─────────────────────────────────────────────────────────────────

@dataclass
class TurnExpectation:
    """Expected outcomes for one conversation turn."""
    is_search: Optional[bool] = None        # None = don't check
    expect_strains: Optional[bool] = None   # True=must have, False=must be empty
    min_strains: int = 0
    language: Optional[str] = None          # 'en' or 'es'
    category: Optional[str] = None          # Indica/Sativa/Hybrid
    is_follow_up: Optional[bool] = None
    response_must_contain: List[str] = field(default_factory=list)   # substrings
    response_must_not_contain: List[str] = field(default_factory=list)
    check_response_mentions_strain: bool = False  # response mentions ≥1 returned strain name


@dataclass
class Turn:
    message: str
    language: str = "en"
    expectation: TurnExpectation = field(default_factory=TurnExpectation)
    note: str = ""   # human-readable description of what this turn tests


@dataclass
class Scenario:
    id: int
    name: str
    description: str
    turns: List[Turn]


@dataclass
class TurnResult:
    turn_idx: int
    message: str
    language: str
    note: str
    response_data: Dict[str, Any]
    rule_checks: Dict[str, bool]   # check_name → passed
    quality_scores: Dict[str, int] = field(default_factory=dict)  # dim → 1-5
    quality_reasoning: str = ""
    latency_ms: float = 0.0

    @property
    def rule_passed(self) -> bool:
        return all(self.rule_checks.values())

    @property
    def quality_avg(self) -> float:
        if not self.quality_scores:
            return 0.0
        return sum(self.quality_scores.values()) / len(self.quality_scores)


@dataclass
class ScenarioResult:
    scenario: Scenario
    turn_results: List[TurnResult]

    @property
    def all_rules_passed(self) -> bool:
        return all(t.rule_passed for t in self.turn_results)

    @property
    def avg_quality(self) -> float:
        scored = [t.quality_avg for t in self.turn_results if t.quality_scores]
        return sum(scored) / len(scored) if scored else 0.0


# ─────────────────────────────────────────────────────────────────
# SCENARIOS
# ─────────────────────────────────────────────────────────────────

SCENARIOS: List[Scenario] = [

    Scenario(
        id=1,
        name="new_user_discovery",
        description="New user greets → explores → compares (EN). Tests: non-search, search, follow-up.",
        turns=[
            Turn(
                message="hey, what can you help me with?",
                language="en",
                note="Greeting — must NOT trigger search",
                expectation=TurnExpectation(
                    is_search=False,
                    expect_strains=False,
                    language="en",
                )
            ),
            Turn(
                message="I want something to relax after a long day at work",
                language="en",
                note="First search — evening/relax context should suggest Indica",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    min_strains=3,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
            Turn(
                message="which one has the lowest THC?",
                language="en",
                note="Follow-up compare — must stay on same strain list",
                expectation=TurnExpectation(
                    is_search=True,
                    is_follow_up=True,
                    expect_strains=True,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
        ]
    ),

    Scenario(
        id=2,
        name="medical_user_en",
        description="User with pain & insomnia narrows options step by step (EN).",
        turns=[
            Turn(
                message="I have chronic pain and insomnia, what do you recommend?",
                language="en",
                note="Medical query — helps_with filter expected",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    min_strains=3,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
            Turn(
                message="show me only indica from those",
                language="en",
                note="Follow-up filter by category",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                )
            ),
            Turn(
                message="which one would you personally recommend and why?",
                language="en",
                note="Soft follow-up — response should justify recommendation",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
        ]
    ),

    Scenario(
        id=3,
        name="spanish_conversation",
        description="Full conversation in Spanish. Tests bilingual consistency across 3 turns.",
        turns=[
            Turn(
                message="hola, buenas tardes",
                language="es",
                note="Spanish greeting",
                expectation=TurnExpectation(
                    is_search=False,
                    expect_strains=False,
                    language="es",
                )
            ),
            Turn(
                message="necesito algo para la ansiedad y el estrés del trabajo",
                language="es",
                note="Spanish medical query — anxiety/stress",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    min_strains=3,
                    language="es",
                    check_response_mentions_strain=True,
                )
            ),
            Turn(
                message="¿cuál tiene menos efectos secundarios?",
                language="es",
                note="Follow-up in Spanish — least side effects",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="es",
                    check_response_mentions_strain=True,
                )
            ),
        ]
    ),

    Scenario(
        id=4,
        name="flavor_hunter",
        description="User wants specific flavors, then refines by THC level.",
        turns=[
            Turn(
                message="I want something with tropical and citrus flavor",
                language="en",
                note="Flavor-specific search",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    min_strains=2,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
            Turn(
                message="I prefer lower THC, something not too strong",
                language="en",
                note="Context switch with new THC filter — not a follow-up",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                )
            ),
        ]
    ),

    Scenario(
        id=5,
        name="context_switch",
        description="User clearly changes intent mid-conversation. Tests that is_follow_up=False on new criteria.",
        turns=[
            Turn(
                message="suggest indica strains for sleep",
                language="en",
                note="Initial search — sleep/indica",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    category="Indica",
                    language="en",
                )
            ),
            Turn(
                message="actually, forget that. I want sativa for energy and creativity",
                language="en",
                note="Context switch — must NOT be follow-up",
                expectation=TurnExpectation(
                    is_search=True,
                    is_follow_up=False,
                    expect_strains=True,
                    category="Sativa",
                    language="en",
                )
            ),
            Turn(
                message="which one has the highest THC?",
                language="en",
                note="Follow-up on Sativa list (not Indica)",
                expectation=TurnExpectation(
                    is_search=True,
                    is_follow_up=True,
                    expect_strains=True,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
        ]
    ),

    Scenario(
        id=6,
        name="specific_strain_inquiry",
        description="User asks about a specific strain, then wants similar options.",
        turns=[
            Turn(
                message="tell me about Northern Lights",
                language="en",
                note="Specific strain query — must return exactly 1 or very few strains",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                    check_response_mentions_strain=True,
                    response_must_contain=["Northern Lights"],
                )
            ),
            Turn(
                message="show me similar strains with the same relaxing effects",
                language="en",
                note="New search based on context — should NOT be treated as follow-up",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    min_strains=2,
                    language="en",
                )
            ),
        ]
    ),

    Scenario(
        id=7,
        name="power_user_multifilter",
        description="Experienced user specifies multiple filters in one shot.",
        turns=[
            Turn(
                message="show me hybrid with high CBD, tropical flavor, helps with anxiety, THC under 15%",
                language="en",
                note="Multi-filter: category + CBD + flavor + medical + THC cap",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
        ]
    ),

    Scenario(
        id=8,
        name="non_search_handling",
        description="General questions and out-of-domain queries — system should respond helpfully without searching.",
        turns=[
            Turn(
                message="what is the difference between indica and sativa?",
                language="en",
                note="General cannabis knowledge question",
                expectation=TurnExpectation(
                    is_search=False,
                    expect_strains=False,
                    language="en",
                )
            ),
            Turn(
                message="can you recommend a good pizza place near me?",
                language="en",
                note="Fully out-of-domain — should politely decline or redirect",
                expectation=TurnExpectation(
                    is_search=False,
                    expect_strains=False,
                    language="en",
                    # Note: response may correctly mention "pizza" while declining — that's OK
                )
            ),
            Turn(
                message="ok then, show me something for stress relief",
                language="en",
                note="Back to cannabis after off-topic — search should resume normally",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                )
            ),
        ]
    ),

    Scenario(
        id=9,
        name="typo_resilience",
        description="User makes typos in flavors and effects — fuzzy matching should handle them.",
        turns=[
            Turn(
                message="show me indica with tropicall flavor and relaxing effects",
                language="en",
                note="Typo: 'tropicall' (extra l) — fuzzy should match 'tropical'",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                )
            ),
            Turn(
                message="something that hlps with insomnia and has citrus tatse",
                language="en",
                note="Typos: 'hlps', 'tatse' — system must still understand query",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
        ]
    ),

    Scenario(
        id=10,
        name="mixed_language_query",
        description="User writes in English but mixes in Spanish cannabis terms.",
        turns=[
            Turn(
                message="I need indica para dormir, something really relaxante",
                language="en",
                note="Mixed EN+ES — should interpret 'dormir'=sleep, 'relaxante'=relaxing",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    min_strains=2,
                    language="en",
                    check_response_mentions_strain=True,
                )
            ),
            Turn(
                message="dame algo with high THC, quiero algo fuerte",
                language="es",
                note="Switched to ES — 'fuerte'=strong → high THC",
                expectation=TurnExpectation(
                    is_search=True,
                    expect_strains=True,
                    language="es",
                )
            ),
        ]
    ),
]


# ─────────────────────────────────────────────────────────────────
# API CLIENT
# ─────────────────────────────────────────────────────────────────

def ask(message: str, language: str, session_id: Optional[str] = None) -> tuple[Dict, float]:
    """Send query to /ask/, return (response_dict, latency_ms)."""
    payload = {"message": message, "language": language}
    if session_id:
        payload["session_id"] = session_id
    t0 = time.perf_counter()
    try:
        resp = requests.post(ASK_URL, json=payload, timeout=60)
        latency = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        return resp.json(), latency
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        return {"error": str(e)}, latency


# ─────────────────────────────────────────────────────────────────
# RULE CHECKER
# ─────────────────────────────────────────────────────────────────

def run_rule_checks(data: Dict, turn: Turn) -> Dict[str, bool]:
    exp = turn.expectation
    checks: Dict[str, bool] = {}

    if "error" in data:
        checks["api_ok"] = False
        return checks

    checks["api_ok"] = True

    strains = data.get("recommended_strains", [])
    filters = data.get("filters_applied", {}) or {}
    response_text = (data.get("response") or "").lower()
    lang = (data.get("language") or "").lower()

    if exp.is_search is not None:
        is_search = filters.get("is_search_query", None)
        if is_search is None:
            # infer from strains presence
            is_search = len(strains) > 0
        checks["is_search_query"] = (is_search == exp.is_search)

    if exp.expect_strains is True:
        checks["has_strains"] = len(strains) > 0
    elif exp.expect_strains is False:
        checks["no_strains"] = len(strains) == 0

    if exp.min_strains > 0:
        checks[f"min_{exp.min_strains}_strains"] = len(strains) >= exp.min_strains

    if exp.language is not None:
        checks["correct_language"] = lang == exp.language

    if exp.category is not None:
        cat = filters.get("category")
        checks["category_filter"] = cat == exp.category

    if exp.is_follow_up is not None:
        is_fu = filters.get("is_follow_up", False)
        checks["is_follow_up"] = (bool(is_fu) == exp.is_follow_up)

    if exp.check_response_mentions_strain and strains:
        strain_names = [s.get("name", "").lower() for s in strains]  # check all returned strains
        mentions = any(name in response_text for name in strain_names if name)
        checks["response_mentions_strain"] = mentions

    for must_have in exp.response_must_contain:
        checks[f"contains_{must_have[:20]}"] = must_have.lower() in response_text

    for must_not in exp.response_must_not_contain:
        checks[f"not_contains_{must_not[:20]}"] = must_not.lower() not in response_text

    return checks


# ─────────────────────────────────────────────────────────────────
# LLM JUDGE
# ─────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are an expert evaluator of cannabis recommendation AI systems.
You score chatbot responses on 5 dimensions, each 1-5:

1 = Very poor / completely wrong
2 = Poor / mostly wrong
3 = Acceptable / partially correct
4 = Good / mostly correct
5 = Excellent / fully correct

Dimensions:
- relevance: Do the recommended strains actually match what the user asked for? (If no strains: is declining correct?)
- language: Is the response in the correct language requested? Is it consistent throughout?
- helpfulness: Does the response actually help the user make a decision? Is it informative?
- naturalness: Does it sound like a real knowledgeable budtender? Conversational, not robotic?
- accuracy: Does the response correctly mention/describe the actual strain names that were returned?

Return ONLY valid JSON:
{"relevance": N, "language": N, "helpfulness": N, "naturalness": N, "accuracy": N, "reasoning": "one sentence"}
"""

def judge_response(
    user_message: str,
    user_language: str,
    response_text: str,
    strains: List[Dict],
    openai_api_key: str
) -> tuple[Dict[str, int], str]:
    """Use OpenAI to judge quality. Returns (scores_dict, reasoning)."""
    strain_summary = ", ".join(
        f"{s.get('name')} ({s.get('category')}, {s.get('thc')}% THC)"
        for s in strains[:5]
    ) if strains else "none"

    user_prompt = f"""User query (language={user_language}): "{user_message}"
Recommended strains: {strain_summary}
Bot response: "{response_text[:600]}"

Score this response on all 5 dimensions."""

    try:
        import urllib.request
        import urllib.error

        body = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 200,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            content = result["choices"][0]["message"]["content"].strip()
            # extract JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            parsed = json.loads(content[start:end])
            scores = {k: int(v) for k, v in parsed.items() if k != "reasoning"}
            reasoning = parsed.get("reasoning", "")
            return scores, reasoning

    except Exception as e:
        return {}, f"Judge error: {e}"


# ─────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────

def run_scenario(
    scenario: Scenario,
    openai_api_key: Optional[str],
    verbose: bool = False
) -> ScenarioResult:
    session_id = None
    turn_results: List[TurnResult] = []

    for i, turn in enumerate(scenario.turns):
        data, latency = ask(turn.message, turn.language, session_id)

        # carry session forward
        if not session_id and "session_id" in data:
            session_id = data.get("session_id")

        rule_checks = run_rule_checks(data, turn)

        quality_scores: Dict[str, int] = {}
        quality_reasoning = ""
        if openai_api_key and "error" not in data:
            response_text = data.get("response", "")
            strains = data.get("recommended_strains", [])
            if response_text:
                quality_scores, quality_reasoning = judge_response(
                    turn.message, turn.language, response_text, strains, openai_api_key
                )

        tr = TurnResult(
            turn_idx=i + 1,
            message=turn.message,
            language=turn.language,
            note=turn.note,
            response_data=data,
            rule_checks=rule_checks,
            quality_scores=quality_scores,
            quality_reasoning=quality_reasoning,
            latency_ms=latency,
        )
        turn_results.append(tr)

        if verbose and "error" not in data:
            resp_preview = (data.get("response") or "")[:120]
            print(f"    Response: {resp_preview}...")
            strains = data.get("recommended_strains", [])
            if strains:
                names = [s.get("name") for s in strains[:5]]
                print(f"    Strains:  {names}")

    return ScenarioResult(scenario=scenario, turn_results=turn_results)


# ─────────────────────────────────────────────────────────────────
# PRINTER
# ─────────────────────────────────────────────────────────────────

SCORE_COLORS = {5: Fore.GREEN, 4: Fore.GREEN, 3: Fore.YELLOW, 2: Fore.RED, 1: Fore.RED}

def score_color(s: int) -> str:
    return SCORE_COLORS.get(s, Fore.WHITE)

def print_scenario_result(sr: ScenarioResult, verbose: bool = False):
    status = f"{Fore.GREEN}PASS{Style.RESET_ALL}" if sr.all_rules_passed else f"{Fore.RED}FAIL{Style.RESET_ALL}"
    q = f"{sr.avg_quality:.1f}/5.0" if sr.avg_quality > 0 else "n/a"
    q_color = Fore.GREEN if sr.avg_quality >= 4.0 else (Fore.YELLOW if sr.avg_quality >= 3.0 else Fore.RED)

    print(f"\n  [{sr.scenario.id:2d}] {sr.scenario.name:<30} Rules:{status}  Quality:{q_color}{q}{Style.RESET_ALL}")
    print(f"       {Fore.WHITE}{sr.scenario.description}{Style.RESET_ALL}")

    for tr in sr.turn_results:
        rule_icon = f"{Fore.GREEN}✓{Style.RESET_ALL}" if tr.rule_passed else f"{Fore.RED}✗{Style.RESET_ALL}"
        failed_checks = [k for k, v in tr.rule_checks.items() if not v]
        fail_str = f"  {Fore.RED}[{', '.join(failed_checks)}]{Style.RESET_ALL}" if failed_checks else ""
        q_str = ""
        if tr.quality_scores:
            scores_fmt = " ".join(
                f"{k[0].upper()}:{score_color(v)}{v}{Style.RESET_ALL}"
                for k, v in tr.quality_scores.items()
                if k != "reasoning"
            )
            q_str = f"  [{scores_fmt}]"

        print(f"       Turn {tr.turn_idx} {rule_icon} {tr.latency_ms:6.0f}ms  \"{tr.message[:55]}\"")
        print(f"              {Fore.YELLOW}{tr.note}{Style.RESET_ALL}{fail_str}{q_str}")
        if tr.quality_reasoning and verbose:
            print(f"              {Fore.CYAN}Judge: {tr.quality_reasoning}{Style.RESET_ALL}")


def print_report(results: List[ScenarioResult], with_judge: bool):
    total_turns = sum(len(sr.turn_results) for sr in results)
    total_rules = sum(
        sum(len(tr.rule_checks) for tr in sr.turn_results)
        for sr in results
    )
    passed_rules = sum(
        sum(sum(1 for v in tr.rule_checks.values() if v) for tr in sr.turn_results)
        for sr in results
    )
    scenarios_passed = sum(1 for sr in results if sr.all_rules_passed)

    scored = [sr for sr in results if sr.avg_quality > 0]
    avg_quality_overall = sum(sr.avg_quality for sr in scored) / len(scored) if scored else 0

    print(f"\n{Fore.CYAN}{'═'*72}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'QUALITY EVALUATION REPORT'.center(72)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═'*72}{Style.RESET_ALL}")
    print()
    print(f"  Scenarios : {scenarios_passed}/{len(results)} passed all rule checks")
    print(f"  Rule checks: {passed_rules}/{total_rules} passed ({passed_rules/total_rules*100:.0f}%)")
    print(f"  Total turns: {total_turns}")
    if with_judge and avg_quality_overall > 0:
        q_color = Fore.GREEN if avg_quality_overall >= 4.0 else (Fore.YELLOW if avg_quality_overall >= 3.0 else Fore.RED)
        print(f"  LLM quality: {q_color}{avg_quality_overall:.2f}/5.0{Style.RESET_ALL}", end="")
        if avg_quality_overall >= 4.0:
            print(f"  {Fore.GREEN}(Good){Style.RESET_ALL}")
        elif avg_quality_overall >= 3.0:
            print(f"  {Fore.YELLOW}(Acceptable){Style.RESET_ALL}")
        else:
            print(f"  {Fore.RED}(Needs improvement){Style.RESET_ALL}")

    # Per-dimension averages
    if with_judge and scored:
        all_scores: Dict[str, List[int]] = {}
        for sr in scored:
            for tr in sr.turn_results:
                for dim, val in tr.quality_scores.items():
                    all_scores.setdefault(dim, []).append(val)
        if all_scores:
            print()
            print(f"  Quality breakdown:")
            for dim, vals in sorted(all_scores.items()):
                avg = sum(vals) / len(vals)
                bar_filled = int(avg)
                bar = "█" * bar_filled + "░" * (5 - bar_filled)
                color = Fore.GREEN if avg >= 4.0 else (Fore.YELLOW if avg >= 3.0 else Fore.RED)
                print(f"    {dim:<14} {color}{bar}  {avg:.2f}{Style.RESET_ALL}")

    # Failed scenarios
    failed = [sr for sr in results if not sr.all_rules_passed]
    if failed:
        print()
        print(f"  {Fore.RED}Failed scenarios:{Style.RESET_ALL}")
        for sr in failed:
            failed_turns = [tr for tr in sr.turn_results if not tr.rule_passed]
            for tr in failed_turns:
                bad = [k for k, v in tr.rule_checks.items() if not v]
                print(f"    #{sr.scenario.id} {sr.scenario.name} | Turn {tr.turn_idx}: {bad}")

    print()
    if scenarios_passed == len(results):
        print(f"{Fore.GREEN}{'✓ ALL SCENARIOS PASSED RULE CHECKS'.center(72)}{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}{'✗ SOME SCENARIOS FAILED'.center(72)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'═'*72}{Style.RESET_ALL}")
    print()


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Conversation quality evaluation")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge scoring")
    parser.add_argument("--scenario", type=int, default=0, help="Run only scenario N (0=all)")
    parser.add_argument("--verbose", action="store_true", help="Show response previews and judge reasoning")
    args = parser.parse_args()

    openai_api_key = None if args.no_judge else os.getenv("OPENAI_API_KEY")
    with_judge = bool(openai_api_key)

    print(f"\n{Fore.MAGENTA}{'*'*72}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'CANAGENT — CONVERSATION QUALITY EVALUATION'.center(72)}{Style.RESET_ALL}")
    judge_status = "with LLM judge" if with_judge else "rule-based only (--no-judge)"
    print(f"{Fore.MAGENTA}{judge_status.center(72)}{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{'*'*72}{Style.RESET_ALL}")

    # Check API
    try:
        requests.get(f"{API_BASE}/api/v1/ping/", timeout=5).raise_for_status()
        print(f"\n{Fore.GREEN}✓ API reachable{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}✗ API not reachable: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Run: docker compose up -d{Style.RESET_ALL}")
        sys.exit(1)

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in SCENARIOS if s.id == args.scenario]
        if not scenarios:
            print(f"{Fore.RED}Scenario {args.scenario} not found{Style.RESET_ALL}")
            sys.exit(1)

    print(f"  Scenarios: {len(scenarios)}  |  Turns: {sum(len(s.turns) for s in scenarios)}\n")

    results: List[ScenarioResult] = []
    for scenario in scenarios:
        print(f"  {Fore.BLUE}Running scenario {scenario.id}: {scenario.name}...{Style.RESET_ALL}")
        sr = run_scenario(scenario, openai_api_key, verbose=args.verbose)
        results.append(sr)
        print_scenario_result(sr, verbose=args.verbose)
        time.sleep(0.5)  # avoid rate limits between scenarios

    print_report(results, with_judge)

    all_passed = all(sr.all_rules_passed for sr in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
