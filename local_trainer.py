import os
import json
import psycopg2
from google import genai
import yt_dlp

# --- AYARLAR ---
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

def get_embedding(text):
    """Metni yapay zekanın anlayacağı 768 boyutlu sayı dizisine çevirir."""
    # text-embedding-004 modeli tam 768 boyutlu çıktı verir (Tablomuzla uyumlu)
    result = client.models.embed_content(
        model="text-embedding-004",
        contents=text
    )
    return result.embeddings[0].values

def download_audio(video_url):
    print(f"[*] YouTube'dan veri çekiliyor: {video_url}")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': 'temp_audio.%(ext)s',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return info.get('title', 'Unknown Title'), "temp_audio.m4a"

def analyze_and_save(video_url):
    try:
        title, audio_path = download_audio(video_url)
        
        # 1. Gemini Analizi (İngilizce Uzman Modu)
        print("[*] Gemini 'Viral DNA' analizi yapıyor...")
        audio_file = client.files.upload(file=audio_path)
        
        prompt = f"""
        Analyze the first 60 seconds of this viral video titled "{title}".
        Identify why it went viral and extract the core DNA.
        Return ONLY a JSON:
        {{
            "hook_text": "The exact attention-grabbing first 3 seconds sentence",
            "transcript_segment": "A key 30-second transcript segment",
            "why_it_went_viral": "Professional analysis of its success",
            "viral_score": 95
        }}
        """
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config={"response_mime_type": "application/json"}
        )
        dna = json.loads(response.text)
        
        # 2. Vektör (Embedding) Oluşturma
        # 'why_it_went_viral' kısmını hafıza için matematikselleştiriyoruz
        print("[*] Anlamsal hafıza (embedding) oluşturuluyor...")
        vector = get_embedding(dna["why_it_went_viral"])

        # 3. Railway Veritabanına Kayıt
        print("[*] Railway veritabanına işleniyor...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        query = """
        INSERT INTO viral_library 
        (video_title, hook_text, transcript_segment, why_it_went_viral, viral_score, embedding, source_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cur.execute(query, (
            title, 
            dna["hook_text"], 
            dna["transcript_segment"], 
            dna["why_it_went_viral"], 
            dna["viral_score"], 
            vector, 
            video_url
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        client.files.delete(name=audio_file.name)
        os.remove(audio_path)
        
        print(f"\n[✔] BAŞARILI: '{title}' kütüphaneye eklendi!")

    except Exception as e:
        print(f"[!] Hata: {e}")

if __name__ == "__main__":
    print("=== PROGNOT VİRAL EĞİTİM MODÜLÜ (READY) ===")
    url = input("Eğitilecek YouTube URL (Veya çıkmak için Enter): ")
    if url:
        analyze_and_save(url)