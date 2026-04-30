"""Unit tests for excluded_feelings / excluded_flavors handling.

Covers:
- QueryAnalysis schema accepts the new fields and defaults to None
- SmartRAGService._violates_excludes detects strains carrying excluded items
  across all localized name columns (name / name_en / name_es)
- SmartRAGService._apply_soft_exclude_post_filter drops violators and tops up
  from a wider re-fetch when results would otherwise drop below target_count
- Pass-through behavior when no excludes are present (no extra DB calls)
- Regression: streaming follow-up override and last_search_context round-trip
  honor the new excluded_* fields
"""

from types import SimpleNamespace

import pytest

from app.core.smart_rag_service import SmartRAGService
from app.core.streamlined_analyzer import QueryAnalysis


# ---------------------------------------------------------------------------
# Fixtures: lightweight strain stand-ins
# ---------------------------------------------------------------------------

def _taxonomy_item(name=None, name_en=None, name_es=None):
    """Stand-in for Feeling/Flavor ORM rows. Localized columns optional."""
    return SimpleNamespace(name=name, name_en=name_en, name_es=name_es)


def _strain(strain_id, name, feelings=(), flavors=()):
    """`feelings` / `flavors` may be plain strings (→ name only) or
    `_taxonomy_item(...)` for explicit localized columns."""
    def _to_item(x):
        if isinstance(x, str) or x is None:
            return _taxonomy_item(name=x)
        return x

    return SimpleNamespace(
        id=strain_id,
        name=name,
        feelings=[_to_item(f) for f in feelings],
        flavors=[_to_item(f) for f in flavors],
    )


def _analysis(**kwargs):
    """Build a minimal QueryAnalysis with `natural_response` and given kwargs."""
    return QueryAnalysis(natural_response=".", **kwargs)


# ---------------------------------------------------------------------------
# QueryAnalysis schema
# ---------------------------------------------------------------------------

def test_query_analysis_defaults_excludes_to_none():
    a = _analysis()
    assert a.excluded_feelings is None
    assert a.excluded_flavors is None


def test_query_analysis_accepts_excluded_lists():
    a = _analysis(excluded_feelings=["sleepy"], excluded_flavors=["earthy"])
    assert a.excluded_feelings == ["sleepy"]
    assert a.excluded_flavors == ["earthy"]


# ---------------------------------------------------------------------------
# _violates_excludes
# ---------------------------------------------------------------------------

def test_violates_excludes_returns_false_with_no_lists():
    s = _strain(1, "Foo", feelings=("Sleepy",))
    assert SmartRAGService._violates_excludes(s, [], []) is False


def test_violates_excludes_detects_feeling_match():
    s = _strain(1, "Foo", feelings=("Sleepy", "Relaxed"))
    assert SmartRAGService._violates_excludes(s, ["sleepy"], []) is True


def test_violates_excludes_case_insensitive():
    s = _strain(1, "Foo", feelings=("SLEEPY",))
    assert SmartRAGService._violates_excludes(s, ["Sleepy"], []) is True


def test_violates_excludes_substring_either_direction():
    # User wrote "sleep", strain has "Sleepy" — substring match should still trigger.
    s = _strain(1, "Foo", feelings=("Sleepy",))
    assert SmartRAGService._violates_excludes(s, ["sleep"], []) is True


def test_violates_excludes_detects_flavor_match():
    s = _strain(1, "Foo", flavors=("earthy", "pine"))
    assert SmartRAGService._violates_excludes(s, [], ["earthy"]) is True


def test_violates_excludes_matches_via_name_es_when_canonical_does_not():
    """Spanish-only analyzer extraction must still match a strain whose canonical
    `name` is the English form. Mirrors the SQL filter's name_en/name_es/name OR."""
    feeling = _taxonomy_item(name="Sleepy", name_en="Sleepy", name_es="Somnoliento")
    s = SimpleNamespace(id=1, name="Foo", feelings=[feeling], flavors=[])
    assert SmartRAGService._violates_excludes(s, ["somnoliento"], []) is True


def test_violates_excludes_matches_via_name_en_when_canonical_is_spanish():
    """Symmetric case: canonical name is Spanish, user input is English."""
    flavor = _taxonomy_item(name="cítrico", name_en="citrus", name_es="cítrico")
    s = SimpleNamespace(id=1, name="Foo", feelings=[], flavors=[flavor])
    assert SmartRAGService._violates_excludes(s, [], ["citrus"]) is True


def test_violates_excludes_with_only_name_column_still_works():
    """Backward compat: tags exposing only `name` (no localized columns) match."""
    feeling = SimpleNamespace(name="Sleepy")  # no name_en / name_es attrs at all
    s = SimpleNamespace(id=1, name="Foo", feelings=[feeling], flavors=[])
    assert SmartRAGService._violates_excludes(s, ["sleepy"], []) is True


