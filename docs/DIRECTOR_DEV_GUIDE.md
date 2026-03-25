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

### ✅ ÖNCE YAPILACAK — TÜM MADDELER TAMAMLANDI

---

#### ✅ 1. System Prompt: Araç Kuralları + Erişim Haritası (B1 + B3)

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

#### ✅ 2. Tool Loop Dedup Guard — TAM İMPLEMENTASYON (B2)

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

#### ✅ 3. SQL Güvenliği — UNION + Comment + Parametrize (B5 + B6)

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

#### ✅ 4. Schema Doğrulama — Somut Aksiyon (B7)

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

#### ✅ 5. Message Router + run_agent use_tools Parametresi (C1)

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

#### ✅ 6. Self-Analysis write_access Düzeltmesi (B11)

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

#### ✅ 7. UNUSED_CLIPS Trigger Mantık Hatası (B8)

`is_successful = false` kullanıcı reddetmiş demek, editörde açılmamış demek değil.

```sql
WHERE quality_verdict IN ('pass', 'fixable')
AND is_successful IS NULL        -- feedback verilmemiş
AND is_published IS NULL         -- yayınlanmamış
AND created_at < now() - interval '3 days'   -- en az 3 gün geçmeli
AND created_at > now() - interval '14 days'
```

---

#### ✅ 8. _trigger_analysis Learn Skoru Bug Fix (B12)

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

#### ✅ 9. Result Truncation İyileştirme (B13)

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

#### ✅ 10. Connection Pooling + Shutdown Handling (D6)

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

#### ✅ 11. Recommendation Lifecycle (C6)

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

#### ✅ 12. Learning Scope Genişletme + Hook Bağlantıları (D4)

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

---

## BÖLÜM 6 — 3. KISIM ANALİZİ: YENİ KAPASİTE ÖNERİLERİ

> Kaynak: Üçüncü tur AI analiz raporu (KISIM 1-5). Kendi kod analizimle doğrulandı.
>
> **MİMARİ UYARI — PIPELINE SENKRON:** `video_worker.py` → `start_pipeline()` → `run_pipeline()` SENKRON çağrı (RQ worker blokiyor). `asyncio.create_task()` sadece mevcut event loop varsa çalışır; yoksa `RuntimeError` fırlatır. Aşağıdaki `create_test_job()` kodu her iki durumu da handle ediyor — önce `create_task` dene, `RuntimeError` gelirse `threading.Thread` aç.
>
> **`is_test_run` KOLONU:** `jobs` tablosunda YOK. Migration 006 gerekli (aşağıda).

---

### KISIM 1 — KRİTİK EKSİK YETENEKLER (4 Kritik)

---

#### ✅ KRİTİK 1: Pipeline Çalıştırma ve Test Yeteneği

**Dosya:** `director/tools/pipeline_executor.py` (YENİ)

**Mimari not:** `asyncio.create_task()` önce deneniyor; `RuntimeError` gelirse thread fallback devreye giriyor. Bu pattern RQ context'inde güvenli.

**Migration önce yapılmalı:**
```sql
-- migrations/006_jobs_test_run.sql
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_test_run BOOLEAN DEFAULT false;
```

