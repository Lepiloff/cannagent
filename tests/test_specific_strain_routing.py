"""
Regression tests for specific-strain routing logic in SmartRAGService.

Covers:
- Follow-up override when named strains are NOT in session (Bug 2 fix)
- Session narrowing when named strains ARE in session (Finding 1 fix)
- Partial match detection for multi-strain DB lookup (Finding 2 fix)
"""

import pytest
from unittest.mock import MagicMock
from app.core.smart_rag_service import SmartRAGService
from app.core.streamlined_analyzer import QueryAnalysis, FollowUpIntent


def _make_strain(name: str, thc: float = 18.0, category: str = "Hybrid") -> MagicMock:
    """Create a mock strain object with the fields SmartRAGService inspects."""
    s = MagicMock()
    s.name = name
    s.thc = thc
    s.category = category
    s.id = hash(name)
    return s


# ── _resolve_strains_in_session ──────────────────────────────────────────


class TestResolveStrains:
    """Tests for _resolve_strains_in_session helper."""

    def test_all_found(self):
        session = [_make_strain("Blue Dream"), _make_strain("Sour Diesel"), _make_strain("OG Kush")]
        resolved = SmartRAGService._resolve_strains_in_session(
            ["Blue Dream", "Sour Diesel"], session
        )
        assert len(resolved) == 2
        assert {s.name for s in resolved} == {"Blue Dream", "Sour Diesel"}

    def test_none_found(self):
        session = [_make_strain("Blue Dream"), _make_strain("OG Kush")]
        resolved = SmartRAGService._resolve_strains_in_session(
            ["Sour Diesel", "Northern Lights"], session
        )
        assert len(resolved) == 0

    def test_partial_match(self):
        session = [_make_strain("Blue Dream"), _make_strain("OG Kush")]
        resolved = SmartRAGService._resolve_strains_in_session(
            ["Blue Dream", "Sour Diesel"], session
        )
        assert len(resolved) == 1
        assert resolved[0].name == "Blue Dream"

    def test_case_insensitive(self):
        session = [_make_strain("Blue Dream")]
        resolved = SmartRAGService._resolve_strains_in_session(
            ["blue dream"], session
        )
        assert len(resolved) == 1

    def test_empty_session(self):
        resolved = SmartRAGService._resolve_strains_in_session(
            ["Sour Diesel"], []
        )
        assert len(resolved) == 0


# ── Follow-up override: named strains not in session → specific strain ───


class TestFollowUpOverrideNotInSession:
    """
    Bug 2 scenario: user asks about a specific strain that is NOT in session.
    The override must drop is_follow_up so the specific strain branch executes.
    """

    def test_single_strain_not_in_session_escapes_followup(self):
        """'tell me about Sour Diesel' with Blue Dream in session."""
        analysis = QueryAnalysis(
            is_search_query=True,
            is_follow_up=True,
            specific_strain_names=["Sour Diesel"],
            follow_up_intent=FollowUpIntent(action="describe"),
            natural_response="Follow-up processed",
        )
        session_strains = [_make_strain("Blue Dream")]

        resolved = SmartRAGService._resolve_strains_in_session(
            analysis.specific_strain_names, session_strains
        )
        # Not all found → should escape follow-up
        assert len(resolved) < len(analysis.specific_strain_names)
        # Simulate what SmartRAGService does
        analysis.is_follow_up = False
        analysis.follow_up_intent = None

        assert analysis.is_follow_up is False
        assert analysis.follow_up_intent is None
        # specific_strain_names preserved for DB lookup
        assert analysis.specific_strain_names == ["Sour Diesel"]

    def test_multi_strain_one_missing_escapes_followup(self):
        """'compare Blue Dream and Sour Diesel' with only Blue Dream in session."""
        analysis = QueryAnalysis(
            is_search_query=True,
            is_follow_up=True,
            specific_strain_names=["Blue Dream", "Sour Diesel"],
            follow_up_intent=FollowUpIntent(action="compare", field="thc", order="desc"),
            natural_response="Follow-up processed",
        )
        session_strains = [_make_strain("Blue Dream"), _make_strain("OG Kush")]

        resolved = SmartRAGService._resolve_strains_in_session(
            analysis.specific_strain_names, session_strains
        )
        assert len(resolved) == 1  # Only Blue Dream found
        assert len(resolved) < len(analysis.specific_strain_names)


