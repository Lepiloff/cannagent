import uuid
import requests

API = "http://localhost:8000/api/v1/chat/ask/"


def test_switch_to_sativa_creativity_flow():
    # 1) Начальный запрос (гибрид + высокий THC + ментол)
    sid = str(uuid.uuid4())
    r1 = requests.post(API, json={
        "message": "recommend me hybrid strain with high thc level and menthol aroma",
        "session_id": sid,
        "history": []
    }, timeout=15)
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1.get("session_id") == sid
    assert j1.get("query_type") in ["search_strains", "filter_strains"]

    # 2) Follow-up (какой самый высокий THC)
    r2 = requests.post(API, json={
        "message": "that sort from list above have highest thc",
        "session_id": sid,
        "history": []
    }, timeout=15)
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2.get("session_id") == sid
    assert j2.get("query_type") in ["sort_strains", "comparison", "follow_up"]

    # 3) Смена темы: Sativa + creativity → ожидаем расширение поиска и преимущественно Sativa
    r3 = requests.post(API, json={
        "message": "ok, I need sativa sort for creative as well",
        "session_id": sid,
        "history": []
    }, timeout=15)
    assert r3.status_code == 200
    j3 = r3.json()
    assert j3.get("session_id") == sid
    assert j3.get("query_type") in ["search_strains", "expand_search"]
    cats = [s.get("category") for s in j3.get("recommended_strains", [])]
    # допускаем 1-2 смешанных, но ожидаем, что большинство Sativa
    assert len(cats) > 0
    assert cats.count("Sativa") >= max(1, len(cats) - 1)