```python
# director/tools/pipeline_executor.py

"""
Director Pipeline Executor — test amaçlı pipeline çalıştırma.
Director bu tool ile:
1. Mevcut bir video URL'si veya upload edilmiş video ile test job'ı oluşturur
2. Pipeline'ı başlatır (is_test_run=True flag'i ile)
3. Her adımın sonucunu takip eder
4. Tamamlandığında tam analiz yapar
"""

from app.services.supabase_client import get_client
from app.director.events import director_events
from app.director.tools.database import _run_sql


def create_test_job(
    video_url: str | None = None,
    video_path: str | None = None,
    channel_id: str = "speedy_cast",
    title: str = "Director Test Run",
    guest_name: str | None = None,
) -> dict:
    """
    Test amaçlı pipeline job'ı oluşturur ve başlatır.
    video_url: R2'deki mevcut bir video URL'si
    channel_id: Test edilecek kanal
    Returns: {job_id, status}
    """
    try:
        if not video_url and not video_path:
            from app.config import settings
            test_video = getattr(settings, 'DIRECTOR_TEST_VIDEO_URL', None)
            if not test_video:
                return {
                    "error": "Test videosu belirtilmedi. "
                    "video_url parametresi ver veya DIRECTOR_TEST_VIDEO_URL env var'ı ayarla."
                }
            video_url = test_video

        client = get_client()

        job_data = {
            "channel_id": channel_id,
            "video_title": f"[TEST] {title}",
            "guest_name": guest_name,
            "status": "queued",
            "is_test_run": True,
        }
        if video_path:
            job_data["video_path"] = video_path

        res = client.table("jobs").insert(job_data).execute()
        if not res.data:
            return {"error": "Job oluşturulamadı"}

        job_id = res.data[0]["id"]

        # Pipeline'ı başlat: önce async dene, RuntimeError gelirse thread aç
        import asyncio
        from app.pipeline.orchestrator import run_pipeline

        try:
            asyncio.create_task(
                _run_pipeline_async(job_id, video_url or video_path,
                                    title, guest_name, channel_id)
            )
        except RuntimeError:
            import threading
            thread = threading.Thread(
                target=_run_pipeline_sync,
                args=(job_id, video_url or video_path, title, guest_name, channel_id)
            )
            thread.daemon = True
            thread.start()

        director_events.emit_sync(
            module="director", event="test_pipeline_started",
            payload={"job_id": job_id, "channel_id": channel_id, "is_test_run": True},
            channel_id=channel_id,
        )

        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "message": (f"Test pipeline başlatıldı. Job ID: {job_id}. "
                        f"Durumu kontrol etmek için: get_test_pipeline_status('{job_id}')")
        }

    except Exception as e:
        return {"error": f"Test pipeline oluşturma hatası: {e}"}


async def _run_pipeline_async(job_id, video_source, title, guest_name, channel_id):
    try:
        from app.pipeline.orchestrator import run_pipeline
        await run_pipeline(job_id, video_source, title, guest_name, channel_id)
    except Exception as e:
        print(f"[Director] Test pipeline failed: {e}")
        director_events.emit_sync(
            module="director", event="test_pipeline_failed",
            payload={"job_id": job_id, "error": str(e)}
        )


def _run_pipeline_sync(job_id, video_source, title, guest_name, channel_id):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            _run_pipeline_async(job_id, video_source, title, guest_name, channel_id)
        )
    finally:
        loop.close()


def get_test_pipeline_status(job_id: str) -> dict:
    """Çalışan veya tamamlanan test pipeline'ın detaylı durumu."""
    try:
        client = get_client()
        job_res = client.table("jobs").select("*").eq("id", job_id).single().execute()
        if not job_res.data:
            return {"error": f"Job {job_id} bulunamadı"}

        job = job_res.data

        steps = _run_sql("""
            SELECT step_name, step_number, status, duration_ms,
                   output_summary, error_message, token_usage, created_at
            FROM pipeline_audit_log
            WHERE job_id = %s
            ORDER BY step_number ASC
        """, (job_id,))

        clips = []
        if job.get("status") in ("completed", "partial"):
            clip_res = (client.table("clips")
                .select("clip_index,content_type,quality_verdict,overall_confidence,"
                        "standalone_score,hook_score,arc_score,hook_text,"
                        "suggested_title,duration_s,file_url")
                .eq("job_id", job_id)
                .order("clip_index")
                .execute())
            clips = clip_res.data or []

        total_cost = sum(
            float((s.get("token_usage") or {}).get("cost_usd", 0) or 0)
            for s in steps
        )
        total_duration = sum(int(s.get("duration_ms") or 0) for s in steps)
        pass_clips = [c for c in clips if c.get("quality_verdict") == "pass"]

        return {
            "job_id": job_id,
            "status": job.get("status"),
            "current_step": job.get("current_step"),
            "progress_pct": job.get("progress_pct", 0),
            "total_duration_min": round(total_duration / 60000, 1),
            "total_cost_usd": round(total_cost, 4),
            "steps": [
                {
                    "name": s.get("step_name"),
                    "status": s.get("status"),
                    "duration_s": round(int(s.get("duration_ms") or 0) / 1000, 1),
                    "error": s.get("error_message"),
                }
                for s in steps
            ],
            "clips_summary": {
                "total": len(clips),
                "pass": len(pass_clips),
                "fail": len(clips) - len(pass_clips),
                "avg_confidence": (
                    round(sum(c.get("overall_confidence", 0) or 0 for c in clips) / len(clips), 2)
                    if clips else None
                ),
            },
            "clips": clips,
            "is_test_run": job.get("is_test_run", False),
        }

    except Exception as e:
        return {"error": f"Status check hatası: {e}"}


def get_active_pipelines() -> dict:
    """Şu an çalışan tüm pipeline'ları listele."""
    try:
        rows = _run_sql("""
            SELECT id, channel_id, video_title, status, current_step,
                   progress_pct, started_at, is_test_run
            FROM jobs
            WHERE status IN ('queued', 'processing', 'awaiting_speaker_confirm')
            ORDER BY created_at DESC
            LIMIT 10
        """)
        return {"active_count": len(rows), "pipelines": rows}
    except Exception as e:
        return {"error": str(e)}


def analyze_test_results(job_id: str) -> dict:
    """Tamamlanmış test pipeline'ın derinlemesine analizi."""
    try:
        status = get_test_pipeline_status(job_id)
        if status.get("error"):
            return status

        if status.get("status") not in ("completed", "partial"):
            return {
                "error": f"Pipeline henüz tamamlanmadı. Durum: {status.get('status')}",
                "current_step": status.get("current_step"),
                "progress": status.get("progress_pct"),
            }

        clips = status.get("clips", [])
        clips_summary = status.get("clips_summary", {})
        pass_rate = 0
        if clips_summary.get("total", 0) > 0:
            pass_rate = clips_summary["pass"] / clips_summary["total"] * 100

        recommendations = []
        step_analysis = []
        for step in status.get("steps", []):
            note = {"name": step["name"], "duration_s": step["duration_s"], "status": step["status"]}
            if "s05" in (step.get("name") or "") and step["duration_s"] > 180:
                note["warning"] = f"S05 normalden yavaş: {step['duration_s']}s (hedef: <180s)"
                recommendations.append("S05 yavaş — video boyutu veya rate limit kontrol edilmeli.")
            if step.get("error"):
                note["error"] = step["error"]
            step_analysis.append(note)

        overall = (
            "İYİ — Pass rate ve süre hedeflerde." if pass_rate >= 50 and status.get("total_duration_min", 99) < 8
            else "ORTA — Pass rate kabul edilebilir ama iyileştirme var." if pass_rate >= 30
            else "ZAYIF — Pass rate düşük, S05/S06 prompt veya DNA incelenmeli."
        )

        from app.director.tools.memory import save_memory
        save_memory(
            content=(f"Test pipeline ({job_id}): {overall} "
                     f"Pass rate: %{pass_rate:.1f}, {len(clips)} klip, "
                     f"${status.get('total_cost_usd', 0):.4f} maliyet."),
            type="learning", tags=["test_run", "pipeline_analysis"], source="auto",
        )

        return {
            "job_id": job_id,
            "overall_assessment": overall,
            "step_analysis": step_analysis,
            "clip_analysis": {
                "pass_rate": round(pass_rate, 1),
                "total_clips": clips_summary.get("total", 0),
                "pass_clips": clips_summary.get("pass", 0),
                "avg_confidence": clips_summary.get("avg_confidence"),
                "content_types": list(set(c.get("content_type", "unknown") for c in clips)),
            },
            "cost_analysis": {
                "total_cost_usd": status.get("total_cost_usd", 0),
                "cost_per_clip": round(status.get("total_cost_usd", 0) / max(len(clips), 1), 4),
                "total_duration_min": status.get("total_duration_min", 0),
            },
            "recommendations": recommendations,
        }

    except Exception as e:
        return {"error": f"Analiz hatası: {e}"}
```

