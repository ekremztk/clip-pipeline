# DIRECTOR GELİŞTİRME REHBERİ — GEÇİCİ
> Bu dosya geliştirme sürecinde kullanılacak. Geliştirme bitince DIRECTOR_MODULE.md'ye işlenip silinecek.
> Kaynak: Dışarıdan gelen AI analiz raporu + kendi kod analizi + ikinci tur doğrulama (2026-03-25)

---

## ÖNCELİK SIRASI (Uygulama Sırası)

| # | Konu | Kaynak | Etki | Süre |
|---|------|--------|------|------|
| 1 | System prompt tool kullanım kuralları + erişim haritası | B1+B3 | Chat UX dramatik iyileşir | 30dk |
| 2 | Tool loop dedup guard'ı (tam implementasyon) | B2 | Spam önlenir, maliyet düşer | 1s |
| 3 | SQL güvenliği: UNION + comment + parametrize | B5+B6 | Production güvenliği | 2s |
| 4 | Schema doğrulama (jobs.updated_at, channels.name) | B7 | Veri doğruluğu | 30dk |
| 5 | Message router + run_agent use_tools parametresi | C1 | UX kritik iyileşme | 2s |
| 6 | Self-analysis write_access düzelt | B11 | Tutarlılık | 30dk |
| 7 | UNUSED_CLIPS mantık düzeltmesi | B8 | Proactive doğruluğu | 30dk |
| 8 | _trigger_analysis learn skoru bug fix | B12 | Skor doğruluğu | 15dk |
| 9 | Result truncation iyileştirme | B13 | Veri kaybı önlenir | 1s |
| 10 | Connection pooling + shutdown handling | D6 | Performans | 1s |
| 11 | Recommendation lifecycle (mark/cleanup) | C6 | Tablo çöplük olmaz | 2s |
| 12 | Learning scope genişletme + hook bağlantıları | D4 | Daha derin öğrenme | 2s |
| 13 | Scorer ayrı modül | C4 | Analiz kalitesi | 3s |

---

## BÖLÜM 1 — YANLIŞLAR / YANILTICI ANALİZ NOTLARI

> Dışarıdan gelen raporda bazı bulgular koda bakmadan yapılmış. Bunlar kapalı:

### C9 — dna_auditor.py "binary dosya" iddiası → YANLIŞ
- `backend/app/director/dna_auditor.py` tam çalışan Python dosyası, 185 satır
- Raporun "binary" demesi PDF export artefaktı

### C10 — router.py "binary dosya" iddiası → YANLIŞ
- `backend/app/director/router.py` tam çalışan FastAPI dosyası, 789 satır

### C3 — Health Pulse "hiç yok" iddiası → YANLIŞ, ZATEN YAPILDI
- `router.py` içinde `_compute_health_pulse()` var (5 check, weighted score)
- `main.py` içinde `_health_pulse_scheduler()` her 5 dakikada günceller

### C8 — Weekly Digest "hiç yok" iddiası → YANLIŞ, ZATEN YAPILDI
- `main.py` içinde `_daily_analysis_scheduler()` günlük 03:00 UTC + `_run_weekly_digest()` Pazartesi 09:00

### C7 — Cross-module signals "hiç yok" iddiası → KISMI
- `clips_ready_for_editor` sinyali orchestrator'da var ✅
- `clip_opened_in_editor` sinyali router.py'de var ✅
- Eksik: publish, YouTube metadata, reframe sinyalleri

### B4 / E1 — Dosya yapısı yeniden düzenlemesi → ERTELE
- agent.py 851 satır, çalışıyor. Refactor kırılma riski yüksek.
- **Önce bug fix, sonra yapı. Şimdilik dokunma.**

---

## BÖLÜM 2 — GEÇERLİ VE YAPILMASI GEREKEN

### ✅ ÖNCE YAPILACAK

---

#### 1. System Prompt: Araç Kuralları + Erişim Haritası (B1 + B3)

**Sorun:** Gemini her mesajda tool çağırma eğiliminde. "Merhaba" desen bile `query_memory` çağırıyor.
Ayrıca prompt'ta "erişim haritası" yok — dosya bulamazsa 5 farklı path denemeye başlıyor.

**SYSTEM_PROMPT'a eklenecek** (mevcut prensiplerin başına):

