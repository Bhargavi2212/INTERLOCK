import pymupdf
import pytest

from app.jobs import runner

A4 = (595, 842)
A1 = (1684, 2384)
BODY = "SG Unit-1 floor wash water transfer pumps, rated capacity 105 m3/hr each. " * 5


def make_pdf(pages):
    doc = pymupdf.open()
    for (w, h), text in pages:
        page = doc.new_page(width=w, height=h)
        page.insert_text((40, 60), text[:90])
        if len(text) > 90:
            page.insert_textbox(pymupdf.Rect(40, 80, w - 40, h - 40), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def inline_jobs(monkeypatch):
    monkeypatch.setattr(runner, "INLINE", True)


def upload(api, store, files):
    pid = api.post("/plants", json={"name": "t"}).json()["plant_id"]
    api.post(f"/plants/{pid}/files", json=[
        {"relative_path": name, "size": len(data), "content_hash": f"h-{name}"} for name, data in files])
    for name, data in files:
        store.put_blob(pid, name, data)
    return pid


def test_three_pages_one_drawing(api, store, inline_jobs):
    pdf = make_pdf([(A4, BODY), (A1, "P&ID D3-146 200NB"), (A4, BODY)])
    pid = upload(api, store, [("Vol1/spec.pdf", pdf)])
    job = api.post(f"/plants/{pid}/ingest").json()["job_id"]
    assert store.get_job(job)["state"] == "done"
    plant = store.get_plant(pid)
    assert plant["page_count"] == 3 and plant["ingest_status"] == "done"
    assert plant["files"][0]["status"] == "ingested" and plant["files"][0]["pages"] == 3
    assert [store.get_page(pid, n)["is_drawing"] for n in range(3)] == [False, True, False]
    assert set(k[1] for k in store.pngs) == {1}
    words = store.get_page(pid, 1)["words"]
    assert words and all(0 <= c <= 1 for w in words for c in w[:4])
    assert store.get_page(pid, 1)["file"] == "Vol1/spec.pdf" and store.get_page(pid, 1)["page"] == 2


def test_pages_all_in_n_order(api, store, inline_jobs):
    pid = upload(api, store, [("b.pdf", make_pdf([(A4, BODY)] * 2)), ("a.pdf", make_pdf([(A4, BODY)] * 3))])
    api.post(f"/plants/{pid}/ingest")
    pages = store.get_pages_all(pid)
    assert [p["n"] for p in pages] == list(range(5))
    assert [(p["file"], p["page"]) for p in pages] == [("a.pdf", 1), ("a.pdf", 2), ("a.pdf", 3),
                                                       ("b.pdf", 1), ("b.pdf", 2)]
    assert set(pages[0]) == {"n", "file", "page", "text"}


def test_corrupt_pdf_fails_that_file_only(api, store, inline_jobs):
    pid = upload(api, store, [("bad.pdf", b"not a pdf at all"), ("good.pdf", make_pdf([(A4, BODY)]))])
    job = api.post(f"/plants/{pid}/ingest").json()["job_id"]
    assert store.get_job(job)["state"] == "done"
    status = {f["relative_path"]: f for f in store.get_plant(pid)["files"]}
    assert status["bad.pdf"]["status"] == "failed" and status["bad.pdf"]["error"]
    assert status["good.pdf"]["status"] == "ingested"
    assert store.get_plant(pid)["page_count"] == 1


def test_missing_upload_marked_missing(api, store, inline_jobs):
    pid = api.post("/plants", json={"name": "t"}).json()["plant_id"]
    api.post(f"/plants/{pid}/files", json=[{"relative_path": "never.pdf", "size": 5, "content_hash": "z"}])
    api.post(f"/plants/{pid}/ingest")
    assert store.get_plant(pid)["files"][0]["status"] == "missing"


def test_second_batch_continues_n(api, store, inline_jobs):
    pid = upload(api, store, [("a.pdf", make_pdf([(A4, BODY)] * 2))])
    api.post(f"/plants/{pid}/ingest")
    api.post(f"/plants/{pid}/files", json=[{"relative_path": "z.pdf", "size": 10, "content_hash": "hz"}])
    store.put_blob(pid, "z.pdf", make_pdf([(A4, BODY)]))
    api.post(f"/plants/{pid}/ingest")
    assert [p["n"] for p in store.get_pages_all(pid)] == [0, 1, 2]
    assert store.get_plant(pid)["page_count"] == 3


def test_restart_marks_unfinished_failed(store):
    j = store.create_job({"type": "ingest"})
    assert runner.fail_unfinished_on_startup() == 1
    assert store.get_job(j)["state"] == "failed" and store.get_job(j)["error"] == "server restarted"