def test_violates_excludes_returns_false_when_no_overlap():
    s = _strain(1, "Foo", feelings=("Relaxed",), flavors=("citrus",))
    assert SmartRAGService._violates_excludes(s, ["sleepy"], ["earthy"]) is False


def test_violates_excludes_handles_empty_relationships():
    s = _strain(1, "Foo", feelings=(), flavors=())
    assert SmartRAGService._violates_excludes(s, ["sleepy"], ["earthy"]) is False


def test_violates_excludes_handles_none_name():
    s = SimpleNamespace(
        id=1, name="X",
        feelings=[SimpleNamespace(name=None)],
        flavors=[],
    )
    assert SmartRAGService._violates_excludes(s, ["sleepy"], []) is False


# ---------------------------------------------------------------------------
# _apply_soft_exclude_post_filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_filter_passthrough_when_no_excludes():
    """No excludes → input is returned untouched, no DB activity."""
    svc = SmartRAGService(repository=None)
    a = _analysis()
    strains = [_strain(i, f"S{i}") for i in range(5)]

    async def _fail_run_db(*args, **kw):
        raise AssertionError("run_db should not be called when there are no excludes")

    out = await svc._apply_soft_exclude_post_filter(
        result_strains=strains,
        candidates=strains * 4,
        analysis=a,
        run_db=_fail_run_db,
        db_svc=svc,
        query_embedding=None,
    )
    assert out == strains


@pytest.mark.asyncio
async def test_post_filter_drops_violators_and_does_not_refetch_when_query_embedding_missing():
    svc = SmartRAGService(repository=None)
    a = _analysis(excluded_feelings=["sleepy"])
    s_clean = [_strain(i, f"C{i}", feelings=("Relaxed",)) for i in range(3)]
    s_violators = [_strain(99 + i, f"V{i}", feelings=("Sleepy",)) for i in range(2)]
    initial = s_clean + s_violators  # 5 total, 2 violate

    async def _run_db_unused(*a, **kw):
        raise AssertionError("should not refetch when query_embedding=None")

    out = await svc._apply_soft_exclude_post_filter(
        result_strains=initial,
        candidates=initial,
        analysis=a,
        run_db=_run_db_unused,
        db_svc=svc,
        query_embedding=None,
        target_count=5,
    )
    assert {s.name for s in out} == {"C0", "C1", "C2"}


@pytest.mark.asyncio
async def test_post_filter_tops_up_from_wider_pool():
    """If filtered count drops below target, wider re-fetch tops up cleanly."""
    svc = SmartRAGService(repository=None)
    a = _analysis(excluded_feelings=["sleepy"])

    s_clean_initial = [_strain(i, f"C{i}", feelings=("Relaxed",)) for i in range(2)]
    s_violators_initial = [_strain(99 + i, f"V{i}", feelings=("Sleepy",)) for i in range(3)]
    initial = s_clean_initial + s_violators_initial  # 5; 2 clean

    # Wider pool returns 20 strains: original 5 + 15 extra (10 clean, 5 violators).
    extra_clean = [_strain(200 + i, f"E{i}", feelings=("Energetic",)) for i in range(10)]
    extra_violator = [_strain(300 + i, f"X{i}", feelings=("Sleepy",)) for i in range(5)]
    wider = initial + extra_clean + extra_violator

    refetch_calls = {"count": 0, "limit": None}

    async def _run_db(fn, *args, **kw):
        # Mimic run_db wrapping a sync call.
        refetch_calls["count"] += 1
        # Last positional arg in _search_with_embedding is `limit`.
        refetch_calls["limit"] = args[-1] if args else kw.get("limit")
        return wider

    fake_db_svc = SimpleNamespace(
        vector_search=SimpleNamespace(_search_with_embedding=lambda *a, **kw: wider)
    )

    out = await svc._apply_soft_exclude_post_filter(
        result_strains=initial,
        candidates=wider,
        analysis=a,
        run_db=_run_db,
        db_svc=fake_db_svc,
        query_embedding=[0.1] * 8,
        target_count=5,
        wider_pool_size=20,
    )

    assert len(out) == 5
    assert all(
        not any("sleepy" in (f.name or "").lower() for f in s.feelings)
        for s in out
    )
    # Should preserve original clean strains and add 3 from wider pool.
    assert {"C0", "C1"} <= {s.name for s in out}
    # Re-fetch happened once with wider_pool_size limit.
    assert refetch_calls["count"] == 1
    assert refetch_calls["limit"] == 20


