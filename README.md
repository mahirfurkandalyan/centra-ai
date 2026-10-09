# Centra AI Chatbot (MVP)

Yerel LLM (Ollama) ile çalışan, SSS tabanlı müşteri asistanı.

## Nasıl çalışır?

1. Admin panelden SSS `.md` dosyası yüklenir (`## Soru` / `**Modül:**` / `### Cevap` formatı).
2. Her sorunun anlamsal vektörü `bge-m3` ile çıkarılıp SQLite'a kaydedilir.
3. Kullanıcı soru sorduğunda en benzer SSS'ler bulunur:

| Benzerlik | Mod | Ne olur? |
|---|---|---|
| ≥ `DIRECT_THRESHOLD` (0.82) | `direct` | SSS cevabı aynen döner, LLM çalışmaz (anında) |
| ≥ `RAG_THRESHOLD` (0.60) | `rag` | En yakın SSS'ler LLM'e verilir, kısa cevap üretilir |
| altı | `fallback` | LLM bilgi olmadan cevap verir: selamlaşır ya da iletişim kanallarına yönlendirir |

Tüm konuşmalar `chat_logs` tablosuna mod, benzerlik ve süre bilgisiyle kaydedilir.

## Sunucuya kurulum (Windows)

Önkoşullar: Ollama, Python 3.12+, Git.

