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
| `ADMIN_TOKEN` | (boş) | Ayarlanırsa admin uçları bu anahtarı ister. Sunucu dışarı açılmadan önce mutlaka ayarlayın. |
| `CENTRA_DATA_DIR` | `./data` | Veritabanı klasörü |

Örnek: `$env:CHAT_MODEL = "gemma3:4b"; powershell -ExecutionPolicy Bypass -File .\run.ps1`

## Proje yapısı

```
app/
  main.py           FastAPI uçları
  rag.py            Arama + cevap üretme mantığı, sistem prompt'u
  store.py          SQLite deposu ve vektör araması
  indexer.py        Arka planda embedding üretimi
  parser.py         SSS .md ayrıştırıcı
  ollama_client.py  Ollama API istemcisi
  config.py         Ayarlar
static/             Sohbet ve admin sayfaları
```
