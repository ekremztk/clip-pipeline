import os
import json
import subprocess
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

CHANNEL_URL = "https://www.youtube.com/@Speedy-Cast-Clips/shorts"
JSON_FILE = "viral_references.json"
LIMIT = 100

def get_top_100_shorts():
    print("🔍 Tüm shorts'lar taranıyor ve izlenmeye göre sıralanıyor. Lütfen bekle...")
    cmd =["yt-dlp", "--dump-json", "--flat-playlist", CHANNEL_URL]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    videos =[]
    for line in result.stdout.strip().split("\n"):
        if not line: continue
        try:
            data = json.loads(line)
            videos.append({
                "url": data.get("url"),
                "views": data.get("view_count", 0)
            })
        except:
            continue

    videos.sort(key=lambda x: x["views"] or 0, reverse=True)
    return [v["url"] for v in videos[:LIMIT]]

def process_video(url):
    print(f"\n🎬 İşleniyor: {url}")
    tmp_audio = "temp_audio.mp3"
    
    info_cmd =["yt-dlp", "--dump-json", "--no-download", url]
    info_res = subprocess.run(info_cmd, capture_output=True, text=True)
    try:
        info = json.loads(info_res.stdout)
        title = info.get("title", "Başlıksız")
        duration = info.get("duration", 0)
    except:
        title, duration = "Başlıksız", 0

    subprocess.run(["yt-dlp", "-x", "--audio-format", "mp3", "-o", tmp_audio, url], capture_output=True)
    if not os.path.exists(tmp_audio):
        print("❌ Ses indirilemedi, atlanıyor.")
        return None

    try:
        print("🤖 Gemini analiz ediyor...")
        audio_file = client.files.upload(file=tmp_audio)
        prompt = 'Sesi dinle ve sadece şu JSON formatında yanıt ver: {"transcript": "videonun tam metni", "why_it_went_viral": "Neden viral oldu? 1 cümle."}'
        
        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        res = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config=json_config
        )
        
        data = json.loads(res.text)
        data["title"] = title
        data["duration"] = duration
        data["source_url"] = url
        
        os.remove(tmp_audio)
        try:
            client.files.delete(name=audio_file.name)
        except:
            pass
            
        return data
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        if os.path.exists(tmp_audio): os.remove(tmp_audio)
        return None

def main():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r") as f:
            try: veriler = json.load(f)
            except: veriler = []
    else:
        veriler = []

    islenen_urller =[v.get("source_url") for v in veriler]
    top_urls = get_top_100_shorts()

    for url in top_urls:
        if url in islenen_urller:
            print(f"⏭️ Zaten JSON'da var, atlanıyor: {url}")
            continue
            
        sonuc = process_video(url)
        if sonuc:
            veriler.append(sonuc)
            with open(JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(veriler, f, indent=2, ensure_ascii=False)
            print("✅ JSON'a eklendi!")

if __name__ == "__main__":
    main()