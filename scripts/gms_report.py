"""Geliştirme oturumunun ilerlemesini GMS'e gönderen CLI.

Sözleşme: `docs/GMS_GONDERICI.md`. Geliştirme akışı (CLAUDE.md) bu komutları çağırır.

    python -m scripts.gms_report config
    python -m scripts.gms_report session-start --feedback "cevaplar çok uzun"
    python -m scripts.gms_report phase measure --round 2 --label tur-02-esik
    python -m scripts.gms_report round-summary tur-02-esik --decision kept --note "DIRECT 0.75"
    python -m scripts.gms_report watch
    python -m scripts.gms_report session-end --stop-reason plateau

Her komuta `--dry-run` eklenebilir: istek yapılmaz, hedef ve gövde (gizler maskeli) yazdırılır.

GMS'e ulaşılamaması değerlendirmeyi ya da geliştirmeyi DURDURMAZ: hata `data/eval/gms.log`'a
yazılır ve komut yine 0 ile çıkar. Tek istisna, gövdenin yerel doğrulamadan geçmemesi (çıkış 2) --
o bir kod hatasıdır, sessizce geçilmemeli.
"""
import argparse
import json
import sys
import time

from app import config, gms_reporter as gms
from scripts.eval_summary import summarize

EVAL_DIR = config.DATA_DIR / "eval"

# Tek seferlik komutlar geliştirmeyi bekletmesin: kısa, sınırlı yeniden deneme.
ONESHOT_MAX_ATTEMPTS = 3
ONESHOT_MAX_WAIT_S = 15


