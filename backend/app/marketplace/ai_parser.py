"""
AI Parser — Gemini 3.5 Flash ile satılmış ürün ilanlarını yapılandırılmış veriye dönüştürür.

Tier sistemi:
  A-E: Yeterli bilgi var (fatura, kutu, pil, durum net)
  S+/S-: Yetersiz bilgi — sadece görsel ve kısıtlı veriyle yorum

Filtreler:
  - Aksesuar/tamir/toplu satış → REJECT
  - Sadece takas → REJECT (takas + satış OK)
  - Farklı marka/seri → REJECT
"""

import re
import json
from typing import Optional
from app.config import settings


SYSTEM_PROMPT = """Sen bir 2. el elektronik ürün analiz uzmanısın. Almanya (eBay.de) pazarı.

## TIER SİSTEMİ

### A-E Serisi (yeterli bilgi varsa — fatura/kutu/pil/durum bilgisi mevcut):

Tier A (Mükemmel):
  - Faturalı (belirtilmiş veya MwSt./Gewerblich satıcı)
  - Batarya %90+
  - Sıfır çizik/hasar (wie neu / neuwertig)
  - Kutulu (OVP) bonus ama zorunlu değil

Tier B (İyi):
  - Batarya %85+
  - Gözle görülür hasar YOK
  - Cihaz tam çalışıyor
  - Fatura olabilir veya olmayabilir (faturalıysa with_receipt flag ekle)
  - Kutu ve/veya aksesuar eksik olabilir

Tier C (Orta):
  - Batarya %85+
  - Cihaz tam çalışıyor
  - Belirgin kullanım izleri (gözle görülür çizikler)
  - Aksesuar eksik
  - Küçük kozmetik hasar (köşe ezik, kasa çizik)

Tier D (Kötü):
  - Batarya %85 altı
  - Belirgin hasar (derin çizik, cam çatlak ama çalışıyor)
  - Bir fonksiyon bozuk olabilir

Tier E (Almıyoruz):
  - iCloud/IMEI kilitli
  - Ekran kırık (kullanılamaz)
  - Su hasarı
  - Parça amaçlı
  - Kesin dolandırıcı belirtileri (çok düşük fiyat + sıfır bilgi + 1 stok fotoğraf)

### S Serisi (yetersiz bilgi — fatura/kutu/pil net değil):

S+ (Görsel/veri olumlu):
  - Bilgi eksik AMA cihaz fotoğraflarda temiz/gerçek görünüyor
  - Çizik/hasar görülmüyor
  - Gerçek ürün fotoğrafı var (stok değil)
  - Satıcı detay vermemiş ama ürün iyi durumda görünüyor
  - Bu satıcılar genelde piyasayı bilmeyen veya üşenen kişiler

S- (Görsel/veri olumsuz):
  - Bilgi eksik VE cihaz fotoğraflarda kötü görünüyor
  - Veya sadece 1 stok fotoğraf var (gerçek ürün gösterilmemiş)
  - Veya açıklamada kötüye işaret eden ipuçları var

## ÖNEMLİ KURALLAR:
- Bilgi yoksa SCAM DEME. Bilgi yoksa S serisi kullan.
- "possible_scam" flag'i SADECE kesin belirtiler varsa (iCloud locked, aşırı düşük fiyat + stok foto, sahte ilan belirtileri)
- Profesyonel satıcı (Gewerblich/MwSt. dahil) = faturalı say, with_receipt flag ekle
- Fatura YOKSA bu Tier E sebebi DEĞİL. Faturasız cihaz alınabilir (IMEI kontrol edilir).
- eBay condition "Neu" = kutulu say (aksi belirtilmedikçe)
- Batarya bilgisi yoksa null yaz, varsayım YAPMA
- Batarya %85 altıysa Tier D. %85 altı cihaz almıyoruz (pil değişim maliyeti karı yer).

## FLAG SEÇENEKLERİ (birden fazla seçilebilir):
no_box, no_charger, with_box, with_receipt, low_battery, screen_scratches,
cracked_back, cracked_screen, dent_or_bend, water_damage, face_id_broken,
icloud_locked, possible_scam, warranty_active, like_new, heavy_use,
insufficient_info, stock_photo_only, swap_listing

## REJECT KURALLARI (bu ilanlar veritabanına YAZILMAZ):
- Hedef marka/seriye AİT DEĞİL
- Aksesuar ilanı (kılıf, şarj kablosu, ekran koruyucu, cam filmi, Hülle, Case, Panzerglas)
- Tamir ilanı (Display Reparatur, Akku Austausch, Reparatur Service)
- Toplu satış (3 Stück, Konvolut, Lot, Sammlung)
- Parça satışı (Ersatzteil, Platine, Mainboard einzeln)
- SADECE takas (nur Tausch, kein Verkauf) — ama "Tausch oder Verkauf" KABUL
- Fiyat mantıksız (1€, 12345€ gibi placeholder fiyatlar)
"""


