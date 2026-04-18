import requests, uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}


def test_list_clips_for_channel_and_job():
    channel_id = f"test_{uuid.uuid4().hex[:8]}"
    requests.post(f"{BASE_URL}/channels",
                  json={"channel_id": channel_id, "display_name": "TC008 Channel"},
                  headers=JSON_HEADERS, timeout=TIMEOUT)

    # No channel_id → 200 empty list (NOT 422)
    r = requests.get(f"{BASE_URL}/clips", headers=HEADERS, timeout=TIMEOUT)
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # With channel_id → 200 list
    r2 = requests.get(f"{BASE_URL}/clips", headers=HEADERS,
                      params={"channel_id": channel_id}, timeout=TIMEOUT)
    assert r2.status_code == 200
    clips = r2.json()
    assert isinstance(clips, list)
    for clip in clips:
        assert "id" in clip
        assert "standalone_score" in clip, "Field must be standalone_score not score"
        assert "user_approved" in clip, "Field must be user_approved not is_successful"

    # Fake job_id → 200 empty or 404
    r3 = requests.get(f"{BASE_URL}/clips", headers=HEADERS,
                      params={"channel_id": channel_id, "job_id": str(uuid.uuid4())}, timeout=TIMEOUT)
    assert r3.status_code in (200, 404)
