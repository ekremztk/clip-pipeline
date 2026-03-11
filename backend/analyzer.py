import os
import psycopg2
import json
import re # JSON temizliği için eklendi
from google import genai
from google.genai import types # JSON formatı zorlamak için eklendi

# ... (AYARLAR kısmı aynı kalacak) ...

def get_embedding(text):
    """Metni 768 boyutlu vektöre çevirir. Çökmelere karşı korumalıdır."""
    try:
        # Hata veren text-embedding-004 yerine, en stabil ve güncel olanını kullanıyoruz
        result = client.models.embed_content(
            model="text-embedding-004", # Eğer bu çalışmazsa 'models/text-embedding-004' olarak denemeye devam edeceğiz, ama genai kütüphanesi bazen eski modelleri istiyor olabilir.
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"[!] Embedding Hatası Detayı: {e}")
        # Eğer text-embedding-004 hata verirse, eski ama çalışan modele düşelim (Fallback)
        try:
            print("[*] Embedding için alternatif model deneniyor...")
            result = client.models.embed_content(
                model="embedding-001",
                contents=text
            )
            return result.embeddings[0].values
        except Exception as e2:
            print(f"[!] Alternatif Embedding de başarısız: {e2}")
            return None

# ... (find_similar_viral_dna aynı kalacak) ...

def analyze_video_for_clips(audio_path, video_title):
    """Videonun içindeki viral potansiyelli anları bulur ve FFmpeg için saniye döner."""
    print(f"[*] '{video_title}' için RAG hafızası taranıyor...")
    refs = find_similar_viral_dna(video_title)
    ref_text = json.dumps(refs, ensure_ascii=False) if refs else "Referans bulunamadı, genel viral kurallarını uygula."

    print("[*] Gemini 2.5 Flash ile klip noktaları analiz ediliyor...")
    try:
        audio_file = client.files.upload(file=audio_path)
        
        prompt = f"""
        You are an elite Viral Video Architect and TikTok/Shorts Retention Algorithm Expert. 
        Your sole purpose is to analyze long-form video transcripts and extract the absolute best 15-35 second segments that are mathematically and psychologically optimized to go viral.

        RAG CONTEXT (PROVEN VIRAL DNA):
        {ref_text}

        CURRENT VIDEO TITLE: "{video_title}"

        YOUR MISSION & CONSTRAINTS:
        1. Extract exactly 3 highly viral potential segments.
        2. Determine timestamps by carefully listening to the speech start and end points. DO NOT cut mid-sentence.
        3. Add a 0.5-second buffer (pad) to the end_time.
        4. The first 3 seconds of each segment MUST contain a powerful "Hook".
        5. Clip duration MUST be strictly between 15 and 35 seconds.
        6. Timestamps MUST be in raw total SECONDS (float or int), NOT MM:SS. (e.g., 65.5).
        7. You must output ONLY a valid JSON array. DO NOT include markdown formatting like ```json or ```. Just the raw array starting with [ and ending with ]. Make sure all strings inside are properly escaped.

        EXPECTED JSON OUTPUT FORMAT:
        [
          {{
            "start_time": 124.5,
            "end_time": 154.0,
            "hook_text": "The exact first sentence spoken in the clip",
            "psychological_trigger": "Explain the psychological reason this holds attention",
            "rag_reference_used": "Which reference was used",
            "virality_score": 98
          }}
        ]
        """
        
        # Gemini'yi JSON formatında cevap vermeye "zorluyoruz"
        json_config = types.GenerateContentConfig(response_mime_type="application/json")
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[audio_file, prompt],
            config=json_config
        )
        
        # İşlem bitince dosyayı temizle
        try:
            client.files.delete(name=audio_file.name)
        except:
            pass

        # --- JSON TEMİZLİK VE ONARMA KATMANI ---
        raw_text = response.text.strip()
        
        # Eğer Gemini inatla markdown (```json ... ```) gönderdiyse onu temizle
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text)
            
        print("[*] Gemini'den gelen ham cevap boyutu:", len(raw_text))

        try:
            parsed_json = json.loads(raw_text)
            return parsed_json
        except json.JSONDecodeError as je:
            print(f"[!] Kritik JSON Parse Hatası: {je}")
            print(f"[!] Hatalı Metin (İlk 500 karakter): {raw_text[:500]}...")
            return []
            
    except Exception as e:
        print(f"[!] Gemini Analiz Hatası: {e}")
        return []