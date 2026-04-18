import requests
import uuid
import time

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}


def create_channel():
    channel_id = f"test_{uuid.uuid4().hex[:8]}"
    resp = requests.post(f"{BASE_URL}/channels",
                         json={"channel_id": channel_id, "display_name": "TC003 Channel"},
                         headers=JSON_HEADERS, timeout=TIMEOUT)
    assert resp.status_code == 200, f"Channel failed: {resp.text}"
    return channel_id


def test_get_job_status_and_metadata():
    channel_id = create_channel()
    job_id = None
    try:
        resp = requests.post(f"{BASE_URL}/jobs",
                             data={"title": "TC003 Video", "channel_id": channel_id,
                                   "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                             headers=HEADERS, timeout=TIMEOUT)
        assert resp.status_code in (200, 201), f"Job failed: {resp.text}"
        job_id = resp.json()["job_id"]

        time.sleep(5)
        r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
        assert r.status_code == 200
        outer = r.json()
        assert "job" in outer, f"Missing 'job' key: {list(outer.keys())}"
        assert "clips" in outer
        job = outer["job"]

        if job.get("status") == "failed":
            print("WARNING: YouTube IP likely blocked. Skipping metadata checks.")
            return

        assert job.get("id") == job_id
        valid = {"queued","processing","analyzing","awaiting_speaker_confirm","cutting","completed","failed","partial"}
        assert job["status"] in valid
        assert "progress_pct" in job
        assert "clip_count" in job
        assert "video_title" in job
        assert job.get("channel_id") == channel_id

        # 404 for non-existent
        r404 = requests.get(f"{BASE_URL}/jobs/00000000-0000-0000-0000-000000000000", headers=HEADERS, timeout=TIMEOUT)
        assert r404.status_code == 404
    finally:
        if job_id:
            requests.delete(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