def _normalize_model(model: str, brand: str, series: str) -> str:
    """AI'ın döndürdüğü model adını normalize et.

    Goal: "Apple iPhone 15 Pro Max" → "15 Pro Max" (strip brand + product category only).
    Series = "iPhone 15" means product_category = "iPhone", expected model starts with "15".
    """
    model = model.strip()
    if not model:
        return model

    # Extract product category (first word of series, e.g. "iPhone" from "iPhone 15")
    series_parts = series.split()
    product_category = series_parts[0] if series_parts else ""

    # Strip prefixes: brand and product category words only (never numbers)
    words_to_strip = set()
    words_to_strip.add(brand.lower())
    if product_category:
        words_to_strip.add(product_category.lower())
    words_to_strip.update(["apple", "samsung", "sony", "nintendo", "google", "microsoft"])

    model_parts = model.split()
    while model_parts and model_parts[0].lower() in words_to_strip:
        model_parts.pop(0)

    if not model_parts:
        return model

    # Capitalize known suffixes, keep numbers as-is
    normalized_parts = []
    for part in model_parts:
        if part.lower() in ("pro", "max", "plus", "ultra", "mini", "air", "slim", "lite", "se"):
            normalized_parts.append(part.capitalize())
        elif part.upper() == part and len(part) <= 3 and not part.isdigit():
            normalized_parts.append(part.upper())
        else:
            normalized_parts.append(part)

    return " ".join(normalized_parts)


def _normalize_storage(storage: str | None) -> str | None:
    """Storage değerini standart formata normalize et."""
    if not storage:
        return None
    storage = storage.strip().upper().replace(" ", "")
    valid = {"32GB", "64GB", "128GB", "256GB", "512GB", "1TB", "2TB"}
    if storage in valid:
        return storage
    digits = re.sub(r'[^0-9]', '', storage)
    if not digits:
        return None
    num = int(digits)
    if num >= 1000:
        return f"{num // 1000}TB"
    if num in (32, 64, 128, 256, 512):
        return f"{num}GB"
    return None


def _pre_filter(items: list[dict]) -> list[dict]:
    """AI'a göndermeden önce bariz gereksiz ilanları filtrele."""
    filtered = []
    reject_keywords = [
        "hülle", "case", "panzerglas", "schutzfolie", "displayschutz",
        "reparatur", "austausch", "service", "ersatzteil", "platine",
        "konvolut", "lot", "sammlung", "3 stück", "5 stück",
        "nur tausch", "nur zum tausch",
    ]

    for item in items:
        title_lower = item["title"].lower()

        if any(kw in title_lower for kw in reject_keywords):
            continue

        if item["price_eur"] and (item["price_eur"] < 5 or item["price_eur"] > 50000):
            continue

        filtered.append(item)

    rejected_count = len(items) - len(filtered)
    if rejected_count > 0:
        print(f"[AIParser] Pre-filter: {rejected_count} items rejected (accessories/repair/invalid price)")

    return filtered


