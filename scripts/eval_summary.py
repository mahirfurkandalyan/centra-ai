"""Bir turun sonuçlarını ve puanlarını özetler, tur geçmişine ekler.

Kullanım:
    python -m scripts.eval_summary tur-03 --note "RAG_TOP_K=1 denendi"
    python -m scripts.eval_summary --history          # tüm turların tablosu

Girdi: data/eval/runs/<tur>/results.json ve scores.json
scores.json: [{"no": 1, "score": 85, "verdict": "Başarılı", "outputIntegrity": "normal",
               "hallucination": false, "note": "..."}, ...]
"""
import argparse
import json
import statistics
import sys

from app import config

EVAL_DIR = config.DATA_DIR / "eval"
HISTORY = EVAL_DIR / "history.jsonl"
COLUMNS = [
    ("label", "Tur"), ("avg_score", "Ort. puan"), ("success_pct", "Başarı %"), ("hallucinations", "Halüs."),
    ("bad_integrity", "Boş/kesik/hata"), ("direct_pct", "Anında %"), ("rag_avg_s", "Model ort. sn"),
    ("all_p90_s", "p90 sn"), ("note", "Not"),
]


def summarize(label: str, note: str) -> dict:
    run_dir = EVAL_DIR / "runs" / label
    results = {r["no"]: r for r in json.loads((run_dir / "results.json").read_text(encoding="utf-8"))}
    scores = {s["no"]: s for s in json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))}
    missing = set(results) - set(scores)
    if missing:
        sys.exit(f"Puanı eksik sorular: {sorted(missing)}")

    vals = [scores[n]["score"] for n in results]
    lat = sorted(r["latency_ms"] or 0 for r in results.values())
    rag_lat = [r["latency_ms"] for r in results.values() if r["mode"] in ("rag", "fallback") and r["latency_ms"]]
    return {
        "label": label,
        "n": len(vals),
        "avg_score": round(statistics.mean(vals), 1),
        # QA hattıyla aynı tanım: 70 ve üstü başarılı sayılır
        "success_pct": round(100 * sum(v >= 70 for v in vals) / len(vals), 1),
        "hallucinations": sum(bool(scores[n].get("hallucination")) for n in results),
        "bad_integrity": sum(scores[n].get("outputIntegrity") in ("bos", "kesik", "hata") for n in results),
        "direct_pct": round(100 * sum(r["mode"] == "direct" for r in results.values()) / len(results), 1),
        "rag_avg_s": round(statistics.mean(rag_lat) / 1000, 1) if rag_lat else None,
        "all_p90_s": round(lat[int(len(lat) * 0.9) - 1] / 1000, 1) if lat else None,
        "note": note,
    }


def print_table(rows: list[dict]) -> None:
    print("| " + " | ".join(h for _, h in COLUMNS) + " |")
    print("|" + "---|" * len(COLUMNS))
    for r in rows:
        print("| " + " | ".join("" if r.get(k) is None else str(r.get(k)) for k, _ in COLUMNS) + " |")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("label", nargs="?")
    ap.add_argument("--note", default="")
    ap.add_argument("--history", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")

    if args.label:
        row = summarize(args.label, args.note)
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False, indent=2))
    if args.history or not args.label:
        rows = [json.loads(line) for line in HISTORY.read_text(encoding="utf-8").splitlines() if line.strip()]
        print_table(rows)


if __name__ == "__main__":
    main()
