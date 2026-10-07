"""Değerlendirme setini bota sorar (sunucu gerekmez, Ollama açık olmalı).

Kullanım:
    python -m scripts.run_eval tur-03
    -> data/eval/runs/tur-03/results.json

Not: Sohbet sunucusu (run.ps1) aynı anda çalışıyorsa ölçülen süreler bozulur; kapalı olmalı.
"""
import argparse
import json
import sys
import time

from app import config, rag

EVAL_DIR = config.DATA_DIR / "eval"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("label", help="Tur adı, ör. tur-00-baseline")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")

    items = json.loads((EVAL_DIR / "eval_set.json").read_text(encoding="utf-8"))
    out_dir = EVAL_DIR / "runs" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    started = time.perf_counter()
    for item in items:
        meta, done, parts = {}, {}, []
        try:
            for ev in rag.answer_stream(item["question"], exclude_ids={item["faq_id"]}, log=False):
                if ev["type"] == "meta":
                    meta = ev
                elif ev["type"] == "token":
                    parts.append(ev["text"])
                elif ev["type"] == "done":
                    done = ev
            status = "ok"
        except Exception as exc:  # hata da bir sonuçtur, puanlamada "hata" sayılır
            status = f"hata: {exc}"
        results.append({
            "no": item["no"],
            "category": item["category"],
            "question": item["question"],
            "expected": item["expected"],
            "answer": "".join(parts),
            "status": status,
            "mode": meta.get("mode"),
            "similarity": meta.get("score"),
            "sources": [s["question"] for s in meta.get("sources", [])],
            "latency_ms": done.get("latency_ms"),
            "first_token_ms": done.get("first_token_ms"),
        })
        (out_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{len(results)}/{len(items)}] {meta.get('mode')} {done.get('latency_ms', 0) / 1000:.1f} sn  "
              f"(geçen {(time.perf_counter() - started) / 60:.1f} dk)", flush=True)

    print(f"Bitti -> {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
