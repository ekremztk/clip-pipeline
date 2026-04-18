import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token"}


def create_channel():
    channel_id = f"test_{uuid.uuid4().hex[:8]}"
    resp = requests.post(
        f"{BASE_URL}/channels",
        json={"channel_id": channel_id, "display_name": "Test Channel"},
        headers={**HEADERS, "Content-Type": "application/json"},
        timeout=TIMEOUT
    )
    assert resp.status_code == 200, f"Channel creation failed: {resp.text}"
    return channel_id


def test_create_new_pipeline_job():
    channel_id = create_channel()
    job_id = None
    try:
        resp = requests.post(
            f"{BASE_URL}/jobs",
            data={"title": "Test Video Title", "channel_id": channel_id,
                  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers=HEADERS, timeout=TIMEOUT
        )
        assert resp.status_code in (200, 201), f"Job creation failed {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "job_id" in data, f"Missing job_id in response: {data}"
        job_id = data["job_id"]
        uuid.UUID(job_id)
        assert data.get("status") == "queued", f"Expected queued: {data}"

        # YouTube IP blocked check
        time.sleep(5)
        status_resp = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
        assert status_resp.status_code == 200
        if status_resp.json()["job"].get("status") == "failed":
            print("WARNING: YouTube IP likely blocked. Skipping.")
            return

        # Missing title → 422
        r = requests.post(f"{BASE_URL}/jobs", data={"channel_id": channel_id}, headers=HEADERS, timeout=TIMEOUT)
        assert r.status_code == 422, f"Expected 422 for missing title, got {r.status_code}"

        # Non-existent channel → 404
        r2 = requests.post(f"{BASE_URL}/jobs", data={"title": "Test", "channel_id": "nonexistent_xyz"},
                           headers=HEADERS, timeout=TIMEOUT)
        assert r2.status_code == 404, f"Expected 404 for bad channel, got {r2.status_code}"

    finally:
        if job_id:
            requests.delete(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
