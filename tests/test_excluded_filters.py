"""Unit tests for excluded_feelings / excluded_flavors handling.

Covers:
- QueryAnalysis schema accepts the new fields and defaults to None
- SmartRAGService._violates_excludes detects strains carrying excluded items
- SmartRAGService._apply_soft_exclude_post_filter drops violators and tops up
  from a wider re-fetch when results would otherwise drop below target_count
- Pass-through behavior when no excludes are present (no extra DB calls)
"""

from types import SimpleNamespace

import pytest

from app.core.smart_rag_service import SmartRAGService
from app.core.streamlined_analyzer import QueryAnalysis


# ---------------------------------------------------------------------------
# Fixtures: lightweight strain stand-ins
# ---------------------------------------------------------------------------

def _strain(strain_id, name, feelings=(), flavors=()):
    return SimpleNamespace(
        id=strain_id,
        name=name,
        feelings=[SimpleNamespace(name=n) for n in feelings],
        flavors=[SimpleNamespace(name=n) for n in flavors],
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
