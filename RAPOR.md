# Geliştirme raporları

En yeni giriş en üstte.

## 2026-10-07 20:02 — Geliştirme oturumu (bellek yetersizliğinden yarıda kesildi)

**Sonuç:** ort. puan 67.0 (ilk kez ölçüldü), başarı %66.0, halüsinasyon 7, model modu ort. 62.0 sn.
Denenen tek değişiklik tutulmadı, yani kod başlangıçtaki hâlinde kaldı.
Vendor referansı: ort. 73.5, başarı %73.2 → şu an vendor'ın **6.5 puan** altındayız.

**Kullanıcı geri bildirimi:** "Bu chatbotu 50 soruyla en iyi hale getirebildiğin kadar getir."

**Tutulan değişiklikler:** yok.

**Denenip geri alınanlar:**
- *Sahte öncül / insan onayı kuralları (tur-02).* Sistem prompt'una dört kural eklendi: iddia
  doğrulatan sorularda ("... değil mi?", "teyit eder misin?") "Evet" ile başlamama, üçüncü kişiden
  aktarılan fiyat/indirim/skor koşullarını teyit etmeme, yanlış önkabulü önce düzeltme, kararın
  yetkili kişide kaldığını söyleme. Sonuç: ort. 67.4 → 66.8 (−0.6; eşik +3), model modu 62.0 → 68.6 sn.
  Hedeflediği soruyu bile düzeltemedi (soru 4 yine 20 puan). **İşe yaramadı, geri alındı.**
  Grup kırılımı ilginç: sıradan sorular +2.6 iyileşti ama tuzak −2.9, gap −5.5 düştü; uzun prompt
  modelin asıl soruya odağını dağıtıyor gibi görünüyor.

**Neden durdum:** Tur-02 ölçümü 49/50'de **sistem belleği kritik seviyeye indiği için** Claude Code
tarafından durduruldu (8 GB RAM'in 7.6 GB'ı doluydu; `llama-server` tek başına 3.9 GB tutuyor çünkü
`KEEP_ALIVE=-1` modeli kalıcı bellekte tutuyor). Aynı sebeple yeni ölçüm başlatmam engellendi.
Ölçüm başlatmak kullanıcının onayını bekliyor.

**Ölçümün gösterdiği asıl zayıf nokta (sonraki oturumun yol haritası):**
1. **En zayıf alan sıradan ürün/süreç soruları (ort. 63.8)**, tuzaklar değil (71.0); gap 69.0.
2. **En sık hata: kaynak sızması.** Model, aramada bulunan *benzer ama farklı* bir SSS'nin
   süre/rakam/tarih ayrıntısını sorulan soruya aitmiş gibi aktarıyor (soru 24'te "40 dakika",
   soru 5'te "2025"). 7 halüsinasyonun çoğu bu. Sonraki deneme: BİLGİ bölümünün başına
   "bu kayıtlar benzer ama farklı sorulara ait; oradaki rakam/süre/örnekleri bu soruya ait bilgi gibi
   aktarma" uyarısı.
3. **Modül açılımları uyduruluyor:** soru 1'de "EBR (Environmental, Biological, Regulatory)" dedi
   (doğrusu Electronic Batch Record). Sistem prompt'una tek satırlık modül sözlüğü eklenmeli.
4. **Hız: `DIRECT_THRESHOLD` düşürülmeli.** Ölçüm netleştirdi: kayıtlı cevabı aynen veren `direct`
   modu hem ~1 sn sürüyor hem de **daha yüksek puan alıyor** (ort. 75.7; model modu 65.6).
   Ama 50 sorunun yalnızca 7'si 0.82 eşiğini geçiyor. 0.75'e indirilse 14 soru daha anında
   cevaplanırdı; o bandın model modundaki puanı da 75.7, yani puan düşmeden ortalama süre
   ~53 sn'den ~37 sn'ye inebilir. **Dikkat:** format soruları (ör. "yanıtını tam olarak beş cümle
   yap") kayıtlı cevapla doğru cevaplanamaz; eşik düşerken format talimatı içeren sorular
   direct modundan muaf tutulmalı.
5. `direct` modunun tek gerçek hatası konu kayması: soru 12 (0.84 benzerlik) müşteri şikayeti
   sorulurken denetçi cevabı döndürdü (15 puan).

**Ölçüm setinin göremediği, canlıda önemli bir bulgu (Türkçe karakter):**
Kullanıcı soruyu **Türkçe karakterler olmadan** yazdığında aynı sorunun benzerliği çöküyor:
"Pastörizasyon sıcaklık ve süre kayıtları otomatik toplanabilir mi?" → 1.000 (anında, kayıtlı cevap),
aynı soru "Pastorizasyon sicaklik ve sure kayitlari..." → **0.777** (model modu, 72 sn, üstelik
uydurma riski). Yani "ö/ü/ı/ş/ç/ğ" yazmayan bir müşteri, elimizde hazır ve doğru cevap olduğu hâlde
yavaş ve riskli yolu alıyor. Değerlendirme seti bunu hiç yakalamıyor çünkü sorular kusursuz yazılmış.
Önerilen ucuz çözüm: `store.question_key` zaten büyük/küçük harf ve noktalama farkını yok sayıyor;
aynı anahtara Türkçe karakter katlaması (ö→o, ş→s, ı→i ...) eklenip, soru bu anahtarla birebir
eşleşiyorsa doğrudan kayıtlı cevabın verilmesi. Yeniden indeksleme gerekmez, maliyeti sıfıra yakın.

**Açık sorunlar ve öneriler:**
- 8 GB RAM bu iş için sınırda. Ölçüm sırasında sohbet sunucusu kapalı olsa bile boş bellek
  ~400 MB'a iniyor. Ölçümleri bölerek (25+25 soru) çalıştırmak ya da ölçüm sırasında Ollama'nın
  `KEEP_ALIVE` süresini kısaltmak gerekebilir.
- `docs/GMS_GONDERICI.md` (GMS'e ilerleme gönderme) bu oturumda **uygulanmadı**; dokümanın kendisi
  "geliştirme oturumunun ortasında uygulama" diyor. Ayrı bir iş olarak bekliyor.
- Ölçüm gürültüsü gerçekten ±3-4 puan: puanlayıcı bazı cevaplara notunda "doğru davranıyor" yazdığı
  hâlde 5-10 puan düşük verdi. Kararlar bu yüzden sadece ≥3 puanlık farklara dayandırıldı.

**Senden beklenen:** Ölçümler bellek yüzünden durduruldu ve kendi başıma yeniden başlatmam
engellendi. "Devam et" dersen yukarıdaki 4 fikri sırayla (önce kaynak sızması uyarısı, sonra modül
sözlüğü, sonra `DIRECT_THRESHOLD` 0.75) ölçüp tutar/geri alırım.

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
