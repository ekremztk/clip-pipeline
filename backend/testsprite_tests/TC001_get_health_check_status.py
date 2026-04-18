import requests

BASE_URL = "http://localhost:8000"
TIMEOUT = 30

def test_get_health_check_status():
    url = f"{BASE_URL}/health"
    try:
        response = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        assert False, f"Request to /health failed: {e}"

    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    try:
        data = response.json()
    except ValueError:
        assert False, "Response is not valid JSON"

    assert isinstance(data.get("ok"), bool), "'ok' field should be boolean"
    assert isinstance(data.get("version"), str), "'version' field should be string"
    assert isinstance(data.get("environment"), str), "'environment' field should be string"

test_get_health_check_status()