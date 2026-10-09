# Centra AI Chatbot — proje bağlamı

centra.com.tr sitesindeki AI chatbot'u (şu an dış bir firmadan hizmet alınıyor) kendi yerel LLM'imizle
değiştirmek için MVP. Kullanıcıyla Türkçe, sade ve teknik jargonsuz konuş.

## Kullanıcıyla çalışma şekli

**Kullanıcı test etmek, denemek, kontrol etmek istemiyor; bunların hepsi senin işin.** Kullanıcı sadece
raporları okur ve yön verir. Ondan asla "şunu deneyip sonucu yapıştırır mısın", "şu komutu çalıştır"
isteme; bilgisayar senin elinde, her şeyi kendin çalıştır, kendin ölç, kendin doğrula.

Kullanıcı ne zaman geleceği belli olmayan aralıklarla gelir ve **serbest cümlelerle** yazar; sabit
komut kelimeleri yok. Niyetini anla:

- **Durum öğrenmek istiyor** (ör. "ne yaptın", "son durum ne", "rapor ver", "nasıl gidiyor") →
  aşağıdaki "Rapor" bölümü.
- **Bir şeyi beğenmedi, bir istek ya da fikir söylüyor, daha iyisini istiyor** (ör. "cevaplar çok uzun",
  "şu soruya saçma cevap verdi", "daha hızlı olsun", "geliştirmeye devam et") → "Geliştirme" bölümü;
  söylediği şey o oturumun öncelikli hedefi olur.
- **Beğendiğini, onayladığını söylüyor** (ör. "güzel olmuş", "tamam", "bunu kullanalım") → "Onay" bölümü.
- Kısa bir soru soruyorsa (ör. "neden yavaş?") düz cevap ver; büyük iş başlatma.
- Niyet gerçekten belirsizse tek kısa soru sor; ama geliştirme başladıktan sonra hiç soru sorma.

Kullanıcı yokken kendiliğinden iş başlatma; geliştirme bitince bekle.

### Rapor

`RAPOR.md`'nin en üstteki girişini ve `python -m scripts.eval_summary --history` tablosunu oku, sade dille anlat:
son görüşmeden beri ne yapıldı, puanlar nasıl değişti (vendor referansı: ort. 73.5, başarı %73.2),
neyin işe yarayıp neyin yaramadığı, botun güzel ve kötü cevaplarından 2-3 gerçek örnek, açık riskler,
kullanıcıdan beklenen karar (ör. "beğendiysen kalıcı hâle getireyim mi?"). Rakam tablosuna boğma.

### Geliştirme

Başladığı andan bitene kadar **kullanıcıya hiç soru sorma, onay bekleme**; kullanıcı bakmayacak.
Belirsizlikte makul kararı kendin ver ve rapora yaz. Akış:

1. `main` üzerinde çalış. Başlamadan önce geri dönüş noktası koy: `git tag oncesi-<YYYYMMDD-HHMM>` ve push et.
2. Sohbet sunucusu açıksa ölçümü bozar; `run.ps1` süreci varsa durdur, bitince yeniden başlat.
3. `data/eval/eval_set.json` yoksa `python -m scripts.make_eval_set`. Seti asla yeniden üretme
   (turlar karşılaştırılamaz hâle gelir).
4. **Oturumu GMS'e aç:** `python -m scripts.gms_report session-start --feedback "<kullanıcının isteği>"`
   ve ölçüm boyunca arka planda `python -m scripts.gms_report watch`. Ayrıntı: `docs/GMS_GONDERICI.md`.
5. **Başlangıç ölçümü** (`tur-NN-baslangic`): mevcut kodu ölç ve puanla.
   Ölçümden önce `gms_report phase measure --round 1 --label <tur>`, puanlamada `phase score`.
   Puanlama bitince `gms_report round-summary <tur> --decision baseline --note "..."`.