```
## ARAÇ KULLANIM KURALLARI

ARAÇ KULLANMA — doğrudan cevap ver:
- Selamlaşma, teşekkür, onaylama ("merhaba", "tamam", "teşekkürler", "harika")
- Bu konuşmada zaten araçla öğrendiğin bilgiyi tekrar soruyorsa
- Genel programlama/AI bilgisi soruları
- Kullanıcı sana bilgi VERİYORSA (kaydet ama tarama yapma)
- Fikir, beyin fırtınası, öneri istiyorsa

ARAÇ KULLAN — sisteme bak:
- Spesifik metrik ("pass rate kaç?", "son 7 günde kaç job?")
- Hata araştırması, güncel durum, dosya içeriği
- Kanal/klip/job hakkında veri

ALTIN KURAL: Soruyu araç çağırmadan cevaplayabiliyorsan ÇAĞIRMA.
Bir dosyayı bulamazsan EN FAZLA 1 kez dene. Bulamazsan "erişimim dışında" de ve devam et.
Aynı aracı aynı argümanlarla HİÇBİR ZAMAN iki kez çağırma.

## ERİŞİM HARİTAN

DOSYA SİSTEMİ:
  ✅ backend/app/ — tüm Python kodu
  ✅ docs/ — MD dokümantasyon
  ✅ backend/migrations/ — SQL şemaları
  ❌ frontend/ — bu container'da yok (git'te var ama read_file ile erişilemiyor)

VERİTABANI:
  ✅ OKUMA: Tüm tablolar
  ✅ YAZMA: director_* tabloları + channels.channel_dna (sadece dna alanı)
  ❌ YAZMA: jobs, clips, transcripts, pipeline_audit_log
```

> **Not:** İleride `capability_scan()` ile bu harita runtime'da dinamik oluşturulabilir
> (startup'ta docs/ var mı kontrol et, sonucu prompt'a inject et). Şimdilik statik yeterli.

---

#### 2. Tool Loop Dedup Guard — TAM İMPLEMENTASYON (B2)

**Sorun:** Aynı tool aynı argümanlarla tekrar çağrılabiliyor. MAX_TOOL_CALLS aşıldığında ne olacağı belirsiz.

**`run_agent` içinde, `max_iterations = 10` satırından sonra:**

```python
max_iterations = 10
iteration = 0
final_text = ""
_tool_call_hashes: set[str] = set()
_total_tool_calls = 0
MAX_TOOL_CALLS = 8
```

**Her tool call öncesi (fc loop içinde):**

```python
import hashlib
call_key = f"{tool_name}:{hashlib.md5(json.dumps(tool_args, sort_keys=True).encode()).hexdigest()}"
if call_key in _tool_call_hashes:
    result = {"note": "Bu araç aynı argümanlarla zaten çağrıldı. Mevcut sonucu kullan."}
else:
    _tool_call_hashes.add(call_key)
    _total_tool_calls += 1
    result = _dispatch_tool(tool_name, tool_args)
```

**MAX_TOOL_CALLS aşıldığında — TAM KOD:**

```python
if _total_tool_calls >= MAX_TOOL_CALLS:
    # Tool'suz final response zorla
    contents.append(types.Content(role="user", parts=[
        types.Part(text="[SİSTEM: Araç çağrısı limiti doldu. "
                        "Topladığın bilgilerle şimdi cevap ver.]")
    ]))
    final_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.3,
        # tools parametresi YOK — sadece text response
    )
    forced_response = client.models.generate_content(
        model=settings.GEMINI_MODEL_PRO,
        contents=contents,
        config=final_config,
    )
    if forced_response.candidates:
        for part in (forced_response.candidates[0].content.parts or []):
            if hasattr(part, "text") and part.text:
                final_text += part.text
    break
```

---

#### 3. SQL Güvenliği — UNION + Comment + Parametrize (B5 + B6)

**Sorun 1:** `query_database`'de UNION ve comment injection kontrolü yok.

```python
# GÜNCEL dangerous keywords (UNION ve comment eklendi):
DANGEROUS_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
    "TRUNCATE", "EXEC", "EXECUTE", "UNION",
]

# Ek kontroller:
if "--" in sql:
    return [{"error": "SQL comments not allowed"}]
if sql.count(";") > 0:
    return [{"error": "Multiple statements not allowed"}]
```