@pytest.mark.asyncio
async def test_post_filter_accepts_fewer_when_pool_exhausted():
    """If wider pool can't supply enough clean strains, accept smaller result set."""
    svc = SmartRAGService(repository=None)
    a = _analysis(excluded_feelings=["sleepy"])
    initial = [_strain(i, f"V{i}", feelings=("Sleepy",)) for i in range(5)]
    # Wider pool also has only sleepy strains.
    wider = initial + [_strain(99 + i, f"W{i}", feelings=("Sleepy",)) for i in range(10)]

    async def _run_db(fn, *args, **kw):
        return wider

    fake_db_svc = SimpleNamespace(
        vector_search=SimpleNamespace(_search_with_embedding=lambda *a, **kw: wider)
    )

    out = await svc._apply_soft_exclude_post_filter(
        result_strains=initial,
        candidates=wider,
        analysis=a,
        run_db=_run_db,
        db_svc=fake_db_svc,
        query_embedding=[0.1] * 4,
        target_count=5,
    )
    assert out == []


@pytest.mark.asyncio
async def test_post_filter_handles_refetch_failure_gracefully():
    """If wider re-fetch raises, return what we have without propagating."""
    svc = SmartRAGService(repository=None)
    a = _analysis(excluded_feelings=["sleepy"])
    initial = [
        _strain(1, "C0", feelings=("Relaxed",)),
        _strain(2, "V0", feelings=("Sleepy",)),
    ]

    async def _run_db_raises(*args, **kw):
        raise RuntimeError("DB blew up")

    fake_db_svc = SimpleNamespace(vector_search=SimpleNamespace(_search_with_embedding=None))

    out = await svc._apply_soft_exclude_post_filter(
        result_strains=initial,
        candidates=[_strain(3, "X")],
        analysis=a,
        run_db=_run_db_raises,
        db_svc=fake_db_svc,
        query_embedding=[0.1, 0.2],
        target_count=5,
    )
    assert [s.name for s in out] == ["C0"]


@pytest.mark.asyncio
async def test_post_filter_excluded_flavors_path():
    svc = SmartRAGService(repository=None)
    a = _analysis(excluded_flavors=["earthy"])
    initial = [
        _strain(1, "Citrus Strain", flavors=("citrus", "lemon")),
        _strain(2, "Earthy Strain", flavors=("earthy",)),
        _strain(3, "Pine Strain", flavors=("pine",)),
    ]
    fake_db_svc = SimpleNamespace(vector_search=SimpleNamespace(_search_with_embedding=None))

    out = await svc._apply_soft_exclude_post_filter(
        result_strains=initial,
        candidates=initial,
        analysis=a,
        run_db=None,
        db_svc=fake_db_svc,
        query_embedding=None,
        target_count=5,
    )
    assert {s.name for s in out} == {"Citrus Strain", "Pine Strain"}


# ---------------------------------------------------------------------------
# _introduces_new_search_criteria — review fix #1: streaming/blocking parity
# ---------------------------------------------------------------------------

def test_introduces_new_search_criteria_false_when_empty():
    a = _analysis()
    assert SmartRAGService._introduces_new_search_criteria(a) is False


def test_introduces_new_search_criteria_true_for_each_field():
    """Each of these fields independently must trigger the override."""
    fields = [
        "required_effects", "required_flavors", "required_terpenes",
        "required_helps_with", "exclude_negatives",
        "excluded_feelings", "excluded_flavors",
    ]
    for f in fields:
        a = _analysis(**{f: ["x"]})
        assert SmartRAGService._introduces_new_search_criteria(a) is True, (
            f"override should fire on {f!r}-only payload"
        )


def test_introduces_new_search_criteria_excluded_feelings_alone_is_enough():
    """Direct review-finding regression: streaming used to skip excluded_feelings."""
    a = _analysis(excluded_feelings=["sleepy"])
    assert SmartRAGService._introduces_new_search_criteria(a) is True


def test_introduces_new_search_criteria_excluded_flavors_alone_is_enough():
    a = _analysis(excluded_flavors=["earthy"])
    assert SmartRAGService._introduces_new_search_criteria(a) is True


def test_introduces_new_search_criteria_ignores_thc_level_and_category():
    """THC/CBD/category alone should NOT force a new search — they can persist
    across follow-ups. Only attribute-style criteria flip the override."""
    a = _analysis(thc_level="high", cbd_level="low", detected_category="Indica")
    assert SmartRAGService._introduces_new_search_criteria(a) is False


# ---------------------------------------------------------------------------
# _inherit_search_context_into — review fix #2: round-trip excludes
# ---------------------------------------------------------------------------