6. **Tur döngüsü:** en zayıf alanı seç (puanı düşük kategoriler, halüsinasyon, boş/kesik cevap,
   yavaşlık, kullanıcının geri bildirimi) → tek bir değişiklik yap → ölç → puanla → karar:
   - Her aşamada aşamayı bildir: `gms_report phase improve|measure|score --round N --label <tur>`.
   - Ortalama puan **≥3 artıyorsa**, ya da puan düşmeden halüsinasyon/boş-kesik sayısı veya süre
     belirgin azalıyorsa → **tut**, commit et (mesajda öncesi/sonrası rakamlar).
   - Aksi halde → **geri al** (`git checkout -- .`), denemeyi rapora "işe yaramadı" diye yaz.
   - Karardan sonra turu bildir: `gms_report round-summary <tur> --decision kept|reverted --note "..."`
     (tur başına bir kez; 409 gelirse üzerine yazmaya çalışma, logla ve rapora yaz).
   - Bir turda sadece bir şeyi değiştir; yoksa neyin işe yaradığı anlaşılmaz.
7. **Durma:** art arda 3 tur "tutulmadı" ise, ya da 12 tur dolduysa, ya da kota uyarısı geldiyse dur.
8. **Oturumu GMS'te kapat:** `python -m scripts.gms_report session-end --stop-reason plateau|roundLimit|quota|error|manual`
   ve `watch` sürecini durdur.
9. `RAPOR.md`'nin **en üstüne** yeni giriş ekle (şablon aşağıda), commit et, push et.
   Girişe "GMS'e gönderim: başarılı / şu hata" notunu da düş.
10. Sohbet sunucusunu yeniden başlat (kullanıcı yeni hâli deneyebilsin).
11. Kullanıcıya **bildirim gönder** (PushNotification aracı varsa onunla, yoksa son mesajla):
    "Geliştirme bitti: ort. puan X → Y. Rapor hazır."

GMS'e ulaşılamaması **hiçbir zaman** ölçümü ya da geliştirmeyi durdurmaz: `gms_report` hatayı
`data/eval/gms.log`'a yazar ve 0 ile çıkar. Akışı GMS yüzünden bekletme.

Puanlamayı **Agent aracıyla alt-göreve** yaptır (`model: sonnet` yeterli; 50 soruyu 2 alt-göreve
böl), `evals/PUANLAMA.md`'nin tamamını talimata koy. Geliştirmeyi kendin yap.

Denenebilecek fikirler (sırası ölçüme göre): `DIRECT_THRESHOLD` / `RAG_THRESHOLD` / `RAG_TOP_K` /
`CONTEXT_CHARS` ayarı; sistem prompt'u; cevap tamlık kontrolü (çok kısa ya da cümle ortasında biten
cevabı yeniden üret); tuzak sorularına özel davranış; aynı RAM sınırında başka model (`gemma3:4b`
kurulu; `qwen3:1.7b`, `llama3.2:3b`, `phi4-mini` gibi ≤4B modeller `ollama pull` ile denenebilir).
**Embedding modelini değiştirme** (5570 kaydın yeniden indekslenmesi saatler sürer).

### Onay