> **Neden UNION tehlikeli:** `SELECT 1 UNION SELECT password FROM auth_users` gibi injection mümkün.
> **Neden ; tehlikeli:** `SELECT 1; DROP TABLE clips` gibi birden fazla statement.

**Sorun 2:** Internal fonksiyonlarda string interpolation:
```python
# KÖTÜ (şu an böyle):
channel_filter = f"AND channel_id = '{channel_id}'"

# DOĞRU (parametrize):
# _run_sql'e params ekledikten sonra:
sql = "WHERE channel_id = %s"
rows = _run_sql(sql, (channel_id,))
```

**Öncelikli parametrize edilecek fonksiyonlar:** `compare_channels`, `get_pipeline_stats`, `get_pass_rate_trend`, `get_clip_analysis`, `learning.py`'deki `_count_rejections_for_content_type`

---

#### 4. Schema Doğrulama — Somut Aksiyon (B7)

> **Aksiyon:** Supabase dashboard'dan `jobs` ve `channels` tablolarının gerçek kolonlarını kontrol et.
> Bu düzeltmeler madde 3 (SQL güvenliği) ile aynı anda yapılabilir.

| Sorgu | Varsayılan Alan | Kontrol | Aksiyon |
|-------|-----------------|---------|---------|
| `get_pipeline_stats` | `jobs.updated_at` | `updated_at` var mı? | Yoksa `completed_at` kullan |
| `get_pipeline_stats` | `pipeline_audit_log.success` | Migration 004 ile eklendi | ✅ var |
| `DNA_STALE` trigger | `channels.name` | `name` mi `display_name` mi? | Hangisi varsa onu kullan |
| `DNA_STALE` trigger | `channels.updated_at` | Row updated_at mı, DNA updated_at mı? | Gerekirse `channel_dna->>'updated_at'` kullan |
| `compare_channels` | `jobs.channel_id` | `pipeline_audit_log`→`jobs` join doğru mu? | SQL'i test et |

---

#### 5. Message Router + run_agent use_tools Parametresi (C1)

**Sorun:** Tüm mesajlar tool loop'a giriyor. "Merhaba" Gemini Pro çağırıyor.

**Seçenek A (basit):** router.py'de sınıflandır, tool'suz Gemini çağır.
**Seçenek B (daha temiz — ÖNERİLEN):** `run_agent`'a `use_tools` parametresi ekle:

```python
# agent.py — run_agent imzası:
async def run_agent(
    user_message: str,
    session_id: str,
    conversation_history: list[dict],
    relevant_memories: list[dict],
    use_tools: bool = True,  # YENİ
) -> AsyncGenerator[dict, None]:
    ...
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=GEMINI_TOOLS if use_tools else None,  # KOŞULLU
        temperature=0.3,
    )
```

```python
# message_router.py (YENİ DOSYA):
import re

DIRECT_PATTERNS = [
    r'^(merhaba|selam|hey|hi|hello|naber|nasılsın)',
    r'^(teşekkür|sağol|eyvallah|thanks|thank you)',
    r'^(tamam|ok|evet|anladım|güzel|harika|süper)',
    r'^(kimsin|ne yapabilirsin|nasıl çalışıyorsun)',
]

DATA_KEYWORDS = [
    'kaç', 'göster', 'analiz', 'kontrol', 'bak', 'pipeline', 'klip', 'clip',
    'hata', 'error', 'score', 'puan', 'maliyet', 'cost', 'durum', 'status',
    'son', 'istatistik', 'stats', 'performance', 'channel', 'kanal', 'job',
    'dna', 'hafıza', 'memory', 'öneri', 'recommendation', 'log', 'deploy',
]

def should_use_tools(message: str) -> bool:
    msg = message.strip().lower()
    if len(msg.split()) < 4:
        for pat in DIRECT_PATTERNS:
            if re.match(pat, msg):
                return False
        if not any(k in msg for k in DATA_KEYWORDS):
            return False
    return True
```

```python
# router.py — _sse_generator içinde:
from app.director.message_router import should_use_tools
use_tools = should_use_tools(message)
async for event in run_agent(message, session_id, history, relevant_memories, use_tools=use_tools):
    ...
```

