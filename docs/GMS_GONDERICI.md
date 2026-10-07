# GMS gönderici — uygulama talimatı

Geliştirme oturumlarının ilerlemesini GMS'teki "centra-ai" ekranına gönderen parça. Sözleşme GMS
oturumuyla kesinleştirildi (2026-10-07). **GMS tarafı yayında ve doğrulandı:** üç yazma ucu çalışıyor,
"centra-ai" bildirici kaydı kullanıcının ürettiği gizin hash'iyle açıldı, ekran GMS navbar'ında.

GMS'in doğruladığı davranışlar: aynı gövde tekrar → 200 `created:false`; tur özeti farklı değerle
tekrar → 409; eski `sequence` → 200 `accepted:false` (yazmaz); bilinmeyen `phase` → 400; 5. turda
`baseline` → 400; `answered > target` → 400; yanlış giz → 401.

**Bu talimatı mevcut bir geliştirme oturumunun ortasında uygulama.** Oturum bitince ayrı bir iş olarak yap.

## Bağlantı ve güvenlik

Ortam değişkenleri (makine düzeyi, kullanıcı ayarladı; değerleri asla yazdırma/loglama):

| Değişken | Değer |
|---|---|
| `GMS_CENTRA_AI_BASE_URL` | `https://192.168.1.254:8443` (QA hattının GMS adresiyle aynı) |
| `GMS_CENTRA_AI_TELEMETRY_PATH` | `/api/centra-ai/telemetry` |
| `GMS_CENTRA_AI_KEY` | `centra-ai` |
| `GMS_CENTRA_AI_SECRET` | gizli |

- Kimlik başlıkları: `X-GMS-CentraAI-Key`, `X-GMS-CentraAI-Secret` (QA hattının başlıklarından farklı).
- **Gönderim kapısı:** URL şeması `https` değilse ya da anahtar/giz eksikse **hiç istek yapma**, sebebi logla.
- **TLS doğrulaması açık kalır.** GMS kurumsal olmayan bir kök sertifika kullanıyor: `httpx`'e
  `verify=` olarak `C:\gms\gms-public.pem` ver (yoksa `NODE_EXTRA_CA_CERTS` değişkenindeki yolu dene).
  `verify=False` kesinlikle yok.
- Gizi loglama: yapılandırmayı yazdırırken `(ayarlı, gizli)` göster, başlık değerlerini maskele.
- Referans: QA hattının `C:\Projects\centra-chatbot\gms\reporter.js` dosyası aynı kuralları uyguluyor
  (sadece oku, o klasöre yazma).

## Uçlar

### 1. Canlı telemetri — `POST /api/centra-ai/telemetry`
16 KB, en fazla 30/dk, **20 sn kadans**.

```json
{
  "runId": "guid", "roundNo": 3, "sequence": 412,
  "phase": "measure",
  "runStatus": "Running",
  "startedAt": "...Z", "finishedAt": null, "progressUpdatedAt": "...Z",
  "counters": { "target": 50, "answered": 17, "errors": 0 },
  "lastError": null, "runnerVersion": "1.0.0", "hostname": "DESKTOP-U7J2DQQ"
}
```
- `phase`: `measure` (bota soru soruluyor) | `score` (puanlanıyor) | `improve` (değişiklik yapılıyor)
- `runStatus`: `Running` | `Idle` | `Completed` | `Stopped` | `Failed`
- `runId`: oturum başında üretilen GUID, oturum boyunca sabit. `roundNo`: 1..12 (başlangıç ölçümü = 1).
- `sequence`: oturum başına **monoton artan**; yeniden denemede eski değeri gönderme. Diske kaydet
  (süreç yeniden başlasa da geri gitmesin).
- `progressUpdatedAt`: gönderim anı DEĞİL, sayaçların en son değiştiği an.
- Bilinmeyen sayaç `null` (sıfır değil). Soru/cevap metni gönderme.
- `counters` alanı gövdede yoksa GMS saklanan sayaçları **korur** (sıfırlamaz); "bu gövdede yok" ile
  "sıfırlandı" farklı şeylerdir.
- `progressUpdatedAt`'i gönderim anı yaparsan donmuş bir ölçüm ekranda canlı görünür ve "ilerleme
  durdu" uyarısı hiç çıkmaz.

### 2. Tur özeti — `POST /api/centra-ai/runs/{runId}/rounds`
8 KB, 10/dk, **tur başına bir kez** (puanlama bittikten ve tut/geri al kararından sonra).