Ek bir şey gerekmez (değişiklikler zaten `main`'de); tek cümleyle teşekkür et.

### Geri alma

Kullanıcı son geliştirmeyi beğenmediğini, eski hâlin daha iyi olduğunu söylerse: en son `oncesi-*` etiketine
`git revert` ile dön (geçmişi silme, `reset --hard` + force push yapma), push et, sunucuyu yeniden
başlat, RAPOR.md'ye not düş.

### RAPOR.md giriş şablonu

```markdown
## <tarih saat> — Geliştirme oturumu
**Sonuç:** ort. puan X → Y, başarı %A → %B, halüsinasyon H1 → H2, model modu ort. S1 → S2 sn
**Kullanıcı geri bildirimi:** ... (yoksa "yok")
**Tutulan değişiklikler:** madde madde, her biri neden ve kaç puan
**Denenip geri alınanlar:** madde madde, neden işe yaramadı
**Neden durdum:** tavana ulaşıldı / tur sınırı / kota
**Açık sorunlar ve öneriler:** ...
**Senden beklenen:** ör. "Beğenmediğin bir şey varsa yaz, yoksa böyle kalsın."
```

## Mimari (detay: README.md)

FastAPI + SQLite + Ollama. Soru → `bge-m3` ile anlamsal arama (5570 SSS kaydı) → benzerliğe göre:
`direct` (kayıtlı cevap aynen, ~1 sn) / `rag` (en yakın SSS'ler + `qwen3:4b-instruct`, ~30-45 sn) /
`fallback` (bilgi yok, model yönlendirir). Kod: `app/`, değerlendirme: `scripts/`, `evals/`.

## Bilgi tabanının kaynağı

QA hattı deposu `C:\Projects\centra-chatbot` (her Cumartesi 18:00 vendor bot'u 1000 soruyla test eden
ayrı bir proje). `python -m app.importer` oradan salt okunur aktarır:
- **gap** (1145): vendor'a yüklenen düzeltilmiş SSS md'leri. Format: `## Soru` / `**Modül:**` / `### Cevap`
  (Pack 15 formatı doğrudur; Pack 14 md yanlış üretildi ve bilerek atlanıyor).
- **golden** (4425): QA hattının her soru için yazdığı referans cevaplar. Aynı soru gap'te varsa gap kazanır.
- "Bağlam Takibi" kategorisi alınmaz.

## Donanım (darboğaz bu)

i7-8550U (4 çekirdek), **8 GB RAM**, MX150 (2 GB). Ölçülenler:
- qwen3:4b-instruct CPU'da: üretim ~7.8 token/sn, prompt okuma ~36 token/sn.
- **İki model GPU'ya birlikte sığmıyor**; Ollama her soruda birini atıp diğerini yüklüyordu (97 sn).
  Çözüm `CHAT_NUM_GPU=0` (sohbet CPU'da, bge-m3 GPU'da). Bunu geri alma.
- `qwen3:4b` (etiketsiz) düşünme modunu kapatmıyor, tek cevap 6 dk sürdü; `-instruct` kullan.
- Windows'ta `localhost` ~2 sn kaybettiriyor → `127.0.0.1`.
- Ollama `keep_alive` için birimsiz "-1" metnini 400 ile reddediyor → sayı gönder.
- 8 GB RAM'de ~4B (Q4) üstü model çalışmaz.

## KESİN KURALLAR

1. `C:\Projects\centra-chatbot` klasörüne **asla yazma** (dosya, git, npm, hiçbir şey). Çalışma ağacı
   kirlenirse Cumartesi QA hattı başlamaz. Sadece okuyabilirsin.
2. Windows Görev Zamanlayıcı görevlerine (`CentraChatbotQA-*`) dokunma, QA hattını çalıştırma.
3. Bu bilgisayar ve Claude hesabı QA hattıyla ortak. Cumartesi 17:00-23:59 arası ağır iş
   (değerlendirme, indeksleme) başlatma; bu saatte geliştirme istenirse kullanıcıya söyle ve bekle.
   Kota uyarısı alırsan hemen dur ve raporla: Cumartesi koşusu için kota kalmalı.
4. Git geçmişini silme/yeniden yazma (force push, reset --hard yok); her geliştirme öncesi `oncesi-*` etiketi koy.
5. `data/` git'e girmez (şirket verisi, veritabanı). Silme; veritabanında yapısal değişiklikten önce
   `data/centra.db`'nin yedeğini al.
6. Gizli bilgi (token, şifre, API anahtarı) yazma, loglama.

## Değerlendirme komutları

```powershell
.\.venv\Scripts\python.exe -m scripts.make_eval_set      # bir kez: sabit 50 soruluk set
.\.venv\Scripts\python.exe -m scripts.run_eval tur-03    # bota sor (~20-30 dk, Ollama açık olmalı)
# puanla (alt-görev): evals/PUANLAMA.md -> data/eval/runs/tur-03/scores.json
.\.venv\Scripts\python.exe -m scripts.eval_summary tur-03 --note "ne değişti"
.\.venv\Scripts\python.exe -m scripts.eval_summary --history
```

Leave-one-out: test sorusunun kendi kaydı aramada gizlenir, bot soruyu ilk kez görüyormuş gibi cevaplar.
50 soruda ölçüm gürültüsü ±3-4 puandır; eşik bu yüzden 3 puan.
