# Geliştirme raporları

En yeni giriş en üstte.

## 2026-10-07 — MVP kurulumu (başlangıç noktası)

**Sonuç:** Chatbot sunucuda çalışıyor. Henüz puanlı ölçüm yapılmadı; ilk geliştirme oturumu başlangıç
ölçümüyle başlayacak.

**Yapılanlar:**
- Yerel LLM kuruldu: Ollama + `qwen3:4b-instruct` (cevap) + `bge-m3` (anlamsal arama).
- QA hattındaki tüm soru-cevaplar bilgi tabanına aktarıldı: 5570 kayıt (1145 gap, 4425 golden).
- Üç cevap modu: kayıtlı cevabı aynen verme, benzer kayıtlarla model cevabı, bilgi yoksa yönlendirme.
- Admin panel: SSS md yükleme (vendor'daki ile aynı format), kayıt listesi, konuşma geçmişi.
- Değerlendirme araçları: sabit 50 soruluk set, leave-one-out ölçüm, QA hattı kurallarıyla puanlama.

**Elle yapılan ilk denemeler:**
- Bilinen sorular (ör. telefon numarası) 1-2 sn'de doğru cevaplandı.
- Odak dışı soru (uzay mekiği) doğru şekilde reddedildi, uydurma yok.
- Model gerektiren sorular ilk başta ~97 sn sürüyordu. Neden: iki model 2 GB ekran kartına sığmayıp
  her soruda birbirini bellekten atıyordu. Sohbet modeli CPU'ya alınınca ~46 sn'ye indi; prompt ve
  kaynak kısaltmasıyla daha da inmesi bekleniyor (ölçülmedi).

**Açık sorunlar:**
- Model modunda cevaplar yavaş (donanım sınırı: 8 GB RAM, zayıf GPU).
- Sohbet hafızası yok; her soru tek başına cevaplanıyor.
- Sitede gömülü widget yok; sadece kendi sohbet sayfası var.

**Senden beklenen:** Bir sonraki adım geliştirme oturumu. Ne istediğini kendi cümlelerinle yazman yeterli.