**Agent tool deklarasyonları:**
```python
types.FunctionDeclaration(
    name="create_test_pipeline",
    description="Start a test pipeline run with a video (is_test_run=True). "
                "Use get_test_pipeline_status to monitor progress.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "channel_id": types.Schema(type="STRING", description="Channel. Default: speedy_cast"),
            "title": types.Schema(type="STRING", description="Test run title"),
            "guest_name": types.Schema(type="STRING"),
            "video_url": types.Schema(type="STRING", description="R2 URL or leave empty for default test video"),
        },
    )
),
types.FunctionDeclaration(
    name="get_test_pipeline_status",
    description="Get detailed status of a running or completed test pipeline.",
    parameters=types.Schema(
        type="OBJECT",
        properties={"job_id": types.Schema(type="STRING")},
        required=["job_id"]
    )
),
types.FunctionDeclaration(
    name="analyze_test_results",
    description="Deep analysis of a completed test pipeline.",
    parameters=types.Schema(
        type="OBJECT",
        properties={"job_id": types.Schema(type="STRING")},
        required=["job_id"]
    )
),
types.FunctionDeclaration(
    name="get_active_pipelines",
    description="List all currently running or queued pipelines.",
    parameters=types.Schema(type="OBJECT", properties={})
),
```

**Dispatcher:**
```python
elif name == "create_test_pipeline":
    from app.director.tools.pipeline_executor import create_test_job
    return create_test_job(video_url=args.get("video_url"), channel_id=args.get("channel_id", "speedy_cast"),
                           title=args.get("title", "Director Test Run"), guest_name=args.get("guest_name"))
elif name == "get_test_pipeline_status":
    from app.director.tools.pipeline_executor import get_test_pipeline_status
    return get_test_pipeline_status(args["job_id"])
elif name == "analyze_test_results":
    from app.director.tools.pipeline_executor import analyze_test_results
    return analyze_test_results(args["job_id"])
elif name == "get_active_pipelines":
    from app.director.tools.pipeline_executor import get_active_pipelines
    return get_active_pipelines()
```

