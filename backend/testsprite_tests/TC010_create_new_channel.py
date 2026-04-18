import requests, uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token", "Content-Type": "application/json"}


def test_create_new_channel():
    channel_id = f"test_{uuid.uuid4().hex[:8]}"

    r = requests.post(f"{BASE_URL}/channels",
                      json={"channel_id": channel_id, "display_name": "Test Channel"},
                      headers=HEADERS, timeout=TIMEOUT)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert r.json().get("created") is True
    assert r.json().get("channel_id") == channel_id

    # GET to verify
    rg = requests.get(f"{BASE_URL}/channels/{channel_id}", headers=HEADERS, timeout=TIMEOUT)
    assert rg.status_code == 200
    assert rg.json().get("id") == channel_id

    # Missing fields → 422
    assert requests.post(f"{BASE_URL}/channels", json={}, headers=HEADERS, timeout=TIMEOUT).status_code == 422
    assert requests.post(f"{BASE_URL}/channels",
                         json={"channel_id": f"test_{uuid.uuid4().hex[:8]}"},
                         headers=HEADERS, timeout=TIMEOUT).status_code == 422
