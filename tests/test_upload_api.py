def new_plant(api):
    return api.post("/plants", json={"name": "BHEL"}).json()["plant_id"]


def f(path, size=100, h=None):
    return {"relative_path": path, "size": size, "content_hash": h or f"hash-{path}",
            "content_type": "application/pdf"}


def test_accept_skip_unsafe_duplicate(api, store):
    pid = new_plant(api)
    r = api.post(f"/plants/{pid}/files", json=[
        f("Vol3/P&IDs/sheet-12.pdf"),
        f("Vol4/sheet-12.PDF"),
        f("drawing.dwg"),
        f("sheet.xlsx"),
        f("empty.pdf", size=0),
        f("../escape.pdf"),
        f("/abs.pdf"),
        f("copy.pdf", h="hash-Vol3/P&IDs/sheet-12.pdf"),
    ]).json()
    assert [a["relative_path"] for a in r["accepted"]] == ["Vol3/P&IDs/sheet-12.pdf", "Vol4/sheet-12.PDF"]
    assert all(a["upload_url"].startswith("memory://upload/") for a in r["accepted"])
    reasons = {s["relative_path"]: s["reason"] for s in r["skipped"]}
    assert reasons["drawing.dwg"] == "not a PDF: .dwg"
    assert reasons["sheet.xlsx"] == "not a PDF: .xlsx"
    assert reasons["empty.pdf"] == "empty file"
    assert reasons["../escape.pdf"] == "unsafe path"
    assert reasons["/abs.pdf"] == "unsafe path"
    assert r["duplicates"] == [{"relative_path": "copy.pdf"}]
    files = store.get_plant(pid)["files"]
    assert [x["status"] for x in files] == ["uploading", "uploading"]


def test_same_name_different_folders_kept_distinct(api):
    pid = new_plant(api)
    r = api.post(f"/plants/{pid}/files", json=[f("A/s.pdf"), f("B/s.pdf")]).json()
    assert len(r["accepted"]) == 2


def test_duplicate_across_batches(api):
    pid = new_plant(api)
    api.post(f"/plants/{pid}/files", json=[f("a.pdf", h="X")])
    r = api.post(f"/plants/{pid}/files", json=[f("again.pdf", h="X")]).json()
    assert r["duplicates"] == [{"relative_path": "again.pdf"}] and r["accepted"] == []


def test_windows_backslashes_normalised(api):
    pid = new_plant(api)
    r = api.post(f"/plants/{pid}/files", json=[f("Vol3\\sheet.pdf")]).json()
    assert r["accepted"][0]["relative_path"] == "Vol3/sheet.pdf"


def test_unknown_plant_404(api):
    assert api.post("/plants/nope/files", json=[]).status_code == 404


def test_list_plants_newest_first(api, store):
    a = new_plant(api)
    b = new_plant(api)
    store.mutate_plant(a, lambda d: d.update(created_at="2026-11-21T10:00:00+00:00"))
    store.mutate_plant(b, lambda d: d.update(created_at="2026-11-21T11:00:00+00:00"))
    listed = api.get("/plants").json()
    assert [p["plant_id"] for p in listed][:2] == [b, a]
    assert set(listed[0]) == {"plant_id", "name", "page_count", "ingest_status", "files", "created_at"}