async def parse_items_batch(
    items: list[dict],
    target_brand: str,
    target_series: str,
) -> list[dict]:
    """
    Bir batch ilan için AI parse yap.

    Returns:
        List of parsed dicts (REJECT edilenler hariç)
    """
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=settings.GCP_PROJECT,
        location=settings.GCP_LOCATION,
    )

    items_text = ""
    for i, item in enumerate(items, 1):
        specs_str = ", ".join([f"{k}: {v}" for k, v in (item.get("specifics") or {}).items()])
        images_str = f"{len(item.get('images', []))} fotoğraf" if item.get("images") else "fotoğraf yok"
        items_text += f"""
ILAN #{i}:
  Başlık: {item['title']}
  Fiyat: {item['price_eur']}€
  eBay Durum: {item.get('condition', '')}
  Satıcı Notu: {item.get('seller_notes', '')}
  Özellikler: {specs_str}
  Görseller: {images_str}
  Satış Tarihi: {item.get('sold_date', '')}
"""

    prompt = f"""HEDEF: {target_brand} {target_series} serisi.

{SYSTEM_PROMPT}

AYRIŞTIRMA:
- product_type: ürün tipi küçük harf (ör: "iphone", "galaxy", "macbook", "playstation")
- model: Seri içindeki SADECE alt-model adı. MARKA YAZMA, SERİ ADINI TEKRARLAMA.
  Örnekler:
    iPhone 15 → model: "15"
    iPhone 15 Pro → model: "15 Pro"
    iPhone 15 Pro Max → model: "15 Pro Max"
    iPhone 15 Plus → model: "15 Plus"
    Samsung Galaxy S24 Ultra → model: "S24 Ultra"
    Samsung Galaxy S24+ → model: "S24+"
    MacBook Air M2 → model: "Air M2"
    PlayStation 5 Slim → model: "5 Slim"
  KURAL: model alanı HİÇBİR ZAMAN marka (Apple, Samsung) veya ürün tipi (iPhone, Galaxy) içermez.
  KURAL: Boşluklar ve büyük/küçük harf TUTARLI olmalı. "15 pro" DEĞİL "15 Pro".
- storage: SADECE şu formatlardan biri: "64GB", "128GB", "256GB", "512GB", "1TB", "2TB". Yoksa null.
- color: Almanca veya İngilizce renk
- battery_pct: Sadece belirtilmişse (sayı). Yoksa null.
- usage_condition: "new", "used", "refurbished"
- tier: "A", "B", "C", "D", "E", "S+", "S-"
- tier_reason: Neden bu tier'a koyduğunun kısa açıklaması (1 cümle)
- flags: Uygun flag'ler listesi
- item_index: İlanın sıra numarası (1'den başlar, ILAN #N'deki N değeri)

İLANLAR:
{items_text}

JSON ARRAY döndür. Her eleman ILAN sırasına göre olmalı (1, 2, 3...).
REJECT için: {{"item_index": N, "reject": true, "reason": "..."}}
Kabul için: {{"item_index": N, "brand": "...", "product_type": "...", "model": "...", "storage": "...", "color": "...", "tier": "...", "tier_reason": "...", "usage_condition": "...", "battery_pct": null, "flags": [...], "ai_confidence": 0.0-1.0}}

SADECE JSON array döndür."""

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        text = response.text.strip()

        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        parsed_list = json.loads(text)

        results = []
        for parsed in parsed_list:
            idx = parsed.get("item_index")
            if idx is not None:
                idx = int(idx) - 1
            else:
                idx = parsed_list.index(parsed)

            if idx < 0 or idx >= len(items):
                continue

            if parsed.get("reject"):
                print(f"[AIParser] REJECT #{idx+1}: {parsed.get('reason', '?')}")
                continue

            if not parsed.get("brand") or not parsed.get("model"):
                continue

            tier_val = parsed.get("tier", "S-")
            if tier_val.startswith("Tier "):
                tier_val = tier_val.replace("Tier ", "")

            model_val = _normalize_model(parsed.get("model", ""), target_brand, target_series)
            storage_val = _normalize_storage(parsed.get("storage"))

            result = {
                "source_url": items[idx]["url"],
                "source_title": items[idx]["title"],
                "brand": parsed.get("brand", target_brand),
                "product_type": parsed.get("product_type", ""),
                "model": model_val,
                "storage": storage_val,
                "color": parsed.get("color"),
                "tier": tier_val,
                "tier_reason": parsed.get("tier_reason", ""),
                "usage_condition": parsed.get("usage_condition", "used"),
                "battery_pct": parsed.get("battery_pct"),
                "flags": parsed.get("flags", []),
                "ai_confidence": parsed.get("ai_confidence", 0.5),
                "sold_price": items[idx]["price_eur"],
                "sold_date": items[idx].get("sold_date"),
                "raw_seller_notes": items[idx].get("seller_notes"),
                "raw_images": items[idx].get("images", []),
                "raw_specifics": items[idx].get("specifics", {}),
            }
            results.append(result)

        print(f"[AIParser] Batch: {len(items)} items → {len(results)} accepted, {len(items) - len(results)} rejected")
        return results

    except Exception as e:
        print(f"[AIParser] Error: {e}")
        return []


