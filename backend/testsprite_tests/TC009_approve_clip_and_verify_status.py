import requests, uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 30
HEADERS = {"Authorization": "Bearer dev_token"}
EXISTING_CHANNEL_ID = "speedy_cast"


def test_approve_clip_and_verify_status():
    clips = requests.get(f"{BASE_URL}/clips", headers=HEADERS,
                         params={"channel_id": EXISTING_CHANNEL_ID, "limit": 1}, timeout=TIMEOUT).json()

    if not clips:
        print(f"WARNING: No clips in '{EXISTING_CHANNEL_ID}'. Testing only 404 case.")
        r = requests.patch(f"{BASE_URL}/clips/{uuid.uuid4()}/approve", headers=HEADERS, timeout=TIMEOUT)
        assert r.status_code == 404
        return

    clip_id = clips[0]["id"]

    r = requests.patch(f"{BASE_URL}/clips/{clip_id}/approve", headers=HEADERS, timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json().get("approved") is True
    assert r.json().get("clip_id") == clip_id

    assert requests.get(f"{BASE_URL}/clips/{clip_id}", headers=HEADERS, timeout=TIMEOUT).json().get("user_approved") is True

    r2 = requests.patch(f"{BASE_URL}/clips/{clip_id}/reject", headers=HEADERS, timeout=TIMEOUT)
    assert r2.status_code == 200 and r2.json().get("rejected") is True

    r3 = requests.patch(f"{BASE_URL}/clips/{clip_id}/unset-approval", headers=HEADERS, timeout=TIMEOUT)
    assert r3.status_code == 200 and r3.json().get("unset") is True

    r404 = requests.patch(f"{BASE_URL}/clips/{uuid.uuid4()}/approve", headers=HEADERS, timeout=TIMEOUT)
    assert r404.status_code == 404