**Neden Seçenek B daha iyi:** SSE akışı, conversation persistence, memory kaydetme hepsi aynı kalır. Sadece Gemini tool mode değişir.

---

#### 6. Self-Analysis write_access Düzeltmesi (B11)

`channels` tablosu blocked listesinde ama `_update_channel_dna()` ona yazıyor. Yeni tablolar da eksik.

```python
"write_access": {
    "allowed": [
        "director_memory", "director_recommendations", "director_conversations",
        "director_events", "director_analyses", "director_decision_journal",
        "director_test_runs", "director_cross_module_signals",
        "channels.channel_dna (merge update — sadece dna alanı)",
    ],
    "blocked": ["jobs", "clips", "transcripts", "pipeline_audit_log", "channels (diğer alanlar)"],
}
```

---

#### 7. UNUSED_CLIPS Trigger Mantık Hatası (B8)

`is_successful = false` kullanıcı reddetmiş demek, editörde açılmamış demek değil.

```sql
WHERE quality_verdict IN ('pass', 'fixable')
AND is_successful IS NULL        -- feedback verilmemiş
AND is_published IS NULL         -- yayınlanmamış
AND created_at < now() - interval '3 days'   -- en az 3 gün geçmeli
AND created_at > now() - interval '14 days'
```

---

#### 8. _trigger_analysis Learn Skoru Bug Fix (B12)

**Mevcut sorun:**
```python
learn = 8 if total < 20 else 10
```
Az veri varken öğrenme ölçülemez — bu "düşük" değil "nötr" olmalı.

**Düzeltme:**
```python
# Yeterli veri yoksa nötr skor, yoksareal ölçüm
if total < 20:
    learn = 7  # nötr — ne yüksek ne düşük, henüz ölçülemiyor
else:
    # Gerçek öğrenme ölçümü: pass rate trend + DNA freshness
    # (scorer modülüne geçene kadar geçici olarak burada)
    trend = get_pass_rate_trend()
    learn = 12 if trend.get("trend") == "improving" else 7 if trend.get("trend") == "stable" else 4
    learn = min(15, learn)
```

---

### 📋 ORTA ÖNCELİK

---

#### 9. Result Truncation İyileştirme (B13)

Mevcut 8000 char hard cut önemli veri kaybedebilir:

```python
def _smart_truncate(result: Any, tool_name: str, max_chars: int = 6000) -> str:
    if isinstance(result, list) and len(result) > 20:
        return json.dumps({
            "total_count": len(result),
            "first_10": result[:10],
            "last_5": result[-5:],
            "note": f"{len(result)} sonuçtan 15'i gösteriliyor"
        }, ensure_ascii=False, default=str)
    result_str = json.dumps(result, ensure_ascii=False, default=str)
    if len(result_str) > max_chars:
        return result_str[:max_chars] + f"...[truncated, {len(result_str)} chars total]"
    return result_str
```

---

#### 10. Connection Pooling + Shutdown Handling (D6)

Her `_run_sql` çağrısında yeni TCP bağlantısı açılıyor. Her Director chat mesajı 3-5 yeni connection demek.

```python
# database.py:
from psycopg2 import pool as pg_pool

_connection_pool: pg_pool.SimpleConnectionPool | None = None

def _get_pool() -> pg_pool.SimpleConnectionPool:
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        _connection_pool = pg_pool.SimpleConnectionPool(
            minconn=1, maxconn=5,
            dsn=settings.DATABASE_URL,
            connect_timeout=5,
        )
    return _connection_pool

def _run_sql(sql: str, params: tuple = ()) -> list[dict]:
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '10s'")
            cur.execute(sql, params)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        pool.putconn(conn)
```

**Shutdown handling** — main.py lifespan'a eklenmeli:

```python
# main.py — lifespan yield'den sonra:
try:
    from app.director.tools.database import _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        print("[DB] Connection pool closed.")
except Exception:
    pass
```

> Olmadan Railway restart'larda "connection leak" uyarıları görülebilir.

---

#### 11. Recommendation Lifecycle (C6)

`director_recommendations` tablosu zamanla çöplüğe döner. Eksik:
- Kullanıcı "bunu uyguladım" veya "atla" diyemiyor
- 30+ gün pending kalan öneriler temizlenmiyor

**Mevcut `PATCH /director/recommendations/{id}` endpoint'i var** — ama frontend'de kullanılmıyor.