def test_inherit_copies_positive_criteria_from_ctx():
    a = _analysis()
    ctx = {
        "detected_category": "Indica",
        "required_helps_with": ["pain"],
        "required_effects": ["relaxed"],
        "required_flavors": ["tropical"],
        "required_terpenes": ["myrcene"],
        "thc_level": "high",
        "cbd_level": "low",
    }
    SmartRAGService._inherit_search_context_into(a, ctx)
    assert a.detected_category == "Indica"
    assert a.required_helps_with == ["pain"]
    assert a.required_effects == ["relaxed"]
    assert a.required_flavors == ["tropical"]
    assert a.required_terpenes == ["myrcene"]
    assert a.thc_level == "high"
    assert a.cbd_level == "low"


def test_inherit_copies_excluded_when_analysis_has_none():
    a = _analysis()
    ctx = {
        "exclude_negatives": ["paranoia"],
        "excluded_feelings": ["sleepy"],
        "excluded_flavors": ["earthy"],
    }
    SmartRAGService._inherit_search_context_into(a, ctx)
    assert a.exclude_negatives == ["paranoia"]
    assert a.excluded_feelings == ["sleepy"]
    assert a.excluded_flavors == ["earthy"]


def test_inherit_preserves_user_supplied_excluded_when_present():
    """User explicitly added new excludes this turn — they must not be overwritten."""
    a = _analysis(
        excluded_feelings=["hungry"],
        excluded_flavors=["diesel"],
        exclude_negatives=["dizzy"],
    )
    ctx = {
        "exclude_negatives": ["paranoia"],
        "excluded_feelings": ["sleepy"],
        "excluded_flavors": ["earthy"],
    }
    SmartRAGService._inherit_search_context_into(a, ctx)
    assert a.excluded_feelings == ["hungry"]
    assert a.excluded_flavors == ["diesel"]
    assert a.exclude_negatives == ["dizzy"]


def test_inherit_no_op_when_ctx_keys_missing():
    a = _analysis()
    SmartRAGService._inherit_search_context_into(a, {})
    assert a.detected_category is None
    assert a.required_helps_with is None
    assert a.excluded_feelings is None


# ---------------------------------------------------------------------------
# _update_session_streamlined — review fix #2: save excludes into session ctx
# ---------------------------------------------------------------------------

def test_update_session_persists_excluded_fields_into_last_search_context():
    """End-to-end save: session.last_search_context must round-trip excluded_*."""
    from app.models.session import ConversationSession

    svc = SmartRAGService(repository=None)
    session = ConversationSession(session_id="t-1")

    a = _analysis(
        is_search_query=True,
        detected_category="Indica",
        required_effects=["relaxed"],
        excluded_feelings=["sleepy"],
        excluded_flavors=["earthy"],
        exclude_negatives=["paranoia"],
        thc_level="high",
    )
    # Need at least one strain so save runs (gate at line ~1845).
    strains = [SimpleNamespace(id=42, name="Some Strain")]

    svc._update_session_streamlined(session, "relaxing but not sleepy", a, strains)

    ctx = session.last_search_context
    assert ctx is not None
    assert ctx["detected_category"] == "Indica"
    assert ctx["required_effects"] == ["relaxed"]
    assert ctx["excluded_feelings"] == ["sleepy"]
    assert ctx["excluded_flavors"] == ["earthy"]
    assert ctx["exclude_negatives"] == ["paranoia"]
    assert ctx["thc_level"] == "high"


def test_update_session_skips_save_when_no_strains():
    """No persisted ctx when search returns no strains (existing contract)."""
    from app.models.session import ConversationSession

    svc = SmartRAGService(repository=None)
    session = ConversationSession(session_id="t-2")

    a = _analysis(is_search_query=True, excluded_feelings=["sleepy"])
    svc._update_session_streamlined(session, "q", a, [])

    assert session.last_search_context is None


def test_full_save_inherit_round_trip():
    """Save excludes via _update_session_streamlined; new analysis with no excludes
    should inherit them via _inherit_search_context_into."""
    from app.models.session import ConversationSession

    svc = SmartRAGService(repository=None)
    session = ConversationSession(session_id="t-3")

    first = _analysis(
        is_search_query=True,
        excluded_feelings=["sleepy"],
        excluded_flavors=["earthy"],
    )
    svc._update_session_streamlined(
        session, "relaxing but not sleepy and not earthy", first,
        [SimpleNamespace(id=1, name="Strain")],
    )

    # Second turn: empty analysis (e.g., "more options" recognised by another path).
    second = _analysis(is_search_query=True)
    SmartRAGService._inherit_search_context_into(second, session.last_search_context)
    assert second.excluded_feelings == ["sleepy"]
    assert second.excluded_flavors == ["earthy"]