```powershell
ollama pull qwen3:4b-instruct
ollama pull bge-m3

cd C:\Projects
git clone https://github.com/mahirfurkandalyan/centra-ai.git
cd centra-ai
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Çalıştırma

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

- Sohbet: http://localhost:8000
- Admin: http://localhost:8000/admin

## QA hattındaki tüm soru-cevapları içe aktarma

QA hattı deposundan (yalnızca okuyarak) tüm golden cevapları ve gap dosyalarını aktarır:

```powershell
.\.venv\Scripts\python.exe -m app.importer "C:\Projects\centra-chatbot" --dry-run   # önce sadece say
.\.venv\Scripts\python.exe -m app.importer "C:\Projects\centra-chatbot"             # aktar + indeksle
```

- Aynı soru hem golden'da hem gap'te varsa **gap cevabı** (düzeltilmiş cevap) kalır.
- "Bağlam Takibi" kategorisindeki sorular alınmaz (önceki mesajlara atıf yapıyorlar).
- Tekrar çalıştırmak güvenlidir; sadece yeni veya değişen kayıtlar işlenir. İndeksleme yarıda kesilirse kaldığı yerden devam eder.
- Sunucu açıkken de çalıştırılabilir; sunucu yeni kayıtları otomatik görür.

## Güncelleme

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ardından sunucuyu durdurup (Ctrl+C) yeniden başlatın.

## Ayarlar (ortam değişkenleri)

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `CHAT_MODEL` | `qwen3:4b-instruct` | Cevap üreten model |
| `EMBED_MODEL` | `bge-m3` | Arama modeli (değiştirilirse tüm SSS yeniden indekslenmeli) |
| `DIRECT_THRESHOLD` | `0.82` | Doğrudan SSS cevabı eşiği |
| `RAG_THRESHOLD` | `0.60` | LLM'e bağlam verme eşiği |
| `RAG_TOP_K` | `2` | LLM'e verilecek SSS sayısı |
| `CONTEXT_CHARS` | `800` | LLM'e verilen her kaynak cevabın azami uzunluğu (cümle sonundan kesilir) |
| `CHAT_NUM_GPU` | `0` | Sohbet modelinin GPU katman sayısı. `0` = yalnızca CPU (küçük GPU'da modellerin birbirini bellekten atmasını önler). Güçlü GPU'lu sunucuda boş bırakın: `$env:CHAT_NUM_GPU = ""` |
| `ADMIN_TOKEN` | (boş) | Ayarlanırsa admin uçları bu anahtarı ister. Sunucu dışarı açılmadan önce mutlaka ayarlayın. |
| `CENTRA_DATA_DIR` | `./data` | Veritabanı klasörü |

Örnek: `$env:CHAT_MODEL = "gemma3:4b"; powershell -ExecutionPolicy Bypass -File .\run.ps1`

## Geliştirme ilerlemesini GMS'e gönderme

Geliştirme oturumlarının ilerlemesi GMS'teki "centra-ai" ekranına gönderilebilir: canlı telemetri
(hangi aşamada, kaç soru cevaplanmış), her turun özeti (puan, halüsinasyon, süre, tut/geri al
kararı) ve oturum özeti. Sözleşmenin tamamı `docs/GMS_GONDERICI.md` dosyasında.

```powershell
.\.venv\Scripts\python.exe -m scripts.gms_report config          # maskeli yapılandırma + kapı durumu
.\.venv\Scripts\python.exe -m scripts.gms_report session-start --feedback "kullanıcının isteği"
.\.venv\Scripts\python.exe -m scripts.gms_report phase measure --round 1 --label tur-01-baslangic
.\.venv\Scripts\python.exe -m scripts.gms_report watch           # 20 sn'de bir canlı telemetri
.\.venv\Scripts\python.exe -m scripts.gms_report round-summary tur-01-baslangic --decision baseline --note "..."
.\.venv\Scripts\python.exe -m scripts.gms_report session-end --stop-reason manual
```

Her komuta `--dry-run` eklenebilir: istek yapılmaz, hedef ve gövde yazdırılır (gizler maskeli).

| Değişken | Açıklama |
|---|---|
| `GMS_CENTRA_AI_BASE_URL` | GMS adresi. **`https` olmak zorunda**, aksi halde hiç istek yapılmaz. |
| `GMS_CENTRA_AI_TELEMETRY_PATH` | Telemetri yolu (varsayılan `/api/centra-ai/telemetry`) |
| `GMS_CENTRA_AI_KEY` | Bildirici anahtarı (`X-GMS-CentraAI-Key`) |
| `GMS_CENTRA_AI_SECRET` | Bildirici gizi (`X-GMS-CentraAI-Secret`). Hiçbir çıktıya ve loga yazılmaz. |
| `GMS_CENTRA_AI_CA` | Kök sertifika yolu. Boşsa `C:\gms\gms-public.pem`, sonra `NODE_EXTRA_CA_CERTS` denenir. |

Güvenlik: TLS doğrulaması her zaman açıktır; GMS'in kurumsal olmayan kökü yalnızca güvenilenler
listesine **eklenir**, doğrulama gevşetilmez. Anahtar ve giz sadece isteğin başlığına konur.

Durum `data/eval/gms_state.json`'da tutulur (runId, tur, aşama, monoton artan `sequence`), gönderim
kayıtları `data/eval/gms.log`'a yazılır. **GMS'e ulaşılamaması ölçümü ya da geliştirmeyi
durdurmaz:** hata loglanır, komut 0 ile çıkar.

## Proje yapısı

```
app/
  main.py           FastAPI uçları
  rag.py            Arama + cevap üretme mantığı, sistem prompt'u
  store.py          SQLite deposu ve vektör araması
  indexer.py        Arka planda embedding üretimi
  parser.py         SSS .md ayrıştırıcı
  ollama_client.py  Ollama API istemcisi
  gms_reporter.py   GMS gönderici: yapılandırma, gönderim kapısı, TLS, karar mantığı
  config.py         Ayarlar
scripts/
  make_eval_set.py  Sabit 50 soruluk değerlendirme seti
  run_eval.py       Seti bota sorar (leave-one-out)
  eval_summary.py   Tur metrikleri ve tur geçmişi tablosu (metriklerin tek kaynağı)
  gms_report.py     GMS'e oturum/aşama/tur bildirimi CLI'si
static/             Sohbet ve admin sayfaları
```