Eklenmesi gereken:
1. `POST /director/recommendations/{id}/apply` — status: applied + uygulama notu
2. `POST /director/cleanup-recommendations` — 30+ gün pending → archived
3. Frontend Recommendations listesine "Uygulandı / Atla" butonları

```python
# router.py'e eklenecek:
@router.post("/recommendations/{rec_id}/apply")
async def apply_recommendation(rec_id: str, note: str = ""):
    client = get_client()
    client.table("director_recommendations").update({
        "status": "applied",
        "dismissed_reason": note or None,
    }).eq("id", rec_id).execute()
    return {"ok": True}

@router.post("/cleanup-recommendations")
async def cleanup_stale_recommendations():
    """30+ gün pending kalan önerileri archive et."""
    rows = _run_sql("""
        UPDATE director_recommendations
        SET status = 'archived'
        WHERE status = 'pending'
          AND created_at < now() - interval '30 days'
        RETURNING id
    """)
    return {"archived": len(rows)}
```

---

#### 12. Learning Scope Genişletme + Hook Bağlantıları (D4)

**learning.py'ye eklenecek fonksiyonlar:**

```python
def on_clip_published(clip_id: str, youtube_video_id: str) -> None:
    """Klip yayına girdiğinde — content_type → yayınlandı sinyali."""
    # feedback.py → publish endpoint'i çağırır

def on_views_received(clip_id: str, views_48h: int, avd_pct: float) -> None:
    """48s görüntülenme verisi geldiğinde — gerçek performans feedback."""
    # views_48h > 1000 ve avd_pct > 50 → "bu content type çalışıyor" memory
    # views_48h < 100 → "yayınlandı ama tutmadı" → hafızaya yaz
    # feedback.py → performance endpoint'i çağırır

def on_editor_session_time(clip_id: str, session_duration_s: int) -> None:
    """Editörde geçirilen süre sinyali."""
    # NOT: Bu fonksiyon gerekmeyebilir.
    # Editor session süresi PostHog event'i olarak gelir.
    # Director bunu get_posthog_events tool'u ile zaten okuyabilir.
    # Ayrı hook yazmak yerine PostHog'dan çekme yeterli.
```

**Hook bağlantı noktaları:**
- `on_clip_published` → `feedback.py` publish endpoint'i (zaten var)
- `on_views_received` → `feedback.py` performance/collect endpoint'i (zaten var)
- `on_editor_session_time` → **PostHog event olarak gelir**, ayrı hook gerekmez

---

### 🔮 DÜŞÜK ÖNCELİK / GELECEK

---

#### READABLE_PATTERNS Enforcement (B10)

`tools/filesystem.py`'de `READABLE_PATTERNS` listesi tanımlı ama `read_file`, `list_files`, `search_codebase` içinde hiçbir yerde kontrol edilmiyor.

**Durum:** Şu an tehlikeli değil (`LOCKED_PATHS` çalışıyor) ama kod tutarsız.
**Seçenek A:** `READABLE_PATTERNS`'i kaldır, sadece `LOCKED_PATHS` ile çalış (daha temiz).
**Seçenek B:** Her `read_file` çağrısında path'in `READABLE_PATTERNS`'dan birine uyup uymadığını kontrol et.
**Şimdilik:** Düşük öncelik, tehlikeli değil.

#### Scorer Ayrı Modül (C4)

`analysis/scorer.py` — 5 boyutlu gerçek skor sistemi:
- Boyut 1: Teknik Sağlık (20p)
- Boyut 2: AI Karar Kalitesi (35p) — kullanıcı onay uyuşumu dahil
- Boyut 3: Çıktı Yapısal Kalitesi (25p)
- Boyut 4: Öğrenme ve Adaptasyon (15p)
- Boyut 5: Stratejik Olgunluk (5p)

#### Context Builder (C2)

Her konuşma başında snapshot: son 24h job count, pending rec count, health score.
Kullanıcı "ne durumdasın?" demeden Director bu bilgiyi bilmeli.

#### Yeni Proactive Trigger'lar (D5)

- `GEMINI_RATE_LIMIT_HIGH` — son 24s içinde 5+ rate limit
- `PIPELINE_DURATION_SPIKE` — son job normalden 2x uzun
- `MEMORY_GROWTH_WARNING` — director_memory 500+ kayıt → temizlik öner

