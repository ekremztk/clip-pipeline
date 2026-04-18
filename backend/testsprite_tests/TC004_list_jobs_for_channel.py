import requests
import uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}


def test_list_jobs_for_channel():
    channel_id = f"test_{uuid.uuid4().hex[:8]}"
    requests.post(f"{BASE_URL}/channels",
                  json={"channel_id": channel_id, "display_name": "TC004 Channel"},
                  headers=JSON_HEADERS, timeout=TIMEOUT)

    r = requests.get(f"{BASE_URL}/jobs", headers=HEADERS, params={"channel_id": channel_id}, timeout=TIMEOUT)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    assert isinstance(r.json(), list)

    r422 = requests.get(f"{BASE_URL}/jobs", headers=HEADERS, timeout=TIMEOUT)
    assert r422.status_code == 422, f"Expected 422 without channel_id, got {r422.status_code}"

    r_limit = requests.get(f"{BASE_URL}/jobs", headers=HEADERS,
                            params={"channel_id": channel_id, "limit": 5}, timeout=TIMEOUT)
    assert r_limit.status_code == 200
    assert len(r_limit.json()) <= 5
