import requests, uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
SPEAKER_MAP = {"speaker_map": {"0": {"role": "host", "name": "Joe"}, "1": {"role": "guest", "name": "Alex"}}}


def test_confirm_speaker_map_and_resume_pipeline():
    # Non-existent job → 404
    r = requests.post(f"{BASE_URL}/jobs/{uuid.uuid4()}/confirm-speakers",
                      json=SPEAKER_MAP, headers=JSON_HEADERS, timeout=TIMEOUT)
    assert r.status_code == 404

    channel_id = f"test_{uuid.uuid4().hex[:8]}"
    requests.post(f"{BASE_URL}/channels",
                  json={"channel_id": channel_id, "display_name": "TC007 Channel"},
                  headers=JSON_HEADERS, timeout=TIMEOUT)

    r2 = requests.post(f"{BASE_URL}/jobs",
                       data={"title": "TC007 Job", "channel_id": channel_id,
                             "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                       headers=HEADERS, timeout=TIMEOUT)
    assert r2.status_code in (200, 201)
    job_id = r2.json()["job_id"]

    try:
        # Job not in awaiting_speaker_confirm → 400 or 404
        r3 = requests.post(f"{BASE_URL}/jobs/{job_id}/confirm-speakers",
                           json=SPEAKER_MAP, headers=JSON_HEADERS, timeout=TIMEOUT)
        assert r3.status_code in (400, 404), \
            f"Expected 400 or 404 for queued job, got {r3.status_code}: {r3.text}"
    finally:
        requests.delete(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS, timeout=TIMEOUT)
