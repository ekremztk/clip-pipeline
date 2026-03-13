# Railway & Vertex AI Deployment Guide

Bu belgede, Gemini Developer API'den Google Cloud Vertex AI'a geçiş yaparken Railway üzerinde Service Account JSON dosyasının nasıl ekleneceği adım adım açıklanmıştır.

## Neden Çevresel Değişken (Env Var)?

Service Account JSON dosyasını `.gitignore`a ekleyip doğrudan koda gömmek yerine onu bir ortam değişkeni (Environment Variable) olarak yönetmek en güvenli ve standart yöntemdir. Kodumuz, bu çevresel değişkeni okuyarak çalışma zamanında güvenli ve geçici (temporary) bir dosya oluşturur ve Vertex AI SDK'inin bunu otomatik tanımasını sağlar.

## Railway Üzerinde Yapılması Gerekenler

Railway projenizin `Variables` (Ortam Değişkenleri) sayfasına giderek aşağıdaki değişkenleri ekleyin:

1. **`GCP_CREDENTIALS_JSON`**:
   - Google Cloud üzerinden indirdiğiniz Service Account `.json` dosyasını herhangi bir metin düzenleyici ile açın.
   - İçindeki tüm metni kopyalayın.
   - Railway'de `GCP_CREDENTIALS_JSON` adında yeni bir değişken oluşturun ve kopyaladığınız JSON içeriğini doğrudan değer (value) olarak yapıştırın.

2. **`GCP_PROJECT`**:
   - Google Cloud proje kimliğiniz (Project ID). Örneğin: `my-clip-pipeline-project`.
   - Sistemin Vertex AI'ı kullanabilmesi için bu değişkenin tanımlı olması şarttır. Aksi takdirde, kod otomatik olarak eski `GEMINI_API_KEY` yöntemine düşer (fallback).

3. **`GCS_BUCKET_NAME`** (Önemli):
   - Vertex AI tarafında büyük ses/video dosyaları (örneğin 20MB+) için Google Cloud Storage kullanılması gerekir.
   - Google Cloud üzerinden oluşturduğunuz Storage Bucket adını `GCS_BUCKET_NAME` değişkenine ekleyin (örneğin: `my-podcast-bucket`).
   - Eğer girilmezse kod sadece kısa dosyalar için uygun olan "Inline Data (Base64)" yöntemine geçecek ancak 20MB'yi aşan dosyalarda hata alınacaktır.

4. **`GCP_LOCATION`** (Opsiyonel):
   - Eğer modelinizin belirli bir Google Cloud bölgesinde (Region) çalışmasını istiyorsanız ekleyebilirsiniz (örneğin: `europe-west4`, `us-central1`).
   - Eklenmezse varsayılan olarak `us-central1` kullanılacaktır.

## Yerel Geliştirme (Local Development)

Kodu bilgisayarınızda denerken `.env` dosyanıza şu satırları eklemeniz yeterlidir:

```env
GCP_PROJECT=your-project-id
GCP_LOCATION=us-central1
GCS_BUCKET_NAME=your-bucket-name
GCP_CREDENTIALS_JSON='{ "type": "service_account", "project_id": "...", ... }'
```

*Not: Yerel `.env` dosyanızda JSON'ı tek bir satır halinde veya tırnak işaretlerine dikkat ederek eklemeniz gerekebilir. Eğer sorun yaşarsanız doğrudan `GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json` olarak klasik yöntemi de yerel ortamınızda kullanabilirsiniz.*

## Arka Plan (Nasıl Çalışıyor?)

1. Kod çalıştığında, sistemde `GCP_CREDENTIALS_JSON` değişkeni varsa, bu içerik anında `tempfile.mkstemp` ile sunucuda (Railway) sadece uygulamanın erişebileceği geçici bir dosyaya yazılır.
2. Bu dosyanın yolu (path), otomatik olarak `GOOGLE_APPLICATION_CREDENTIALS` ortam değişkenine atanır.
3. `google-genai` SDK'i (Vertex AI destekli), başlatıldığı anda bu credential dosyasını bularak gerekli yetkilendirmeyi yapar. İşlem tamamen güvenli gerçekleşir.