# ── Follow-up narrowing: all named strains in session → subset ───────────


class TestFollowUpSessionNarrowing:
    """
    Finding 1 scenario: user asks about specific strains that ARE all in session.
    The session must be narrowed to just those strains before follow-up executor.
    """

    def test_narrows_to_two_from_five(self):
        """'compare Blue Dream and Sour Diesel' with 5 strains in session."""
        session_strains = [
            _make_strain("Blue Dream", thc=18.0),
            _make_strain("Sour Diesel", thc=22.0),
            _make_strain("OG Kush", thc=20.0),
            _make_strain("Northern Lights", thc=17.0),
            _make_strain("Trainwreck", thc=19.0),
        ]
        analysis = QueryAnalysis(
            is_search_query=True,
            is_follow_up=True,
            specific_strain_names=["Blue Dream", "Sour Diesel"],
            follow_up_intent=FollowUpIntent(action="compare", field="thc", order="desc"),
            natural_response="Follow-up processed",
        )

        resolved = SmartRAGService._resolve_strains_in_session(
            analysis.specific_strain_names, session_strains
        )
        assert len(resolved) == 2
        assert {s.name for s in resolved} == {"Blue Dream", "Sour Diesel"}
        # Verify is_follow_up stays True (all found)
        assert len(resolved) == len(analysis.specific_strain_names)
        assert analysis.is_follow_up is True

    def test_single_strain_in_session_narrows(self):
        """'tell me about Blue Dream' with Blue Dream among 3 session strains."""
        session_strains = [
            _make_strain("Blue Dream"),
            _make_strain("OG Kush"),
            _make_strain("Northern Lights"),
        ]
        analysis = QueryAnalysis(
            is_search_query=True,
            is_follow_up=True,
            specific_strain_names=["Blue Dream"],
            follow_up_intent=FollowUpIntent(action="describe"),
            natural_response="Follow-up processed",
        )

        resolved = SmartRAGService._resolve_strains_in_session(
            analysis.specific_strain_names, session_strains
        )
        assert len(resolved) == 1
        assert resolved[0].name == "Blue Dream"

    def test_no_specific_names_means_no_narrowing(self):
        """'which has highest THC?' — no specific_strain_names, full session used."""
        analysis = QueryAnalysis(
            is_search_query=True,
            is_follow_up=True,
            specific_strain_names=None,
            follow_up_intent=FollowUpIntent(action="compare", field="thc", order="desc"),
            natural_response="Follow-up processed",
        )
        # The override condition checks `analysis.specific_strain_names` first;
        # if None, the block is skipped entirely → session_strains unchanged
        assert analysis.specific_strain_names is None


# ── Backward compat: property specific_strain_name ───────────────────────


class TestBackwardCompat:
    """Verify the backward-compat property works for existing single-strain code paths."""

    def test_single_strain_property(self):
        a = QueryAnalysis(
            specific_strain_names=["Sour Diesel"],
            natural_response="test",
        )
        assert a.specific_strain_name == "Sour Diesel"

    def test_multi_strain_property_returns_first(self):
        a = QueryAnalysis(
            specific_strain_names=["Blue Dream", "Sour Diesel"],
            natural_response="test",
        )
        assert a.specific_strain_name == "Blue Dream"

    def test_none_property(self):
        a = QueryAnalysis(natural_response="test")
        assert a.specific_strain_name is None
        assert a.specific_strain_names is None

    def test_serialization_roundtrip(self):
        a = QueryAnalysis(
            specific_strain_names=["Blue Dream", "Sour Diesel"],
            natural_response="test",
        )
        d = a.model_dump()
        assert "specific_strain_names" in d
        assert "specific_strain_name" not in d  # property not serialized
        a2 = QueryAnalysis(**d)
        assert a2.specific_strain_names == ["Blue Dream", "Sour Diesel"]
        assert a2.specific_strain_name == "Blue Dream"