**Güvenlik:**
- Test pipeline'lar `is_test_run = True` flag taşır
- Günde max 5 test pipeline (config.py limiti)
- Speaker confirmation test modunda otomatik atlanmalı (orchestrator'a `is_test_run` kontrolü ekle)

---

#### ✅ KRİTİK 2: Uzun Vadeli Planlama ve Tahmin

**Dosya:** `director/predictive/forecaster.py` (YENİ)

```python
# director/predictive/forecaster.py

"""
Director Forecasting Engine — basit istatistiksel projeksiyonlar.
GPU gerektirmez. Linear regression ve moving average ile çalışır.
"""

import statistics
from datetime import datetime, timezone
from app.director.tools.database import _run_sql


def forecast_monthly_cost() -> dict:
    """
    Bu ayki harcama hızına göre ay sonu maliyet projeksiyonu.
    Son 14 günün günlük ortalamasından hesaplar.
    """
    try:
        rows = _run_sql("""
            SELECT
                DATE_TRUNC('day', created_at)::DATE AS date,
                SUM(COALESCE((token_usage->>'cost_usd')::FLOAT, 0)) AS daily_cost
            FROM pipeline_audit_log
            WHERE created_at > now() - interval '14 days'
              AND token_usage IS NOT NULL AND token_usage::text != '{}'
            GROUP BY 1
            ORDER BY 1
        """)

        if len(rows) < 3:
            return {"error": "Yeterli veri yok (minimum 3 gün gerekli)"}

        daily_costs = [float(r.get("daily_cost") or 0) for r in rows]
        avg_daily = statistics.mean(daily_costs)
        std_daily = statistics.stdev(daily_costs) if len(daily_costs) > 1 else 0

        now = datetime.now(timezone.utc)
        days_elapsed = min(now.day, len(rows))
        days_remaining = 30 - days_elapsed
        current_month_total = sum(daily_costs[-days_elapsed:]) if days_elapsed > 0 else 0
        projected_total = current_month_total + avg_daily * days_remaining

        # Deepgram maliyeti
        from app.director.tools.deepgram import get_deepgram_usage
        deepgram = get_deepgram_usage(14)
        deepgram_daily = 0
        if not deepgram.get("error"):
            deepgram_daily = deepgram.get("totals", {}).get("estimated_cost_usd", 0) / 14

        railway_monthly = 5.0  # $5/ay varsayılan
        grand_total = projected_total + (deepgram_daily * days_remaining) + railway_monthly

        return {
            "gemini_cost": {
                "current_month_so_far": round(current_month_total, 2),
                "avg_daily": round(avg_daily, 4),
                "projected_month_end": round(projected_total, 2),
                "confidence_range": {
                    "low": round(projected_total - std_daily * days_remaining * 0.5, 2),
                    "high": round(projected_total + std_daily * days_remaining * 0.5, 2),
                },
            },
            "deepgram_cost": {
                "avg_daily": round(deepgram_daily, 4),
                "projected_remaining": round(deepgram_daily * days_remaining, 2),
            },
            "railway_cost": railway_monthly,
            "grand_total_projected": round(grand_total, 2),
            "days_elapsed": days_elapsed,
            "days_remaining": days_remaining,
        }

    except Exception as e:
        return {"error": str(e)}


def forecast_pipeline_volume() -> dict:
    """Pipeline kullanım trendi ve projeksiyon."""
    try:
        rows = _run_sql("""
            SELECT
                COUNT(*) FILTER (WHERE created_at > now() - interval '30 days') AS current_30,
                COUNT(*) FILTER (WHERE created_at BETWEEN now() - interval '60 days'
                                 AND now() - interval '30 days') AS previous_30,
                COUNT(*) FILTER (WHERE created_at > now() - interval '7 days') AS current_7
            FROM jobs
        """)
        if not rows:
            return {"error": "Veri yok"}

        r = rows[0]
        current_30 = int(r.get("current_30") or 0)
        previous_30 = int(r.get("previous_30") or 0)
        current_7 = int(r.get("current_7") or 0)
        growth_rate = ((current_30 - previous_30) / max(previous_30, 1)) * 100
        projected_next_30 = round(current_7 * 4.3)

        return {
            "last_30_days": current_30,
            "previous_30_days": previous_30,
            "last_7_days": current_7,
            "growth_rate_pct": round(growth_rate, 1),
            "trend": "artış" if growth_rate > 10 else "düşüş" if growth_rate < -10 else "stabil",
            "projected_next_30_days": projected_next_30,
            "projected_clips_next_30": round(projected_next_30 * 3.5),
        }

    except Exception as e:
        return {"error": str(e)}


def predict_failure_risk(video_duration_s: float | None = None,
                          channel_id: str | None = None) -> dict:
    """Yeni bir pipeline için başarısızlık risk tahmini."""
    try:
        rows = _run_sql("""
            SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'failed') AS failed
            FROM jobs WHERE created_at > now() - interval '90 days'
        """)
        if not rows:
            return {"risk": "bilinmiyor", "reason": "Yeterli veri yok"}

        r = rows[0]
        total = int(r.get("total") or 0)
        failed = int(r.get("failed") or 0)
        base_fail_rate = (failed / max(total, 1)) * 100
        risk_score = base_fail_rate
        risk_factors = []

        if video_duration_s and video_duration_s > 5400:
            risk_score += 30
            risk_factors.append(f"Video {video_duration_s/60:.0f} dakika — çok uzun, S05 timeout riski yüksek")
        elif video_duration_s and video_duration_s > 3600:
            risk_score += 15
            risk_factors.append(f"Video {video_duration_s/60:.0f} dakika — uzun videolarda timeout riski artıyor")

        if channel_id:
            ch_rows = _run_sql("""
                SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'failed') AS failed
                FROM jobs WHERE channel_id = %s AND created_at > now() - interval '30 days'
            """, (channel_id,))
            if ch_rows:
                ch_total = int(ch_rows[0].get("total") or 0)
                ch_failed = int(ch_rows[0].get("failed") or 0)
                if ch_total >= 3 and (ch_failed / ch_total * 100) > base_fail_rate + 10:
                    risk_score += 10
                    risk_factors.append(f"Bu kanal son 30 günde %{ch_failed/ch_total*100:.0f} fail rate")

        risk_level = (
            "düşük" if risk_score < 15 else "orta" if risk_score < 30
            else "yüksek" if risk_score < 50 else "çok yüksek"
        )
        return {
            "risk_level": risk_level,
            "risk_score": round(risk_score, 1),
            "base_fail_rate": round(base_fail_rate, 1),
            "risk_factors": risk_factors,
            "recommendation": (
                "Normal şartlarda çalıştırılabilir." if risk_score < 15
                else "Dikkatli ol, logları takip et." if risk_score < 30
                else "Riskli — gece saatlerinde dene." if risk_score < 50
                else "Çok riskli — video'yu trim et veya farklı saatte dene."
            ),
        }

    except Exception as e:
        return {"error": str(e)}


def forecast_capacity() -> dict:
    """Sistem kapasite projeksiyonu — DB boyut trendi."""
    try:
        rows = _run_sql("""
            SELECT
                (SELECT COUNT(*) FROM director_events) AS event_count,
                (SELECT COUNT(*) FROM director_memory) AS memory_count,
                (SELECT COUNT(*) FROM director_conversations) AS conversation_count,
                (SELECT COUNT(*) FROM director_recommendations) AS recommendation_count,
                (SELECT COUNT(*) FROM clips) AS total_clips,
                (SELECT COUNT(*) FROM jobs) AS total_jobs,
                (SELECT COUNT(*) FROM pipeline_audit_log) AS audit_log_count
        """)
        if not rows:
            return {"error": "Veri okunamadı"}

        r = rows[0]
        warnings = []
        if int(r.get("memory_count") or 0) > 500:
            warnings.append(f"director_memory {r['memory_count']} kayıt — temizlik düşünülmeli")
        if int(r.get("event_count") or 0) > 10000:
            warnings.append(f"director_events {r['event_count']} kayıt — arşivleme düşünülmeli")
        if int(r.get("audit_log_count") or 0) > 50000:
            warnings.append(f"pipeline_audit_log {r['audit_log_count']} kayıt — cleanup gerekli")

        return {
            "table_sizes": {k: int(v or 0) for k, v in r.items()},
            "warnings": warnings,
            "status": "healthy" if not warnings else "attention_needed",
        }

    except Exception as e:
        return {"error": str(e)}
```

**Tool deklarasyonları:**
```python
types.FunctionDeclaration(name="forecast_monthly_cost",
    description="Project end-of-month cost (Gemini + Deepgram + Railway).",
    parameters=types.Schema(type="OBJECT", properties={})),
types.FunctionDeclaration(name="forecast_pipeline_volume",
    description="Pipeline usage trend and next-30-day projection.",
    parameters=types.Schema(type="OBJECT", properties={})),
types.FunctionDeclaration(name="predict_failure_risk",
    description="Predict pipeline failure risk based on video duration and channel history.",
    parameters=types.Schema(type="OBJECT", properties={
        "video_duration_s": types.Schema(type="NUMBER"),
        "channel_id": types.Schema(type="STRING"),
    })),
types.FunctionDeclaration(name="forecast_capacity",
    description="Check system capacity — DB table sizes and growth warnings.",
    parameters=types.Schema(type="OBJECT", properties={})),
```

---

#### ✅ KRİTİK 3: Gerçek Zamanlı Pipeline İzleme

`get_active_pipelines()` zaten KRİTİK 1'deki `pipeline_executor.py`'e dahil edildi.

**Polling yaklaşımı tercih sebebi:** WebSocket stream Railway CPU ortamında ağır. Pipeline 5-10 dakika sürdüğü için saniye bazlı izleme gerekmez — Director `get_test_pipeline_status`'u birkaç kez çağırarak ilerlemeyi takip eder.

---

#### ✅ KRİTİK 4: A/B Test Çalıştırma

**Dosya:** `director/tools/ab_test.py` (YENİ)

```python
# director/tools/ab_test.py

"""
Director A/B Test Runner — aynı videoyu iki farklı konfigürasyonla çalıştırıp karşılaştır.
"""

from app.director.tools.pipeline_executor import create_test_job, get_test_pipeline_status
from app.director.tools.memory import save_memory
from app.director.events import director_events
from app.services.supabase_client import get_client


def start_ab_test(
    test_name: str,
    channel_id: str = "speedy_cast",
    video_url: str | None = None,
    description: str = "",
) -> dict:
    """
    A/B test başlat — aynı video ile iki pipeline paralel çalıştırır.
    Gerçek prompt A/B test için prompt_lab modülü gerekir (gelecek sprint).
    """
    try:
        client = get_client()

        res = client.table("director_test_runs").insert({
            "test_name": test_name,
            "channel_id": channel_id,
            "description": description,
            "status": "running",
            "params": {"video_url": video_url, "type": "ab_test"},
        }).execute()
        test_id = res.data[0]["id"] if res.data else None

        run_a = create_test_job(video_url=video_url, channel_id=channel_id,
                                title=f"[A/B Test A] {test_name}")
        if run_a.get("error"):
            return {"error": f"Run A başlatılamadı: {run_a['error']}"}

        run_b = create_test_job(video_url=video_url, channel_id=channel_id,
                                title=f"[A/B Test B] {test_name}")
        if run_b.get("error"):
            return {"error": f"Run B başlatılamadı: {run_b['error']}"}

        if test_id:
            client.table("director_test_runs").update({
                "params": {"video_url": video_url, "type": "ab_test",
                           "run_a_job_id": run_a["job_id"], "run_b_job_id": run_b["job_id"]},
            }).eq("id", test_id).execute()

        director_events.emit_sync(module="director", event="ab_test_started",
            payload={"test_id": test_id, "test_name": test_name,
                     "run_a_job_id": run_a["job_id"], "run_b_job_id": run_b["job_id"]})

        return {
            "ok": True, "test_id": test_id, "test_name": test_name,
            "run_a_job_id": run_a["job_id"], "run_b_job_id": run_b["job_id"],
            "message": (f"A/B test başlatıldı. İki pipeline paralel çalışıyor.\n"
                        f"Tamamlandığında: compare_ab_test('{test_id}')"),
        }

    except Exception as e:
        return {"error": str(e)}


def compare_ab_test(test_id: str) -> dict:
    """Tamamlanmış A/B test'in iki run'ını karşılaştır."""
    try:
        client = get_client()
        test_res = client.table("director_test_runs").select("*").eq("id", test_id).single().execute()
        if not test_res.data:
            return {"error": f"Test {test_id} bulunamadı"}

        params = test_res.data.get("params") or {}
        run_a_id = params.get("run_a_job_id")
        run_b_id = params.get("run_b_job_id")
        if not run_a_id or not run_b_id:
            return {"error": "Test'te run job_id bulunamadı"}

        status_a = get_test_pipeline_status(run_a_id)
        status_b = get_test_pipeline_status(run_b_id)

        if status_a.get("status") != "completed" or status_b.get("status") != "completed":
            return {"error": "Her iki run da tamamlanmalı",
                    "run_a_status": status_a.get("status"), "run_b_status": status_b.get("status")}

        def _metrics(status):
            c = status.get("clips_summary", {})
            total = c.get("total", 0)
            passed = c.get("pass", 0)
            return {"total_clips": total, "pass_clips": passed,
                    "pass_rate": round(passed / max(total, 1) * 100, 1),
                    "avg_confidence": c.get("avg_confidence"),
                    "total_cost_usd": status.get("total_cost_usd", 0),
                    "total_duration_min": status.get("total_duration_min", 0)}

        ma = _metrics(status_a)
        mb = _metrics(status_b)

        if ma["pass_rate"] > mb["pass_rate"] + 5:
            winner, reason = "A", f"Run A %{ma['pass_rate']} vs Run B %{mb['pass_rate']} pass rate"
        elif mb["pass_rate"] > ma["pass_rate"] + 5:
            winner, reason = "B", f"Run B %{mb['pass_rate']} vs Run A %{ma['pass_rate']} pass rate"
        elif ma["total_cost_usd"] < mb["total_cost_usd"] * 0.8:
            winner, reason = "A", "Pass rate benzer ama Run A daha ucuz"
        elif mb["total_cost_usd"] < ma["total_cost_usd"] * 0.8:
            winner, reason = "B", "Pass rate benzer ama Run B daha ucuz"
        else:
            winner, reason = "berabere", "Anlamlı fark yok"

        comparison = {
            "test_id": test_id, "test_name": test_res.data.get("test_name"),
            "run_a": {"job_id": run_a_id, **ma},
            "run_b": {"job_id": run_b_id, **mb},
            "winner": winner, "reason": reason,
            "deltas": {
                "pass_rate_diff": round(ma["pass_rate"] - mb["pass_rate"], 1),
                "cost_diff_usd": round(ma["total_cost_usd"] - mb["total_cost_usd"], 4),
            },
        }

        client.table("director_test_runs").update(
            {"status": "completed", "result": comparison}
        ).eq("id", test_id).execute()

        save_memory(
            content=(f"A/B Test '{test_res.data.get('test_name')}': Winner={winner}. {reason}. "
                     f"A: %{ma['pass_rate']} pass. B: %{mb['pass_rate']} pass."),
            type="learning", tags=["ab_test"], source="auto",
        )
        return comparison

    except Exception as e:
        return {"error": str(e)}
```

---

### KISIM 2 — 11 GENİŞLEME MODÜLÜ (DURUM ANALİZİ)

> Her modülün mevcut durumu koda bakılarak kontrol edildi.

| # | Modül | Durum | Aksiyon |
|---|-------|-------|---------|
| 5.1 | **Prompt Lab** | ✅ YAPILDI | `GET/POST /director/prompt-lab` + activate endpoint var |
| 5.2 | **Predictive Layer** (Forecaster) | ✅ YAPILDI | `forecaster.py` oluşturuldu + agent entegrasyonu |
| 5.3 | **Execution Planner** | ✅ YAPILDI | `execution_planner.py` + create_execution_plan tool |
| 5.4 | **Dependency Graph** | ✅ YAPILDI | `dependency_graph.py` + check_dependency_impact + cross-module signals + router endpoint |
| 5.5 | **Decision Journal** | ✅ YAPILDI | Migration 004 + endpoints + frontend tab var |
| 5.6 | **Multi-Channel Intelligence** | ✅ YAPILDI | `compare_channels()` database.py'de var |
| 5.7 | **Editor Intelligence** | ✅ YAPILDI | `editor_intelligence.py` + engagement stats + conversion rate + agent entegrasyonu |
| 5.8 | **Notifications/Telegram** | ✅ YAPILDI | `notifier.py` + Telegram push (pipeline fail, cost spike, perf drop, rate limit, weekly digest) |
| 5.9 | **Dashboard Backend** | ✅ YAPILDI | `GET /director/dashboard` endpoint var |
| 5.10 | **Pipeline Event Hooks** | ✅ YAPILDI | S05/S06/S08/error hookları eklendi |
| 5.11 | **Model Router** | ✅ YAPILDI | `model_router.py` oluşturuldu + Flash/Pro seçimi |

---

#### 5.3 Execution Planner

Director bir öneri verdiğinde sadece "ne" değil "nasıl" da söyleyen sistem.

**Tool:** `create_execution_plan(recommendation_id)`

Adım adım plan üretir:
```python
# Çıktı formatı:
{
  "recommendation_id": "...",
  "steps": [
    {"order": 1, "file": "backend/app/pipeline/steps/s05_unified_discovery.py",
     "action": "build_channel_context() fonksiyonuna BAŞARISIZ PATTERNLAR bölümü ekle",
     "risk": "düşük"},
    {"order": 2, "action": "create_test_pipeline ile test et"},
    {"order": 3, "file": "docs/MODULE_1_CLIP_EXTRACTOR.md", "action": "S05 bölümünü güncelle"},
  ],
  "total_risk": "düşük",
  "expected_impact": "+4-6 puan pass rate artışı",
}
```

---

#### ✅ 5.4 Dependency Graph

```python
# router.py'e eklenecek:
@router.get("/cross-module-graph")
async def get_cross_module_graph(channel_id: str = None):
    """M1→M2 ve M2→M1 sinyal akışını grafik olarak döndür."""
    # director_cross_module_signals tablosundan group by source/target/event_type
```

**Hardcoded bağımlılık haritası** — `director/dependency_graph.py` (YENİ):
```python
DEPENDENCY_MAP = {
    "r2_storage": {"used_by": ["s08_export", "editor_reframe", "clip_playback"],
                   "impact_if_down": "KRİTİK — yeni klip yüklenemez, editor çalışmaz"},
    "deepgram":   {"used_by": ["s02_transcribe"],
                   "impact_if_down": "YÜKSEK — transkripsiyon durur"},
    "gemini_pro": {"used_by": ["s05_discovery", "s06_evaluation", "director_chat"],
                   "impact_if_down": "KRİTİK — klip keşfi ve Director durur"},
    "supabase":   {"used_by": ["tüm sistem"],
                   "impact_if_down": "KRİTİK — hiçbir şey çalışmaz"},
    "channel_dna":{"used_by": ["s05_discovery", "s06_evaluation"],
                   "impact_if_down": "YÜKSEK — klip seçimi rastgele olur"},
}
```
**Tool:** `check_dependency_impact(component)` — bir serviste sorun görüldüğünde etki analizi.

---

#### ✅ 5.7 Editor Intelligence

```python
# director/tools/editor_intelligence.py (YENİ)
def get_editor_engagement_stats(channel_id: str) -> dict:
    """Hangi klip tipleri editörde daha çok açılıyor?"""
    return _run_sql("""
        SELECT payload->>'quality_verdict' AS verdict,
               COUNT(*) AS open_count,
               COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS pct
        FROM director_cross_module_signals
        WHERE channel_id = %s AND event_type = 'clip_opened_in_editor'
          AND created_at > now() - interval '30 days'
        GROUP BY 1
    """, (channel_id,))

def get_clips_opened_but_not_published(channel_id: str) -> list:
    """Editörde açıldı ama yayınlanmadı."""
    return _run_sql("""
        SELECT c.id, c.title, c.quality_verdict, c.created_at
        FROM clips c
        JOIN director_cross_module_signals s ON s.payload->>'clip_id' = c.id::text
        WHERE c.channel_id = %s AND s.event_type = 'clip_opened_in_editor'
          AND c.is_published IS NULL AND c.created_at > now() - interval '14 days'
        ORDER BY c.created_at DESC
    """, (channel_id,))
```

---

#### 5.8 Notifications — Gerçek Push

`send_notification` şu an sadece `director_events`'a yazıyor. Gerçek Telegram push için:

```python
# director/notifier.py (YENİ — opsiyonel, httpx YERINE stdlib kullan Railway uyumu için)
import urllib.request
import json

def send_telegram(message: str) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return {"ok": False, "reason": "Telegram env vars eksik"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())
```

Hangi olaylar bildirim gönderir: pipeline failed, cost spike, performance drop, weekly digest.

> **Öncelik düşük** — `director_events` tablosundan frontend polling şimdilik yeterli.

---

#### ✅ 5.10 Pipeline Event Hooks — Tamamlama

Mevcut: `clips_ready_for_editor`. Eksik hooklar (`orchestrator.py` / ilgili step dosyalarına):

```python
# S05 sonunda (s05_unified_discovery.py):
director_events.emit_sync(
    module="module_1", event="s05_discovery_completed",
    payload={"job_id": job_id, "candidate_count": len(candidates),
             "duration_ms": elapsed_ms, "fallback_mode": fallback_mode},
)

# S06 sonunda (s06_batch_evaluation.py):
director_events.emit_sync(
    module="module_1", event="s06_evaluation_completed",
    payload={"job_id": job_id, "pass_count": pass_count, "fail_count": fail_count,
             "avg_standalone": avg_standalone, "duration_ms": elapsed_ms},
)

# S08 sonunda (s08_export.py):
director_events.emit_sync(
    module="module_1", event="s08_export_completed",
    payload={"job_id": job_id, "exported_count": exported, "r2_upload_failures": r2_failures},
)

# Pipeline hatası (orchestrator):
director_events.emit_sync(
    module="module_1", event="pipeline_error",
    payload={"job_id": job_id, "step": step_name, "error": str(e)},
)
```

**Kural:** Bu hooklar asenkron ve non-blocking. Hook başarısız olursa pipeline devam eder.

---

#### ✅ 5.11 Model Router

```python
# director/model_router.py (YENİ)
from app.config import settings

FLASH_PATTERNS = [
    "özetle", "çevir", "düzenle", "düzelt", "format", "listele",
    "summarize", "translate", "list", "quick"
]

def select_model(message: str, force_tools: bool = False) -> str:
    """Mesaj karmaşıklığına göre Flash veya Pro seç."""
    if force_tools:
        return settings.GEMINI_MODEL_PRO  # Tool calling her zaman Pro
    msg_lower = message.lower()
    if len(message.split()) < 30 and any(p in msg_lower for p in FLASH_PATTERNS):
        return settings.GEMINI_MODEL_FLASH
    return settings.GEMINI_MODEL_PRO
```

**Ek tool — model kullanımı analizi:**
```python
# director/tools/model_router.py
def analyze_model_usage(days: int = 30) -> dict:
    """Langfuse'dan adım adım model kullanımı analizi. Flash'a geçilebilecek adımları öner."""
    from app.director.tools.langfuse import get_langfuse_data
    data = get_langfuse_data(days=days)
    # by_step bazında maliyet karşılaştırması + Flash önerisi
    # S06 text-only → Flash geçiş önerisi (%75 tasarruf, 2 hafta A/B test ile doğrula)
    # Director chat → Pro kalmalı (analiz kalitesi kritik)
```

> **Dikkat:** Tool calling gerektiren tüm isteklerde KESINLIKLE Pro. Flash tool reliability düşük.
> `use_tools=False` mesajlarda Flash kullanılabilir.

---

### KISIM 3 — YENİ KAPASİTELER ÖNCELİK TABLOSU

| # | Modül | Zorluk | Etki | Bağımlılık | Öncelik |
|---|-------|--------|------|------------|---------|
| 1 | Pipeline event hooks (S05/S06/S08/error) | Kolay | ÇOK YÜKSEK | Pipeline adımları | **KRİTİK** |
| 2 | Migration 006 (jobs.is_test_run) | Kolay | YÜKSEK | Yok | **KRİTİK** |
| 3 | director/config.py güvenlik limitleri | Kolay | YÜKSEK | Yok | **KRİTİK** |
| 4 | Pipeline Executor (create_test_job + tools) | Orta | ÇOK YÜKSEK | Migration 006 | **YÜKSEK** |
| 5 | Forecaster (maliyet + hacim + kapasite) | Kolay | YÜKSEK | Yok | **YÜKSEK** |
| 6 | Model Router (Flash/Pro + analyze_model_usage) | Kolay | YÜKSEK (maliyet) | Langfuse | **YÜKSEK** |
| 7 | A/B Test Runner | Orta | YÜKSEK | Pipeline Executor | ORTA |
| 8 | Editor Intelligence (engagement stats) | Orta | ORTA | PostHog/DB | ORTA |
| 9 | Dependency Graph (hardcoded harita) | Kolay | ORTA | Yok | ORTA |
| 10 | Execution Planner | Orta | ORTA | Recommendation sistemi | ORTA |
| 11 | Telegram bildirim | Kolay | ORTA | Env vars | DÜŞÜK |
| 12 | Multi-Channel cross_channel_analysis | Orta | ORTA | Birden fazla kanal | DÜŞÜK |
| 13 | Prompt Lab analyzer (5.1 derinleştirme) | Zor | YÜKSEK | A/B Test + Pipeline Executor | GELECEK |

---

### KISIM 4 — SYSTEM PROMPT EKLEMELERİ (Yeni Kapasite İçin)

> BÖLÜM 2'deki mevcut system prompt eklerine ek olarak:

```
## YENİ ARAÇLARIN KULLANIM KURALLARI

### Pipeline Test Araçları
- create_test_pipeline: Sadece kullanıcı açıkça "pipeline başlat/test et" dediğinde.
  ASLA otomatik tetikleme. Her zaman onay iste. Günde max 5 test (maliyet kontrolü).
- get_test_pipeline_status: İlerleme takibi için. Polling yapabilirsin ama max 3 kez.
- analyze_test_results: Sadece pipeline completed olduğunda çağır.
- get_active_pipelines: Pipeline durumu sorulduğunda kullan.

### A/B Test Araçları
- start_ab_test: Kullanıcı "karşılaştır" veya "A/B test" dediğinde.
  İKİ pipeline çalışacağını ve maliyetin 2x olacağını kullanıcıya bildir, onay al.
- compare_ab_test: Her iki run tamamlandığında. Öncesinde status kontrol et.

### Tahmin Araçları
- forecast_monthly_cost / forecast_pipeline_volume: "tahmin", "nereye gidiyoruz" gibi sorularda.
  Tahmin olduğunu açıkça belirt. Gerçek değil projeksiyon.
- predict_failure_risk: Yeni pipeline öncesinde risk değerlendirmesi isteniğinde.
- forecast_capacity: "sistem ne durumda", "kapasite?" gibi sorularda.

### Model Seçimi
- Tool gerektiren tüm sorgular → Gemini Pro (otomatik, değiştirme)
- Kısa/basit cevaplar (use_tools=False) → model_router karar verir
```

---

### KISIM 5 — GÜVENLİK LİMİTLERİ (`director/config.py`)

> Yeni dosya. Agent'ın kendini veya sistemi zarara uğratmasını önler. Tüm sabitler merkezi.

```python
# director/config.py (YENİ DOSYA)
"""
Director güvenlik limitleri ve rate-limit korumaları.
Bu değerler agent.py ve diğer modüller tarafından kullanılır.
"""

# Tool loop limitleri
MAX_TOOL_CALLS_PER_SESSION = 8
MAX_ITERATIONS_PER_SESSION = 10

# Token / result limitleri
MAX_RESULT_CHARS = 6_000
MAX_MEMORY_RESULTS = 10
MAX_DB_RESULTS = 50

# Pipeline güvenlik
MAX_DAILY_TEST_PIPELINES = 5
MAX_CONCURRENT_TEST_PIPELINES = 2
PIPELINE_ALLOWED_STATUSES_TO_START = ["failed", "pending"]
PIPELINE_BLOCK_IF_ALREADY_RUNNING = True

# A/B test güvenlik
MAX_DAILY_AB_TESTS = 2

# Notification spam önleme
MAX_NOTIFICATIONS_PER_HOUR = 5

# Gemini API rate limit retry
GEMINI_RETRY_DELAYS = [30, 30, 60]
GEMINI_MAX_RETRIES = 3

# Yazma korumaları
BLOCKED_TABLES_FOR_WRITE = frozenset([
    "jobs", "clips", "transcripts", "pipeline_audit_log",
    "channels",  # channel_dna hariç — ayrı kontrol
])

ALLOWED_WRITE_TABLES = frozenset([
    "director_memory", "director_recommendations", "director_conversations",
    "director_events", "director_analyses", "director_decision_journal",
    "director_test_runs", "director_cross_module_signals", "director_prompt_lab",
])

def validate_table_write(table_name: str) -> bool:
    if table_name in BLOCKED_TABLES_FOR_WRITE:
        return False
    return table_name in ALLOWED_WRITE_TABLES

def clamp_db_results(sql: str, max_rows: int = MAX_DB_RESULTS) -> str:
    """SQL'de LIMIT yoksa ekle."""
    if "LIMIT" not in sql.upper():
        return sql.rstrip("; \n") + f" LIMIT {max_rows}"
    return sql
```

**`agent.py`'de kullanım:**
```python
from app.director.config import MAX_TOOL_CALLS_PER_SESSION, MAX_ITERATIONS_PER_SESSION, MAX_RESULT_CHARS
# run_agent:
max_iterations = MAX_ITERATIONS_PER_SESSION
MAX_TOOL_CALLS = MAX_TOOL_CALLS_PER_SESSION
```

**`database.py`'de kullanım:**
```python
from app.director.config import clamp_db_results
sql = clamp_db_results(clean_sql)  # query_database içinde
```

> **Neden ayrı dosya:** Sabitler agent.py'ye gömülü → test edilemez, bakımı zor. Config dosyası ile merkezi ve override edilebilir.

---

### KISIM 6 — KRİTİK MİMARİ NOTLAR (3. KISIM İÇİN)

1. **Pipeline senkron:** `video_worker.py` → `start_pipeline()` → `run_pipeline()` blokiyor. Director'ın pipeline başlatması için RQ enqueue zorunlu.

2. **`is_test_run` kolonu:** Jobs tablosunda YOK. Migration 006 olmadan test pipeline çalıştırılamaz.

3. **Flash maliyet tasarrufu gerçekçi:** `use_tools=False` + mesaj kısa ise Flash, tool gerektiriyorsa Pro. Bu ayrım modelin çalışmasını bozmadan yapılabilir.

4. **Telegram opsiyonel:** `send_notification` tool mevcut. Telegram env değişkenleri yoksa graceful fallback → sadece event yaz.

5. **Pipeline event hooks öncelikli:** Director şu an pipeline içini görmüyor (sadece başını ve sonunu). S02/S05/S06 hookları eklenince Director gerçek zamanlı pipeline monitoring yapabilir.

---

## BÖLÜM 7 — GÜNCELLENMİŞ UYGULAMA SIRASI (TÜM SPRINTLER)

```
SPRINT 1 — KRİTİK BUGLAR (hızlı kazanımlar): ✅ TAMAMLANDI
1.  ✅ agent.py → SYSTEM_PROMPT başına "Araç Kuralları" + "Erişim Haritası" + yeni tool kuralları
2.  ✅ agent.py → run_agent'a use_tools parametresi ekle
3.  ✅ director/message_router.py → yeni dosya, should_use_tools()
4.  ✅ router.py → chat endpoint'inde message_router kullan
5.  ✅ tools/self_analysis.py → write_access listesini güncelle
6.  ✅ director/proactive.py → UNUSED_CLIPS SQL düzelt
7.  ✅ agent.py → learn skoru bug fix (nötr = 7)

SPRINT 2 — TEMEL ALTYAPI (yeni dosyalar + migration): ✅ TAMAMLANDI
8.  ✅ director/config.py → güvenlik limitleri (YENİ DOSYA)
9.  ✅ migrations/006_jobs_test_run.sql → jobs.is_test_run kolonu (MIGRATION)
10. ✅ agent.py → tool loop dedup + MAX_TOOL_CALLS tam implementasyon
11. ✅ tools/database.py → UNION + ; + parameterize SQL güvenliği
12. ✅ tools/database.py → connection pooling + shutdown handling
13. ✅ agent.py → _smart_truncate ile result özeti güncelle

SPRINT 3 — YENİ ÇEKIRDEK YETENEKLER: ✅ TAMAMLANDI
14. ✅ director/tools/pipeline_executor.py → create_test_job, get_test_pipeline_status,
    analyze_test_results, get_active_pipelines (YENİ DOSYA)
15. ✅ agent.py → pipeline executor tool deklarasyonları + dispatcher
16. ✅ director/predictive/forecaster.py → forecast_monthly_cost, forecast_pipeline_volume,
    predict_failure_risk, forecast_capacity (YENİ DOSYA)
17. ✅ agent.py → forecaster tool deklarasyonları + dispatcher
18. ✅ director/model_router.py → Flash/Pro seçimi (YENİ DOSYA)
19. ✅ Schema doğrulama → jobs.updated_at, channels.name kontrol

SPRINT 4 — PIPELINE HOOK + DERİNLEŞTİRME: ✅ TAMAMLANDI
20. ✅ orchestrator.py + s05/s06/s08 → pipeline event hooks (S05/S06/S08/error)
21. ✅ router.py → recommendation apply/cleanup endpoint'leri
22. ✅ learning.py → on_clip_published, on_views_received
23. ✅ director/tools/editor_intelligence.py → engagement stats, opened_not_published
24. ✅ agent.py → editor intelligence tool deklarasyonları

SPRINT 5 — A/B TEST + KARŞILAŞTIRMA: ✅ TAMAMLANDI
25. ✅ director/tools/ab_test.py → start_ab_test, compare_ab_test (YENİ DOSYA)
26. ✅ agent.py → ab_test + dependency_graph tool deklarasyonları + dispatcher
27. ✅ director/dependency_graph.py → hardcoded harita + check_dependency_impact + cross-module signals

SPRINT 6 — GELİŞMİŞ ANALİZ + STRATEJİ: ✅ TAMAMLANDI
29. ✅ director/execution_planner.py → create_execution_plan (YENİ DOSYA)
30. ✅ director/analysis/scorer.py → 5 boyutlu skor sistemi (YENİ DOSYA) + _trigger_analysis entegrasyonu
32. ✅ proactive.py → 3 yeni trigger: GEMINI_RATE_LIMIT_HIGH, PIPELINE_DURATION_SPIKE, MEMORY_GROWTH_WARNING
33. ✅ director/tools/prompt_lab.py → analyze_prompt_performance, suggest_prompt_improvement (YENİ DOSYA)
34. ✅ director/tools/cross_channel.py → cross_channel_analysis (YENİ DOSYA)
35. ✅ agent.py → 5 yeni tool deklarasyonu + dispatcher

28. ✅ director/notifier.py → Telegram push bildirimleri (pipeline failed, cost spike, performance drop, rate limit, weekly digest)

KALAN (düşük öncelik):
31. Context builder (startup snapshot → prompt inject) — nice-to-have
```

---

*Geliştirme bittiğinde bu dosya silinecek, değişiklikler DIRECTOR_MODULE.md'ye işlenecek.*