def _counters(label: str | None) -> dict | None:
    """Aktif turun sayaçları. Bilinmiyorsa None döner (gövdeye hiç konmaz)."""
    if not label:
        return None
    run_dir = EVAL_DIR / "runs" / label
    try:
        results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        results = None
    target = None
    try:
        target = json.loads((run_dir / "meta.json").read_text(encoding="utf-8")).get("target")
    except (OSError, ValueError):
        try:
            target = len(json.loads((EVAL_DIR / "eval_set.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            target = None
    if results is None:
        # Ölçüm henüz başlamadı: hedef biliniyorsa onu bildir, bilinmeyen sayaç None kalır.
        return {"target": target, "answered": None, "errors": None} if target else None
    return {
        "target": target,
        "answered": len(results),
        "errors": sum(1 for r in results if r.get("status") != "ok"),
    }


def _run_times(label: str) -> tuple[str | None, str | None]:
    """Turun başlangıç/bitiş zamanı (run_eval'in yazdığı meta.json)."""
    try:
        meta = json.loads((EVAL_DIR / "runs" / label / "meta.json").read_text(encoding="utf-8"))
        return meta.get("started_at"), meta.get("finished_at")
    except (OSError, ValueError):
        return None, None  # eski turlarda meta.json yok; GMS alanı boş kabul eder


def _print_dry_run(cfg: gms.GmsConfig, method: str, path: str, body: dict) -> None:
    print(f"[dry-run] {method} {(cfg.base_url or '(tanımsız)').rstrip('/')}{path}")
    print("[dry-run] başlıklar: " + json.dumps(gms.describe_headers(cfg), ensure_ascii=False))
    allowed, reasons = gms.assert_send_allowed(cfg)
    print(f"[dry-run] gönderim kapısı: {'açık' if allowed else 'KAPALI -> ' + '; '.join(reasons)}")
    print("[dry-run] gövde:")
    print(json.dumps(body, ensure_ascii=False, indent=2))


def deliver(cfg: gms.GmsConfig, method: str, path: str, body: dict, state: dict,
            kind: str, dry_run: bool) -> dict:
    """Gönderir, GMS yanıtına göre kararı uygular, loglar. İstisna fırlatmaz."""
    if dry_run:
        _print_dry_run(cfg, method, path, body)
        return {"action": "dry-run"}

    waited = 0
    decision = {"action": "halt-unknown", "reason": "hiç denenmedi"}
    for attempt in range(1, ONESHOT_MAX_ATTEMPTS + 1):
        result = gms.send_json(cfg, method, path, body)
        if result.get("blocked"):
            gms.log(f"{kind}.blocked", {"reason": result["blocked"]})
            print(f"GMS'e gönderilmedi (kapı kapalı): {result['blocked']}")
            return {"action": "blocked", "reason": result["blocked"]}
        decision = gms.decide_next_action(
            result["status"], result["body"], result["network_error"],
            attempt=attempt, local_sequence=state.get("sequence"),
        )
        gms.raise_sequence_floor(state, decision.get("sequence_floor"))
        gms.log(f"{kind}.{decision['action']}", {
            "status": result["status"], "attempt": attempt, "reason": decision["reason"],
        })
        if decision["action"] != "backoff":
            break
        delay = min(decision["delay_s"], ONESHOT_MAX_WAIT_S - waited)
        if delay <= 0 or attempt == ONESHOT_MAX_ATTEMPTS:
            break
        print(f"GMS geçici hata ({decision['reason']}); {delay} sn sonra tekrar.")
        time.sleep(delay)
        waited += delay

    label = {"ok": "gönderildi", "conflict": "409 (üzerine yazılmadı)",
             "resync": "sequence tabanı yükseltildi"}.get(decision["action"], decision["action"])
    print(f"GMS {kind}: {label} — {decision['reason']}")
    if decision["action"] == "conflict" and decision.get("stored"):
        print("GMS'te kayıtlı değerler: " + json.dumps(decision["stored"], ensure_ascii=False)[:400])
    return decision


DRY_RUN_RUN_ID = "00000000-0000-0000-0000-000000000000"


def _require_session(state: dict, dry_run: bool) -> None:
    """Oturum yoksa dur. Kuru çalıştırmada gövde yine gösterilebilsin diye yer tutucu konur."""
    if state.get("runId"):
        return
    if dry_run:
        state["runId"] = DRY_RUN_RUN_ID
        state["startedAt"] = state.get("startedAt") or gms.utc_now()
        return
    print("Oturum yok; önce session-start çalıştırın.", file=sys.stderr)
    sys.exit(2)


def _validate_or_exit(errors: list[str], kind: str) -> None:
    if errors:
        print(f"HATA: {kind} gövdesi yerel doğrulamadan geçmedi:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        gms.log(f"{kind}.invalid", {"errors": errors})
        sys.exit(2)


# --- komutlar -----------------------------------------------------------------------------


def cmd_config(args, cfg: gms.GmsConfig) -> None:
    print(json.dumps(gms.describe_config(cfg), ensure_ascii=False, indent=2))
    allowed, reasons = gms.assert_send_allowed(cfg)
    print(f"gönderim kapısı: {'açık' if allowed else 'KAPALI'}")
    for r in reasons:
        print(f"  - {r}")
    state = gms.load_state()
    print("durum: " + json.dumps(
        {k: state[k] for k in ("runId", "roundNo", "phase", "runStatus", "sequence", "activeLabel")},
        ensure_ascii=False))


def cmd_session_start(args, cfg: gms.GmsConfig) -> None:
    state = gms.load_state()
    state.update({
        "runId": gms.new_run_id(),
        "roundNo": 1,
        "phase": "measure",
        "runStatus": "Running",
        "startedAt": gms.utc_now(),
        "finishedAt": None,
        "sequence": 0,
        "progressUpdatedAt": None,
        "counters": None,
        "activeLabel": args.label,
        "userFeedback": args.feedback,
        "stopReason": None,
        "baselineScore": None,
        "finalScore": None,
        "keptCount": 0,
        "revertedCount": 0,
        "sentRounds": {},
    })
    body = gms.build_session(state)
    _validate_or_exit(gms.validate_session(body), "session")
    deliver(cfg, "PUT", gms.SESSION_PATH.format(run_id=state["runId"]), body, state, "session", args.dry_run)
    if not args.dry_run:
        gms.save_state(state)
        print(f"Oturum açıldı: runId={state['runId']}")


def cmd_phase(args, cfg: gms.GmsConfig) -> None:
    state = gms.load_state()
    _require_session(state, args.dry_run)
    state["phase"] = args.phase
    state["runStatus"] = "Running"
    if args.round:
        state["roundNo"] = args.round
    if args.label:
        state["activeLabel"] = args.label
    gms.note_counters(state, _counters(state.get("activeLabel")))
    state["sequence"] = gms.next_sequence(state)
    body = gms.build_telemetry(state)
    _validate_or_exit(gms.validate_telemetry(body), "telemetry")
    deliver(cfg, "POST", cfg.telemetry_path, body, state, "telemetry", args.dry_run)
    if not args.dry_run:
        gms.save_state(state)


def cmd_round_summary(args, cfg: gms.GmsConfig) -> None:
    state = gms.load_state()
    _require_session(state, args.dry_run)
    if args.round:
        state["roundNo"] = args.round
    metrics = summarize(args.label, args.note or "")
    started_at, finished_at = _run_times(args.label)
    body = gms.build_round(state, metrics, args.decision, args.note or "", started_at, finished_at)
    errors = gms.validate_round(body)
    # modeCounts toplamı target'ı aşarsa GMS 400 döner; yerelde de geçmesin.
    target = (_counters(args.label) or {}).get("target")
    modes = body.get("modeCounts") or {}
    if isinstance(target, int) and sum(modes.values()) > target:
        errors.append(f"modeCounts toplamı ({sum(modes.values())}) > target ({target})")
    _validate_or_exit(errors, "round")

    decision = deliver(cfg, "POST", gms.ROUNDS_PATH.format(run_id=state["runId"]), body,
                       state, "round", args.dry_run)
    if args.dry_run:
        return
    if args.decision == "baseline":
        state["baselineScore"] = metrics["avg_score"]
    elif args.decision == "kept":
        state["keptCount"] = int(state.get("keptCount") or 0) + 1
    else:
        state["revertedCount"] = int(state.get("revertedCount") or 0) + 1
    # finalScore = kodun ŞU ANKİ hâlinin puanı; geri alınan tur onu değiştirmez.
    if args.decision in ("baseline", "kept"):
        state["finalScore"] = metrics["avg_score"]
    state["sentRounds"][str(state["roundNo"])] = decision["action"]
    gms.save_state(state)


def cmd_session_end(args, cfg: gms.GmsConfig) -> None:
    state = gms.load_state()
    _require_session(state, args.dry_run)
    state["finishedAt"] = gms.utc_now()
    state["stopReason"] = args.stop_reason
    state["runStatus"] = "Failed" if args.stop_reason == "error" else "Completed"
    body = gms.build_session(state)
    _validate_or_exit(gms.validate_session(body), "session")
    deliver(cfg, "PUT", gms.SESSION_PATH.format(run_id=state["runId"]), body, state, "session", args.dry_run)
    if args.dry_run:
        return
    # Ekranın son hâli doğru görünsün: kapanış telemetrisi de gidiyor.
    state["sequence"] = gms.next_sequence(state)
    tele = gms.build_telemetry(state)
    if not gms.validate_telemetry(tele):
        deliver(cfg, "POST", cfg.telemetry_path, tele, state, "telemetry", False)
    gms.save_state(state)
    print(f"Oturum kapandı: {args.stop_reason}")


def cmd_watch(args, cfg: gms.GmsConfig) -> None:
    """Arka planda 20 sn'de bir telemetri. Sayaçlar aktif turun results.json'ından okunur."""
    started = time.monotonic()
    tick = 0
    while True:
        state = gms.load_state()
        if not state.get("runId"):
            print("Oturum yok; watch durdu.", file=sys.stderr)
            return
        if args.label:
            state["activeLabel"] = args.label
        gms.note_counters(state, _counters(state.get("activeLabel")))
        state["sequence"] = gms.next_sequence(state)
        body = gms.build_telemetry(state)
        errors = gms.validate_telemetry(body)
        if errors:
            gms.log("telemetry.invalid", {"errors": errors})
            print("Telemetri gövdesi geçersiz: " + "; ".join(errors), file=sys.stderr)
        else:
            decision = deliver(cfg, "POST", cfg.telemetry_path, body, state, "telemetry", args.dry_run)
            if decision["action"] in ("halt-auth", "halt-run", "halt-missing-route", "blocked"):
                print(f"watch durdu: {decision['reason']}")
                if not args.dry_run:
                    gms.save_state(state)
                return
        if not args.dry_run:
            gms.save_state(state)
        tick += 1
        if args.once or (args.max_seconds and time.monotonic() - started >= args.max_seconds):
            return
        time.sleep(args.interval)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="python -m scripts.gms_report", description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="istek yapma, gövdeyi ve hedefi yazdır")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config", help="maskeli yapılandırma ve gönderim kapısı").set_defaults(fn=cmd_config)

    p = sub.add_parser("session-start", help="yeni oturum: runId üret, oturum özetini gönder")
    p.add_argument("--feedback", default=None, help="kullanıcının isteği (≤500 karakter)")
    p.add_argument("--label", default=None, help="ilk turun adı, ör. tur-01-baslangic")
    p.set_defaults(fn=cmd_session_start)

    p = sub.add_parser("phase", help="aşamayı güncelle ve bir telemetri gönder")
    p.add_argument("phase", choices=gms.PHASES)
    p.add_argument("--round", type=int, default=None)
    p.add_argument("--label", default=None)
    p.set_defaults(fn=cmd_phase)

    p = sub.add_parser("round-summary", help="tur özetini gönder (puanlama ve karar sonrası)")
    p.add_argument("label", help="tur adı, ör. tur-02-esik")
    p.add_argument("--decision", choices=gms.DECISIONS, required=True)
    p.add_argument("--note", default="", help="o turda ne denendi (≤300 karakter)")
    p.add_argument("--round", type=int, default=None)
    p.set_defaults(fn=cmd_round_summary)

    p = sub.add_parser("session-end", help="oturumu kapat")
    p.add_argument("--stop-reason", choices=gms.STOP_REASONS, required=True)
    p.set_defaults(fn=cmd_session_end)

    p = sub.add_parser("watch", help="20 sn'de bir canlı telemetri")
    p.add_argument("--label", default=None)
    p.add_argument("--interval", type=int, default=gms.CADENCE_S)
    p.add_argument("--once", action="store_true", help="tek tur gönder ve çık")
    p.add_argument("--max-seconds", type=int, default=None, help="bu süre sonunda dur")
    p.set_defaults(fn=cmd_watch)

    args = ap.parse_args()
    cfg = gms.load_config()
    args.fn(args, cfg)


if __name__ == "__main__":
    main()
