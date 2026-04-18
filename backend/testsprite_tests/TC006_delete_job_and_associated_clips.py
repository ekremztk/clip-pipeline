import requests, uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}


def test_delete_job_and_associated_clips():
    channel_id = f"test_{uuid.uuid4().hex[:8]}"
    requests.post(f"{BASE_URL}/channels",
                  json={"channel_id": channel_id, "display_name": "TC006 Channel"},
                  headers=JSON_HEADERS, timeout=TIMEOUT)

    r = requests.post(f"{BASE_URL}/jobs",
                      data={"title": "TC006 Job", "channel_id": channel_id,
                            "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                      headers=HEADERS, timeout=TIMEOUT)
    assert r.status_code in (200, 201), f"Job creation failed: {r.text}"
    job_id = r.json()["job_id"]

    del_r = requests.delete(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
    assert del_r.status_code == 200, f"Expected 200 on delete, got {del_r.status_code}"
    assert del_r.json().get("deleted") is True
    assert del_r.json().get("job_id") == job_id

    get_r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
    assert get_r.status_code == 404

    del2 = requests.delete(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
    assert del2.status_code == 404

    del3 = requests.delete(f"{BASE_URL}/jobs/{uuid.uuid4()}", headers=HEADERS, timeout=TIMEOUT)
    assert del3.status_code == 404
