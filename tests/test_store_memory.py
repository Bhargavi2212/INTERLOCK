from app.store.memory import MemoryStore


def test_plant_lifecycle():
    s = MemoryStore()
    p = s.create_plant("BHEL")
    assert p["ingest_status"] == "empty" and len(p["plant_id"]) == 12
    s.mutate_plant(p["plant_id"], lambda d: d["files"].append({"relative_path": "a.pdf"}))
    assert s.get_plant(p["plant_id"])["files"] == [{"relative_path": "a.pdf"}]


def test_returned_docs_are_copies():
    s = MemoryStore()
    p = s.create_plant("x")
    p["name"] = "changed"
    assert s.get_plant(p["plant_id"])["name"] == "x"


def test_change_index_resolves_without_plant_id():
    s = MemoryStore()
    s.put_change("plant1", "chg1", {"text": "t"})
    assert s.get_change("chg1") == {"text": "t"}
    assert s.change_index["chg1"] == "plant1"


def test_jobs_and_unfinished():
    s = MemoryStore()
    j = s.create_job({"type": "ingest"})
    assert s.get_job(j)["state"] == "queued"
    assert [x["job_id"] for x in s.unfinished_jobs()] == [j]
    s.update_job(j, {"state": "done"})
    assert s.unfinished_jobs() == []


def test_pages_all_round_trip():
    s = MemoryStore()
    pages = [{"n": 0, "file": "a.pdf", "page": 1, "text": "x"}]
    s.put_pages_all("p", pages)
    assert s.get_pages_all("p") == pages