async def parse_and_save(
    items: list[dict],
    target_brand: str,
    target_series: str,
    batch_size: int = 20,
) -> int:
    """
    Tüm ilanları batch'ler halinde parse edip Supabase'e kaydet.
    Pre-filter → AI parse → DB save.
    """
    from app.services.supabase_client import get_client
    import asyncio

    items = _pre_filter(items)
    if not items:
        print("[AIParser] No items after pre-filter")
        return 0

    supabase = get_client()
    total_saved = 0

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        print(f"[AIParser] Processing batch {i // batch_size + 1} ({len(batch)} items)...")

        parsed = await parse_items_batch(batch, target_brand, target_series)

        if not parsed:
            # Rate limit or error — retry once after 30s
            print(f"[AIParser] Batch failed, retrying in 30s...")
            await asyncio.sleep(30)
            parsed = await parse_items_batch(batch, target_brand, target_series)

        for item in parsed:
            try:
                sold_date_val = None
                if item.get("sold_date"):
                    month_map = {"Jan": "01", "Feb": "02", "Mär": "03", "Apr": "04", "Mai": "05", "Jun": "06",
                                 "Jul": "07", "Aug": "08", "Sep": "09", "Okt": "10", "Nov": "11", "Dez": "12"}
                    date_m = re.match(r'(\d{1,2})\.\s*(\w{3})\.?\s*(\d{4})', item["sold_date"])
                    if date_m:
                        day = date_m.group(1).zfill(2)
                        month = month_map.get(date_m.group(2), "01")
                        year = date_m.group(3)
                        sold_date_val = f"{year}-{month}-{day}"

                supabase.table("marketplace_price_data").upsert({
                    "source_platform": "ebay_de",
                    "source_url": item["source_url"],
                    "source_title": item["source_title"],
                    "brand": item["brand"],
                    "product_type": item["product_type"],
                    "model": item["model"],
                    "storage": item["storage"],
                    "color": item["color"],
                    "tier": item["tier"],
                    "usage_condition": item["usage_condition"],
                    "battery_pct": item["battery_pct"],
                    "flags": item["flags"],
                    "sold_price": item["sold_price"],
                    "sold_date": sold_date_val,
                    "raw_seller_notes": item["raw_seller_notes"],
                    "raw_images": item["raw_images"],
                    "raw_specifics": item["raw_specifics"],
                    "ai_confidence": item["ai_confidence"],
                    "extra": {"tier_reason": item.get("tier_reason", "")},
                }, on_conflict="source_url").execute()

                total_saved += 1
            except Exception as e:
                print(f"[AIParser] DB save error for {item['source_url']}: {e}")

        if i + batch_size < len(items):
            await asyncio.sleep(8)

    print(f"[AIParser] Total saved: {total_saved}/{len(items)}")
    return total_saved