#### Maliyet Projeksiyonu (C5)

- `project_monthly_cost()` — ay sonu tahmini
- `get_cost_per_clip()` — pass klip başına maliyet
- `get_cost_optimization_suggestions()` — Flash pre-screening önerisi

#### Capability Scan (Dinamik Erişim Haritası)

Startup'ta `capability_scan()` çalıştır → prompt'a inject et:
```python
def capability_scan() -> str:
    capabilities = []
    if Path(settings.PROJECT_ROOT / "docs").exists():
        capabilities.append("✅ docs/ erişilebilir")
    else:
        capabilities.append("❌ docs/ bulunamadı")
    ...
    return "\n".join(capabilities)
```
Şimdilik statik erişim haritası yeterli.

---

## BÖLÜM 3 — DOKUNULMAYACAK İYİ YAPILAR

- **Agent loop** (`run_agent`) — iteration, SSE yield, error handling ✅
- **Tool dispatcher** (`_dispatch_tool`) — merkezi mapping ✅
- **Events singleton** (`director_events`) — emit_sync + emit, never-raise ✅
- **Learning temel yapısı** — approve/reject → memory → recommendation ✅
- **Proactive framework** — spam önleme, emit + write_recommendation ✅
- **Memory araçları** — embedding + RPC fallback + history ✅
- **Filesystem güvenliği** — path traversal guard, locked paths ✅
- **Langfuse tracing** — her Gemini çağrısında, failure asla bloklamıyor ✅
- **Dış servis tool'ları** — langfuse, sentry, posthog, railway, deepgram, websearch ✅

---

## BÖLÜM 4 — SCHEMA DOĞRULAMA (B7)

> **Aksiyon:** Supabase → Table Editor'dan `jobs` ve `channels` kolonlarını kontrol et.
> SQL güvenliği (madde 3) düzeltilirken aynı anda yap.

| Sorgu | Varsayılan Alan | Kontrol | Aksiyon |
|-------|-----------------|---------|---------|
| `get_pipeline_stats` | `jobs.updated_at` | Var mı? | Yoksa `completed_at` kullan |
| `get_pipeline_stats` | `pipeline_audit_log.success` | Migration 004 ile eklendi | ✅ var |
| `DNA_STALE` trigger | `channels.name` | `name` mi `display_name` mi? | Hangisi varsa kullan |
| `DNA_STALE` trigger | `channels.updated_at` | Row updated_at mı, DNA updated_at mı? | Gerekirse `channel_dna->>'updated_at'` kullan |
| `compare_channels` | `jobs.channel_id` | `pipeline_audit_log`→`jobs` join doğru mu? | Test et |

---

## BÖLÜM 5 — UYGULAMA SIRASI ÖZET

```
HIZLI (30dk - 1 gün):
1. agent.py → SYSTEM_PROMPT başına "Araç Kuralları" + "Erişim Haritası" ekle
2. agent.py → run_agent'a use_tools parametresi ekle
3. director/message_router.py → yeni dosya, should_use_tools()
4. director/router.py → chat endpoint'inde message_router kullan
5. tools/self_analysis.py → write_access listesini güncelle
6. director/proactive.py → UNUSED_CLIPS SQL düzelt
7. agent.py → learn skoru bug fix (nötr = 7)

ORTA (1-3 gün):
8. agent.py → tool loop dedup + MAX_TOOL_CALLS tam implementasyon
9. tools/database.py → query_database dangerous keywords (UNION + comment + ;)
10. tools/database.py → _run_sql parametrize + connection pool + shutdown
11. Schema doğrulama → jobs.updated_at, channels.name kontrol
12. agent.py → _smart_truncate ile _result_summary güncelle
13. router.py → recommendation apply/cleanup endpoint'leri
14. learning.py → on_clip_published, on_views_received ekle

GELECEK:
15. Scorer ayrı modül (analysis/scorer.py)
16. Context builder
17. Yeni proactive trigger'lar
18. READABLE_PATTERNS kararı (enforce veya kaldır)
19. Maliyet projeksiyonu
```

---

*Geliştirme bittiğinde bu dosya silinecek, değişiklikler DIRECTOR_MODULE.md'ye işlenecek.*
