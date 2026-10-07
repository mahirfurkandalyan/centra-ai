"""QA hattı deposundaki soru-cevapları bilgi tabanına aktarır (depoya yalnızca okuma erişimi).

Kullanım:
    python -m app.importer "C:\\Projects\\centra-chatbot"            # aktar + indeksle
    python -m app.importer "C:\\Projects\\centra-chatbot" --dry-run  # sadece say, yazma

Kaynaklar:
    Questions and Answers/Pack N/Answers/expected-answers-pack-N.json  -> golden cevaplar
    mds/CENTRA_Knowledge_Base_Gaps*.md                                  -> gap (düzeltilmiş) cevaplar
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

from . import ollama_client, store
from .parser import FaqEntry, parse_faq_markdown

# Önceki mesajlara atıf yapan sorular tek başına anlamsız, bilgi tabanına alınmaz
SKIP_CATEGORY = re.compile(r"bağlam", re.I)
_PACK_NO = re.compile(r"(\d+)")


def _load_json_list(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):  # {"items": [...]} gibi sarmalanmış biçimler
        data = next((v for v in data.values() if isinstance(v, list)), [])
    return [r for r in data if isinstance(r, dict)]


def _pack_sort_key(path: Path) -> int:
    m = _PACK_NO.search(path.parent.parent.name)
    return int(m.group(1)) if m else 0


def _golden_files(root: Path) -> list[Path]:
    """Birleşik dosyası (expected-answers-pack-N.json) olan pakette parça dosyalarını (-p01...) atlar.
    Birleşik dosyası olmayan paketlerde (ör. Pack 6: 6a, 6b) tüm parçalar alınır."""
    files = []
    for answers_dir in root.glob("Questions and Answers/Pack */Answers"):
        pack_no = _PACK_NO.search(answers_dir.parent.name)
        merged = answers_dir / f"expected-answers-pack-{pack_no.group(1)}.json" if pack_no else None
        files += [merged] if merged and merged.exists() else sorted(answers_dir.glob("expected-answers-pack-*.json"))
    return sorted(files, key=_pack_sort_key)


def load_golden(root: Path) -> tuple[list[tuple[str, list[FaqEntry]]], dict]:
    """Her paket için (dosya adı, kayıtlar) listesi döner."""
    report = {"files": 0, "records": 0, "skipped_context": 0, "skipped_empty": 0}
    result = []
    for ans_path in _golden_files(root):
        answers = _load_json_list(ans_path)
        # Golden dosyasında soru/kategori yoksa soru dosyasından tamamlanır
        q_path = ans_path.parent.parent / "Questions" / ans_path.name.replace("expected-answers", "questions")
        questions = {r.get("no"): r for r in _load_json_list(q_path)} if q_path.exists() else {}

        entries = []
        for a in answers:
            q = questions.get(a.get("no"), {})
            question = (a.get("question") or q.get("question") or "").strip()
            answer = (a.get("expectedAnswer") or "").strip()
            category = (a.get("category") or q.get("category") or "Genel").strip()
            if SKIP_CATEGORY.search(category):
                report["skipped_context"] += 1
            elif not question or not answer:
                report["skipped_empty"] += 1
            else:
                entries.append(FaqEntry(question, category, answer))
        report["files"] += 1
        report["records"] += len(entries)
        result.append((ans_path.name, entries))
    return result, report


def load_gaps(root: Path, extra_dirs: list[Path]) -> tuple[list[tuple[str, list[FaqEntry]]], dict]:
    report = {"files": 0, "records": 0, "errors": 0}
    result = []
    paths = sorted((root / "mds").glob("CENTRA_Knowledge_Base_Gaps*.md"))
    for d in extra_dirs:
        paths += sorted(d.rglob("*.md"))
    for md_path in paths:
        entries, errors = parse_faq_markdown(md_path.read_text(encoding="utf-8-sig"))
        if errors:
            print(f"  uyarı: {md_path.name}: {len(entries)} kayıt okundu, {len(errors)} blok okunamadı ({errors[0]})")
        report["files"] += 1
        report["records"] += len(entries)
        report["errors"] += len(errors)
        result.append((md_path.name, entries))
    return result, report


def index_pending(batch_size: int = 32) -> None:
    total = store.stats()["faq_pending_index"]
    done, started = 0, time.perf_counter()
    while rows := store.pending_embeddings(batch_size):
        ids = [r["id"] for r in rows]
        store.save_embeddings(ids, ollama_client.embed([r["question"] for r in rows]))
        done += len(ids)
        elapsed = time.perf_counter() - started
        eta = elapsed / done * (total - done)
        print(f"\r  indekslendi: {done}/{total}  (kalan ~{eta / 60:.0f} dk)   ", end="", flush=True)
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="QA hattı soru-cevaplarını bilgi tabanına aktarır")
    ap.add_argument("root", type=Path, help="QA hattı deposu, ör. C:\\Projects\\centra-chatbot")
    ap.add_argument("--dry-run", action="store_true", help="Sadece say, veritabanına yazma")
    ap.add_argument("--no-index", action="store_true", help="İndekslemeyi sunucuya bırak")
    ap.add_argument("--extra", type=Path, action="append", default=[],
                    help="Ek gap .md klasörü (alt klasörler dahil); birden fazla verilebilir")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")  # eski Windows konsollarında Türkçe karakter hatası olmasın

    if not (args.root / "Questions and Answers").is_dir():
        sys.exit(f"'{args.root}' içinde 'Questions and Answers' klasörü bulunamadı")
    for d in args.extra:
        if not d.is_dir():
            sys.exit(f"Ek klasör bulunamadı: {d}")

    golden, g_report = load_golden(args.root)
    gaps, m_report = load_gaps(args.root, args.extra)
    print(f"Golden: {g_report['files']} dosya, {g_report['records']} kayıt "
          f"(bağlam sorusu atlandı: {g_report['skipped_context']}, boş: {g_report['skipped_empty']})")
    print(f"Gap:    {m_report['files']} dosya, {m_report['records']} kayıt (ayrıştırma uyarısı: {m_report['errors']})")
    if args.dry_run:
        return

    store.init_db()
    totals = {"added": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    # Önce golden, sonra gap: gap aynı soruyu düzeltilmiş cevabıyla ezer (öncelik kuralı sıradan bağımsız da korunur)
    for source_type, batches in (("golden", golden), ("gap", gaps)):
        for name, entries in batches:
            for k, v in store.upsert_faqs(entries, name, source_type).items():
                totals[k] += v
    s = store.stats()
    print(f"Veritabanı: {totals['added']} yeni, {totals['updated']} güncellendi, "
          f"{totals['unchanged']} değişmedi, {totals['skipped']} atlandı (gap'te zaten var)")
    print(f"Toplam {s['faq_total']} kayıt {s['sources']}, indeks bekleyen: {s['faq_pending_index']}")

    if not args.no_index and s["faq_pending_index"]:
        print("İndeksleniyor (Ctrl+C ile durdurabilirsiniz; kaldığı yerden devam eder)...")
        index_pending()
    print("Tamam.")


if __name__ == "__main__":
    main()