```json
{
  "roundNo": 3, "label": "tur-03",
  "changeNote": "≤300 karakter: o turda ne denendi",
  "decision": "kept",
  "avgScore": 71.4, "successPct": 68.0,
  "hallucinations": 2, "badIntegrity": 0, "fallbackCount": 5,
  "directPct": 34.0,
  "modeCounts": { "direct": 17, "rag": 28, "fallback": 5 },
  "avgLatencySec": 2.41, "p90LatencySec": 5.80,
  "ragAvgLatencySec": 3.62, "avgFirstTokenSec": 0.88,
  "groupScores": { "trap": 58.2, "gap": 64.0, "normal": 79.1 },
  "startedAt": "...Z", "finishedAt": "...Z"
}
```
- `decision`: `baseline` | `kept` | `reverted`
- `fallbackCount`: puanlamada `outputIntegrity == "fallback"` sayısı. `badIntegrity`: bos/kesik/hata.
- `modeCounts` toplamı `target`'ı aşarsa GMS 400 döner.
- `groupScores`: soru grupları `data/eval/eval_set.json`'dan türetilir (`source_type == "gap"` → gap;
  `scripts/make_eval_set.TRAP` kategorisine uyan golden → trap; diğerleri → normal).
- **İdempotans:** anahtar `runId + roundNo`. Aynı gövde → 200. Farklı gövde → **409**, saklanan
  değerler döner; üzerine yazmaya çalışma, 409'u logla ve rapora yaz.
- Metrikler `scripts/eval_summary.summarize` ile aynı tanımları kullanmalı (tek kaynak; o fonksiyonu
  genişlet, ikinci bir hesaplama yazma).

### 3. Oturum özeti — `PUT /api/centra-ai/runs/{runId}`
4 KB, 10/dk, oturum **başında ve sonunda**.

```json
{
  "startedAt": "...Z", "finishedAt": null,
  "userFeedback": "≤500 karakter: kullanıcının isteği",
  "stopReason": null,
  "baselineScore": 58.6, "finalScore": null,
  "keptCount": 0, "revertedCount": 0
}
```
- `stopReason`: `plateau` | `roundLimit` | `quota` | `error` | `manual`
- Oturum açılır açılmaz gönderilebilir; telemetri gelmeden de GMS koşu satırını açar, kullanıcının
  isteği kaybolmaz.

## Önerilen yapı

- `app/gms_reporter.py`: yapılandırma, gönderim kapısı, HTTP istemcisi (TLS, maskeleme, tekrar deneme).
- `data/eval/gms_state.json`: aktif oturumun durumu (runId, roundNo, phase, runStatus, startedAt,
  sequence, progressUpdatedAt). Tek doğruluk kaynağı.
- `python -m scripts.gms_report ...` CLI (geliştirme akışı bunu çağırır):
  - `session-start --feedback "..."` → yeni runId, PUT oturum
  - `phase measure|score|improve --round N` → durumu güncelle
  - `round-summary tur-03 --decision kept --note "..."` → POST tur özeti
  - `session-end --stop-reason plateau` → PUT oturum, runStatus Completed
  - `watch` → arka planda 20 sn'de bir telemetri; `answered`/`errors` sayaçlarını aktif turun
    `results.json`'ından okur
  - `--dry-run` → istek yapmadan gövdeyi ve hedefi (gizler maskeli) yazdır
- `scripts/run_eval.py`: her sorudan sonra `gms_state.json`'daki `progressUpdatedAt`'i güncelle (ya da
  watcher bunu `results.json`'ın değişiminden türetsin).

## Hata davranışı

GMS'e ulaşılamaması **asla** değerlendirmeyi ya da geliştirmeyi durdurmamalı. Gönderim hataları
loglanır (`data/eval/gms.log`), geliştirme devam eder. RAPOR.md'ye "GMS'e gönderim: başarılı / şu hata" notu düşülür.

## Bitince

1. `--dry-run` ile üç gövdenin doğru üretildiğini göster.
2. GMS uçları yayındaysa gerçek gönderimi bir kez dene (`session-start` + birkaç `watch` döngüsü +
   `session-end --stop-reason manual`), GMS ekranında göründüğünü kullanıcıya söyle.
3. `CLAUDE.md`'deki "Geliştirme" akışına bu CLI çağrılarını ekle (oturum başı/sonu, her aşama, her tur).
4. README'ye kısa bir bölüm ekle.
