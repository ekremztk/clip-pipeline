import requests, subprocess, tempfile, os, uuid

BASE_URL = "http://localhost:8000"
TIMEOUT = 60
HEADERS = {"Authorization": "Bearer dev_token"}


def make_real_mp4(path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:size=64x64:rate=1",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", "1", "-c:v", "libx264", "-c:a", "aac", path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def test_upload_video_preview():
    tmp = os.path.join(tempfile.gettempdir(), f"test_{uuid.uuid4().hex}.mp4")
    try:
        make_real_mp4(tmp)
        with open(tmp, "rb") as f:
            r = requests.post(f"{BASE_URL}/jobs/upload-preview", headers=HEADERS,
                              files={"file": ("test.mp4", f, "video/mp4")}, timeout=TIMEOUT)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "upload_id" in data, f"Missing upload_id: {data}"
        assert "duration_seconds" in data, f"Missing duration_seconds: {data}"
        uuid.UUID(data["upload_id"])
        assert data["duration_seconds"] > 0

        # Invalid format → 400
        r2 = requests.post(f"{BASE_URL}/jobs/upload-preview", headers=HEADERS,
                           files={"file": ("x.txt", b"not a video", "text/plain")}, timeout=TIMEOUT)
        assert r2.status_code == 400, f"Expected 400 for invalid file, got {r2.status_code}"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
