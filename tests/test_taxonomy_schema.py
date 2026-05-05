from types import SimpleNamespace

from app.core.taxonomy_aliases import canonical_taxonomy_name
from app.core.smart_rag_service import SmartRAGService
from app.core.streamlined_analyzer import QueryAnalysis
from app.db.repository import StrainRepository
from app.models.database import Negative, Strain, Terpene, strain_other_terpenes_table


def test_terpene_mapping_uses_current_canna_schema():
    assert strain_other_terpenes_table.name == "strains_strain_other_terpenes"
    assert "dominant_terpene_id" in Strain.__table__.c
    assert "is_dominant" not in strain_other_terpenes_table.c


def test_strain_terpenes_property_combines_and_deduplicates_current_relations():
    myrcene = Terpene(id=13, name="Myrcene", description="", translation_status="")
    limonene = Terpene(id=15, name="Limonene", description="", translation_status="")
    strain = Strain(id=1, name="Test", category="Hybrid", dominant_terpene=myrcene)
    strain.other_terpenes = [myrcene, limonene]

    assert [terpene.name for terpene in strain.terpenes] == ["Myrcene", "Limonene"]


def test_taxonomy_aliases_match_canna_cleanup_rules():
    assert canonical_taxonomy_name("Negative", "Anxiety") == "Anxious"
    assert canonical_taxonomy_name("HelpsWith", "Inflamacion") == "Inflamación"
    assert canonical_taxonomy_name("Terpene", "Mirceno (herbal)") == "Myrcene"


def test_repository_lookup_canonicalizes_known_alias_before_querying():
    class FakeQuery:
        condition = None

        def filter(self, condition):
            self.condition = condition
            return self

        def first(self):
            return None

    class FakeDB:
        query_obj = FakeQuery()

        def query(self, model):
            return self.query_obj

    repo = StrainRepository(FakeDB())
    repo._get_taxonomy_by_name(Negative, "Anxiety")

    compiled = str(
        FakeDB.query_obj.condition.compile(compile_kwargs={"literal_binds": True})
    )
    assert "'anxious'" in compiled


def test_terpene_attribute_filter_checks_dominant_and_other_relations(monkeypatch):
    class FakeQuery:
        def __init__(self, db):
            self.db = db
            self.join_key = None

        def join(self, target):
            self.join_key = getattr(target, "key", None)
            self.db.joined_keys.append(self.join_key)
            return self

        def filter(self, *args):
            return self

        def distinct(self):
            return self

        def all(self):
            if self.join_key == "dominant_terpene":
                return [(1,)]
            if self.join_key == "other_terpenes":
                return [(3,)]
            return []

    class FakeDB:
        def __init__(self):
            self.joined_keys = []

        def query(self, *args):
            return FakeQuery(self)

    fake_db = FakeDB()
    svc = SmartRAGService(repository=None)
    svc.repository = SimpleNamespace(db=fake_db)
    monkeypatch.setattr(
        svc,
        "_resolve_to_db_values",
        lambda user_inputs, taxonomy_field, language: ["Myrcene"],
    )

    candidates = [
        SimpleNamespace(id=1, name="Dominant Match"),
        SimpleNamespace(id=2, name="No Match"),
        SimpleNamespace(id=3, name="Other Match"),
    ]
    analysis = QueryAnalysis(natural_response=".", required_terpenes=["myrcene"])
    filter_params = {}

    filtered = svc._apply_attribute_filters(candidates, analysis, filter_params)

    assert [strain.id for strain in filtered] == [1, 3]
    assert fake_db.joined_keys == ["dominant_terpene", "other_terpenes"]
    assert filter_params["terpenes"] == ["Myrcene"]
