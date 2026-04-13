--------------------------------------------------------------------------------
S01 — SES ÇIKARMA VE HAZIRLIK (AUDIO EXTRACTION)
[ ] Akış Kontrolü: S01 mevcut haliyle FFmpeg kullanarak videodan .m4a formatında ses çıkarıyor. Bu adımda yapısal bir sorun yok, ancak üretilen ses dosyasının metadata bozulmaları yaşamaması ve S02'ye eksiksiz aktarıldığından (hata yutulmadığından) emin olunan bir "dosya boyutu / süre bütünlüğü" doğrulama adımı eklenebilir.

--------------------------------------------------------------------------------
S02 — DEŞİFRE VE NOVA-3 ENTEGRASYONU (TRANSCRIPTION)
[ ] Model Güncellemesi: Deepgram API çağrısındaki parametreyi model=nova-3 olarak değiştir.
[ ] Keyterm Prompting (Özel Kelime Enjeksiyonu): Nova-3'ün en büyük nimetlerinden biri olan Keyterm özelliğini API'ye ekle. channel_dna ve video_title içerisindeki kanala özel terimleri, konuk isimlerini, oyun veya sektör jargonlarını (maksimum 100 kelimeye kadar) liste olarak Deepgram API isteğine dahil et. Bu, S05 ve S06'da yapay zekanın halüsinasyon görmesini (yanlış yazılmış kelimeleri anlamaya çalışmasını) kökünden çözecektir.
[ ] Çok Dilli (Multilingual) Modeli Aktifleştirme: Nova-3'ün endüstride ilk olan anlık dil algılama özelliğini kullanmak için API isteğinde İngilizce, İspanyolca vb. 10 dil arası anlık geçişleri (code-switching) tanıyacak parametreleri aktif et.
[ ] Boş Kelime (Words Array) Validasyonu: Deepgram bazen gürültülü anlarda veya sadece müzik olan bölümlerde words dizisini boş döndürebiliyor (Path 1 Hatası). Bu dizinin boş gelip gelmediğini kontrol eden, boşsa S07'de sistemi kelime ortasından kesmeye zorlamayacak güvenli bir hata yakalama (validation) bloğu ekle.

--------------------------------------------------------------------------------
S03 & S04 — KİMLİK TESPİTİ VE SENARYOLAŞTIRMA (KRİTİK VERİ KAYBI HATALARI)
[ ] KRİTİK HATA ÇÖZÜMÜ (String/Integer Uyuşmazlığı): S03, en çok konuşanı ve ikinciyi bulup ID'leri tam sayı (0, 1) olarak predicted_map'e kaydediyor. Ancak S04, konuşmacıyı eşleştirirken kodda "SPEAKER_0" şeklinde bir string (metin) arıyor. Bu uyuşmazlık yüzünden eşleşme asla gerçekleşmiyor ve sistem istisnasız tüm konuşmacıları "UNKNOWN" (Bilinmeyen) olarak etiketliyor. S04'teki arama mantığı derhal speaker_map.get(int_speaker_id) şeklinde düzeltilmeli!
[ ] Zaman Damgası Hassasiyetinin Korunması: S04, Deepgram'ın verdiği milisaniyelik words[].start hassasiyetini tek ondalıklı (örneğin [02:23.4]) yaklaşık değerlere yuvarlayıp bozuyor. Nova-3'ün getirdiği yüksek hassasiyetli süreleri bozmamak için bu yuvarlama iptal edilmeli.

--------------------------------------------------------------------------------
S05 — VİRAL KEŞİF (HIZ, MALİYET VE MANTIK GÜNCELLEMELERİ)
[ ] Sadece Transkript Kullanımı (Maliyet Düşürme): Gemini 2.5 Pro'ya S05'te videonun tamamını yükleyen (video upload) ağır ve aşırı pahalı işlemi iptal et. S05, aday klipleri bulmak için sadece S04'ten gelen temiz ve düzeltilmiş labeled_transcript (transkript senaryosu), channel_dna ve guest_profile verilerini kullanmak üzere güncellenmeli. (Ağır görsel analiz işi sadece S06'da yapılmalı).
[ ] Eksik Doğrulama Kontrolü: S05'in çıktıları filtrelediği _validate_candidates fonksiyonunda start >= video_duration kontrolü var ancak sürenin eksi (-) değer olup olmadığını kontrol eden bir güvenlik ağı yok; eklenecek.

