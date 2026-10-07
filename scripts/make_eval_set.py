"""Bilgi tabanından sabit bir değerlendirme seti çıkarır (her turda AYNI set kullanılmalı).

Kullanım:
    python -m scripts.make_eval_set            # data/eval/eval_set.json (varsa dokunmaz)
    python -m scripts.make_eval_set --force    # yeniden üret (tur karşılaştırmaları bozulur!)

Değerlendirme leave-one-out çalışır: her test sorusunun kendi kaydı aramada gizlenir, bot o soruyu
"ilk kez görüyormuş" gibi cevaplar. Beklenen cevap gizlenen kaydın cevabıdır.
"""
import argparse
import json
import random
import re
import sys

from app import config, store

OUT = config.DATA_DIR / "eval" / "eval_set.json"
SEED = 42
# Vendor'un QA hattında en çok puan kaybettiği tuzak/sınır kategorileri
TRAP = re.compile(
    r"halüsinasyon|güvenlik|etik|dürüstlük|yanlış önerme|tuzak|rakam|taahhüt|otonom|odak dışı|format", re.I
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--size", type=int, default=50)
    args = ap.parse_args()

    if OUT.exists() and not args.force:
        sys.exit(f"{OUT} zaten var; turlar karşılaştırılabilir kalsın diye üzerine yazılmadı (--force ile zorla).")

    with store.connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, question, module, answer, source_type FROM faqs WHERE embedding IS NOT NULL ORDER BY id"
        )]
    rng = random.Random(SEED)
    golden = [r for r in rows if r["source_type"] == "golden"]
    gap = [r for r in rows if r["source_type"] == "gap"]
    trap = [r for r in golden if TRAP.search(r["module"])]
    normal = [r for r in golden if not TRAP.search(r["module"])]

    n_trap, n_gap = round(args.size * 0.3), round(args.size * 0.2)
    picked = (
        rng.sample(trap, min(n_trap, len(trap)))
        + rng.sample(gap, min(n_gap, len(gap)))
    )
    picked_ids = {r["id"] for r in picked}
    rest = [r for r in normal if r["id"] not in picked_ids]
    picked += rng.sample(rest, min(args.size - len(picked), len(rest)))
    if len(picked) < args.size:  # havuzlardan biri yetersizse kalan herhangi bir kayıtla tamamla
        picked_ids = {r["id"] for r in picked}
        rest = [r for r in rows if r["id"] not in picked_ids]
        picked += rng.sample(rest, min(args.size - len(picked), len(rest)))
    rng.shuffle(picked)
    counts = {
        "tuzak": sum(TRAP.search(r["module"]) is not None and r["source_type"] == "golden" for r in picked),
        "gap": sum(r["source_type"] == "gap" for r in picked),
    }

    items = [
        {
            "no": i,
            "faq_id": r["id"],
            "source_type": r["source_type"],
            "category": r["module"],
            "question": r["question"],
            "expected": r["answer"],
        }
        for i, r in enumerate(picked, 1)
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(items)} soru -> {OUT}  (tuzak: {counts['tuzak']}, gap: {counts['gap']}, "
          f"diğer: {len(items) - counts['tuzak'] - counts['gap']})")


if __name__ == "__main__":
    main()