--------------------------------------------------------------------------------
S06 — TOPLU DEĞERLENDİRME (CLAUDE PROMPT VE SESSİZ HATALAR)
[ ] GİZLİ HATA ÇÖZÜMÜ (Undefined failed_log): 603. satırdaki len(failed_log) hatasını düzelt. failed_log kodu try/except Exception: pass içinde yazıldığı için NameError veriyor ama sistem bu hatayı yutup (swallow) hiçbir şey olmamış gibi devam ediyor. failed_log değişkenini düzgün tanımla.
[ ] S05 Çıktılarının S06 Promptuna Enjeksiyonu (Çöpe Giden Veriler): Şu an S05'te Gemini'nin ürettiği estimated_duration, needs_context, reason ve primary_signal gibi altın değerindeki analizler, S06'da tamamen görmezden geliniyor. Claude'a gönderilen candidate array'ine veya SYSTEM_PROMPT'a bu alanları dahil et. Claude'un "Gemini bunu buradaki espri (reason: humor) için seçti" argümanını bilmesi, daha mantıklı kırpmalar yapmasını sağlayacak.
[ ] Robotik 10 Kelimelik Bölme Mantığının İptali: _extract_context_segments fonksiyonundaki, metni her 10 kelimede bir [MM:SS.ss] şeklinde parçalayan (Path 4 Hatası) mantığı sil. Nova-3'ün kusursuz paragraf, noktalama biçimlendirmesini ve cümle düzeyinde gerçek zaman damgalarını kullanarak Claude'a çok daha insani bir okuma metni gönder.

--------------------------------------------------------------------------------
S07 — HASSAS KESİM MATEMATİĞİ (UYUMSUZLUK VE KELİME ORTASI KESİMLER)
[ ] Süre Limiti (Hard-Cap) Uyuşmazlık Hatası: S05 ve S06, kullanıcının belirlediği job-level dinamik süreleri (clip_duration_max vb.) okuyor. Fakat S07 bunları tamamen yok sayıp settings.MAX_CLIP_DURATION sabitine zorluyor. S07 de clip_duration_max parametresini saygı duyacak şekilde güncellenmeli.
[ ] 3 Saniyelik Aralık Arama Penceresi Optimizasyonu: Nova-3'ün zamanlama kusursuzluğu sayesinde, Claude'un S06'da karar verdiği zamanlar gerçeğe çok daha yakın olacak. S07'deki ±3 saniyelik gereksiz arama (search window) mantığını daralt ve daha net eşleşmeye bırak (Path 2 Hatası).
[ ] Hata Fallback (Kelime Ortası Kesim) Çözümü: S07'de bir hata (exception) olduğunda sistem, LLM'in verdiği ham sürelere dönüyor (Path 3 Hatası). Bu da klibin kesin olarak kelimenin ortasından kesilmesine sebep oluyor. Hata bloğu çalışsa dahi kelime sınırlarına yapıştıracak (snap) güvenli bir "ikincil yedek matematik" (fallback snap) ekle.
[ ] Nefes/Boşluk Payı (Breath Buffer) Kayması: Hizalamadan sonra yapılan - 0.3 saniye geri çekme işlemi (Path 5 Hatası), eğer konuşmacılar hiç duraksamadan konuşuyorsa bir önceki kelimenin son seslerini klibe dahil ediyor. 0.3 saniye geri çekerken "bir önceki kelimenin bitiş süresine çarpıp çarpmadığını" kontrol eden ufak bir mantık (if snapped_start - 0.3 < prev_word.end) eklenmeli.

--------------------------------------------------------------------------------
S08 — KESİM İŞLEMİ (KÖR KESİMİ ENGELLEME)
[ ] Güvenlik Ağı (Sanity Check): S08, FFmpeg ile kesim yaparken S07'nin final_start verisine körü körüne inanıyor. S08 komutu çalıştırmadan hemen önce, gelen final_start süresinin, Deepgram'ın asıl JSON'ındaki bir kelime başlangıcıyla (word.start) milisaniyelik uyuşup uyuşmadığını son bir kez doğrulayan bir kontrol adımı (cross-reference) ekle. Uyuşmazlık varsa son bir milisaniye yuvarlaması yapsın.
