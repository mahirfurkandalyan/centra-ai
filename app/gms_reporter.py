"""Geliştirme oturumunun ilerlemesini GMS'in "centra-ai" ekranına gönderen parça.

Sözleşme: `docs/GMS_GONDERICI.md`. Referans uygulama QA hattının `gms/reporter.js` dosyası
(salt okunur); gönderim kapısı, maskeleme ve geri çekilme kuralları oradakiyle aynı.

Buradaki hiçbir fonksiyon istisna fırlatmaz: GMS'e ulaşılamaması değerlendirmeyi ya da
geliştirmeyi durdurmamalı. Ağ hatası da bir sonuçtur, çağıran onu `action` alanından okur.

Gizli bilgi (anahtar, giz) hiçbir koşulda yazdırılmaz; yalnızca isteğin başlığına konur.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import config

# --- Sözleşme sabitleri -------------------------------------------------------------------

KEY_HEADER = "X-GMS-CentraAI-Key"
SECRET_HEADER = "X-GMS-CentraAI-Secret"

DEFAULT_TELEMETRY_PATH = "/api/centra-ai/telemetry"
ROUNDS_PATH = "/api/centra-ai/runs/{run_id}/rounds"
SESSION_PATH = "/api/centra-ai/runs/{run_id}"

RUNNER_VERSION = "1.0.0"
CADENCE_S = 20  # canlı telemetri kadansı (30/dk sınırının çok altında)

# Gövde boyu sınırları (GMS reddeder)
TELEMETRY_MAX_BYTES = 16 * 1024
ROUND_MAX_BYTES = 8 * 1024
SESSION_MAX_BYTES = 4 * 1024

CHANGE_NOTE_MAX = 300
USER_FEEDBACK_MAX = 500
MAX_ROUND_NO = 12

PHASES = ("measure", "score", "improve")
RUN_STATUSES = ("Running", "Idle", "Completed", "Stopped", "Failed")
DECISIONS = ("baseline", "kept", "reverted")
STOP_REASONS = ("plateau", "roundLimit", "quota", "error", "manual")

# Geri çekilme: referans uygulamayla aynı
BACKOFF_BASE_S = 5
BACKOFF_MAX_S = 15 * 60
BACKOFF_MAX_ATTEMPTS = 8
AUTH_COOLDOWN_S = 30 * 60

SEND_TIMEOUT_S = 10
MAX_RESPONSE_BYTES = 64 * 1024

STATE_PATH = config.DATA_DIR / "eval" / "gms_state.json"
LOG_PATH = config.DATA_DIR / "eval" / "gms.log"


def utc_now() -> str:
    """GMS'in beklediği biçim: milisaniyeli ISO 8601, UTC, "Z" sonlu."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# --- Yapılandırma -------------------------------------------------------------------------


@dataclass(frozen=True)
class GmsConfig:
    base_url: str | None
    telemetry_path: str
    key: str | None
    secret: str | None  # asla yazdırılmaz
    ca_path: str | None


def load_config(env: dict[str, str] | None = None) -> GmsConfig:
    e = env if env is not None else os.environ
    return GmsConfig(
        base_url=e.get("GMS_CENTRA_AI_BASE_URL") or None,
        telemetry_path=e.get("GMS_CENTRA_AI_TELEMETRY_PATH") or DEFAULT_TELEMETRY_PATH,
        key=e.get("GMS_CENTRA_AI_KEY") or None,
        secret=e.get("GMS_CENTRA_AI_SECRET") or None,
        ca_path=e.get("GMS_CENTRA_AI_CA") or _default_ca_path(e),
    )


def _default_ca_path(env: dict[str, str]) -> str | None:
    """GMS kurumsal olmayan bir kök sertifika kullanıyor; güven köküne o kök EKLENİR.

    Doğrulamayı gevşeten ya da kapatan bir seçenek bu dosyada hiç yoktur.
    """
    for candidate in (r"C:\gms\gms-public.pem", env.get("NODE_EXTRA_CA_CERTS")):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def describe_config(cfg: GmsConfig) -> dict:
    """Loglanabilir özet: giz asla görünmez, anahtar değeri de gösterilmez."""
    return {
        "base_url": cfg.base_url or "(tanımsız)",
        "telemetry_path": cfg.telemetry_path,
        "key": f"(ayarlı, {len(cfg.key)} karakter)" if cfg.key else "(tanımsız)",
        "secret": "(ayarlı, gizli)" if cfg.secret else "(tanımsız)",
        "ca_path": cfg.ca_path or "(tanımsız - sistem kök listesi)",
    }


def describe_headers(cfg: GmsConfig) -> dict:
    """Gönderilecek başlıkların ADLARI; değerler hiçbir çıktıya girmez."""
    return {
        "Content-Type": "application/json",
        KEY_HEADER: "(gizli)" if cfg.key else "(tanımsız)",
        SECRET_HEADER: "(gizli)" if cfg.secret else "(tanımsız)",
    }


def assert_send_allowed(cfg: GmsConfig) -> tuple[bool, list[str]]:
    """Gönderim kapısı. Güvenli varsayılan: https değilse ya da kimlik eksikse hiç istek yapılmaz."""
    reasons: list[str] = []
    if not cfg.base_url:
        reasons.append("GMS_CENTRA_AI_BASE_URL tanımsız")
    else:
        try:
            scheme = httpx.URL(cfg.base_url).scheme
        except Exception:
            scheme = ""
            reasons.append("GMS_CENTRA_AI_BASE_URL geçersiz")
        if scheme and scheme != "https":
            reasons.append(f"https olmayan bağlantı üzerinden kimlik bilgisi gönderilmez ({scheme}://)")
    if not cfg.key or not cfg.secret:
        reasons.append("GMS_CENTRA_AI_KEY / GMS_CENTRA_AI_SECRET tanımsız")
    return not reasons, reasons


def _ssl_context(cfg: GmsConfig) -> ssl.SSLContext:
    """TLS doğrulaması AÇIK kalır; kurumsal olmayan kök yalnızca güvenilenler listesine eklenir."""
    ctx = ssl.create_default_context()
    if cfg.ca_path:
        ctx.load_verify_locations(cafile=cfg.ca_path)
    return ctx


def hostname() -> str | None:
    name = (os.environ.get("COMPUTERNAME") or socket.gethostname() or "").strip()
    return name or None


# --- Durum (data/eval/gms_state.json tek doğruluk kaynağı) --------------------------------

_EMPTY_STATE: dict[str, Any] = {
    "runId": None,
    "roundNo": 1,
    "phase": "measure",
    "runStatus": "Idle",
    "startedAt": None,
    "finishedAt": None,
    "sequence": 0,
    "progressUpdatedAt": None,
    "counters": None,
    "activeLabel": None,
    "userFeedback": None,
    "stopReason": None,
    "baselineScore": None,
    "finalScore": None,
    "keptCount": 0,
    "revertedCount": 0,
    "sentRounds": {},
}


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_EMPTY_STATE)
    merged = dict(_EMPTY_STATE)
    merged.update({k: v for k, v in state.items() if k in _EMPTY_STATE})
    return merged


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)  # yarım yazılmış durum dosyası bırakmamak için


def new_run_id() -> str:
    return str(uuid.uuid4())


def next_sequence(state: dict) -> int:
    """Oturum başına monoton artan. Süreç yeniden başlasa da geri gitmez (diske yazılır)."""
    state["sequence"] = int(state.get("sequence") or 0) + 1
    return state["sequence"]


def raise_sequence_floor(state: dict, floor: int | None) -> None:
    """GMS daha yüksek bir sequence biliyorsa yerel tabanı yükselt; ASLA düşürme."""
    if isinstance(floor, int):
        state["sequence"] = max(int(state.get("sequence") or 0), floor)


def note_counters(state: dict, counters: dict | None) -> None:
    """Sayaçlar DEĞİŞTİYSE progressUpdatedAt'i o ana alır.

    progressUpdatedAt gönderim anı yapılırsa donmuş bir ölçüm ekranda canlı görünür ve
    "ilerleme durdu" uyarısı hiç çıkmaz; bu yüzden yalnızca değişimde güncellenir.
    """
    if counters is None:
        return
    if state.get("counters") != counters:
        state["counters"] = counters
        state["progressUpdatedAt"] = utc_now()


# --- Gövde üretimi ------------------------------------------------------------------------


def build_telemetry(state: dict) -> dict:
    """Canlı telemetri gövdesi. Yalnızca sayısal/durumsal alanlar; soru/cevap metni YOK."""
    body: dict[str, Any] = {
        "runId": state.get("runId"),
        "roundNo": state.get("roundNo"),
        "sequence": state.get("sequence"),
        "phase": state.get("phase"),
        "runStatus": state.get("runStatus"),
        "startedAt": state.get("startedAt"),
        "finishedAt": state.get("finishedAt"),
        "progressUpdatedAt": state.get("progressUpdatedAt"),
        "lastError": state.get("lastError"),
        "runnerVersion": RUNNER_VERSION,
        "hostname": hostname(),
    }
    # counters gövdede YOKSA GMS saklanan sayaçları korur; "bu gövdede yok" ile
    # "sıfırlandı" farklı şeyler olduğu için bilinmiyorsa alan hiç konmaz.
    counters = state.get("counters")
    if counters is not None:
        body["counters"] = counters
    return body


def build_round(state: dict, metrics: dict, decision: str, change_note: str,
                started_at: str | None, finished_at: str | None) -> dict:
    """Tur özeti gövdesi. Metrikler scripts.eval_summary.summarize'dan gelir (tek kaynak)."""
    return {
        "roundNo": state.get("roundNo"),
        "label": metrics.get("label"),
        "changeNote": (change_note or "")[:CHANGE_NOTE_MAX],
        "decision": decision,
        "avgScore": metrics.get("avg_score"),
        "successPct": metrics.get("success_pct"),
        "hallucinations": metrics.get("hallucinations"),
        "badIntegrity": metrics.get("bad_integrity"),
        "fallbackCount": metrics.get("fallback_count"),
        "directPct": metrics.get("direct_pct"),
        "modeCounts": metrics.get("mode_counts"),
        "avgLatencySec": metrics.get("avg_latency_s"),
        "p90LatencySec": metrics.get("all_p90_s"),
        "ragAvgLatencySec": metrics.get("rag_avg_s"),
        "avgFirstTokenSec": metrics.get("avg_first_token_s"),
        "groupScores": metrics.get("group_scores"),
        "startedAt": started_at,
        "finishedAt": finished_at,
    }


def build_session(state: dict) -> dict:
    """Oturum özeti gövdesi; oturum açılır açılmaz gönderilebilir."""
    return {
        "startedAt": state.get("startedAt"),
        "finishedAt": state.get("finishedAt"),
        "userFeedback": (state.get("userFeedback") or "")[:USER_FEEDBACK_MAX] or None,
        "stopReason": state.get("stopReason"),
        "baselineScore": state.get("baselineScore"),
        "finalScore": state.get("finalScore"),
        "keptCount": state.get("keptCount"),
        "revertedCount": state.get("revertedCount"),
    }


# --- Doğrulama (GMS'e bilerek geçersiz gövde göndermemek için) ----------------------------


def _size_ok(body: dict, limit: int) -> str | None:
    size = len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
    return None if size <= limit else f"gövde {size} bayt, sınır {limit}"


def validate_telemetry(body: dict) -> list[str]:
    errors: list[str] = []
    if not body.get("runId"):
        errors.append("runId yok")
    if body.get("phase") not in PHASES:
        errors.append(f"phase geçersiz: {body.get('phase')!r} (izinli: {', '.join(PHASES)})")
    if body.get("runStatus") not in RUN_STATUSES:
        errors.append(f"runStatus geçersiz: {body.get('runStatus')!r}")
    round_no = body.get("roundNo")
    if not isinstance(round_no, int) or not 1 <= round_no <= MAX_ROUND_NO:
        errors.append(f"roundNo 1..{MAX_ROUND_NO} olmalı: {round_no!r}")
    seq = body.get("sequence")
    if not isinstance(seq, int) or seq < 1:
        errors.append(f"sequence pozitif tam sayı olmalı: {seq!r}")
    counters = body.get("counters")
    if counters is not None:
        target, answered = counters.get("target"), counters.get("answered")
        if isinstance(target, int) and isinstance(answered, int) and answered > target:
            errors.append(f"answered ({answered}) > target ({target})")
    if msg := _size_ok(body, TELEMETRY_MAX_BYTES):
        errors.append(msg)
    return errors


def validate_round(body: dict) -> list[str]:
    errors: list[str] = []
    decision = body.get("decision")
    if decision not in DECISIONS:
        errors.append(f"decision geçersiz: {decision!r} (izinli: {', '.join(DECISIONS)})")
    round_no = body.get("roundNo")
    if not isinstance(round_no, int) or not 1 <= round_no <= MAX_ROUND_NO:
        errors.append(f"roundNo 1..{MAX_ROUND_NO} olmalı: {round_no!r}")
    # baseline yalnızca başlangıç ölçümü içindir; GMS 1. turdan sonrasını reddeder.
    if decision == "baseline" and round_no != 1:
        errors.append(f"decision=baseline yalnızca 1. turda geçerli (roundNo={round_no})")
    if not body.get("label"):
        errors.append("label yok")
    # modeCounts toplamının target'ı aşmaması, target'ı bilen çağıran tarafta kontrol edilir
    # (scripts.gms_report.cmd_round_summary); burada tur dosyalarına erişim yok.
    if msg := _size_ok(body, ROUND_MAX_BYTES):
        errors.append(msg)
    return errors


def validate_session(body: dict) -> list[str]:
    errors: list[str] = []
    if not body.get("startedAt"):
        errors.append("startedAt yok")
    stop = body.get("stopReason")
    if stop is not None and stop not in STOP_REASONS:
        errors.append(f"stopReason geçersiz: {stop!r} (izinli: {', '.join(STOP_REASONS)})")
    if msg := _size_ok(body, SESSION_MAX_BYTES):
        errors.append(msg)
    return errors


# --- GMS yanıtına verilecek karar (saf fonksiyon: ağ yok, yan etki yok) -------------------


def backoff_delay(attempt: int) -> int:
    n = max(1, int(attempt or 1))
    return min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** (n - 1))


def decide_next_action(http_status: int | None, body: Any, network_error: str | None,
                       attempt: int = 1, local_sequence: int | None = None) -> dict:
    """action: ok | resync | conflict | halt-until-change | halt-auth | backoff | halt-unknown."""
    if network_error:
        return {"action": "backoff", "retry_same": True, "delay_s": backoff_delay(attempt),
                "give_up_after": BACKOFF_MAX_ATTEMPTS, "reason": f"ağ hatası: {network_error}"}
    if http_status in (401, 403):
        return {"action": "halt-auth", "retry_same": False, "delay_s": AUTH_COOLDOWN_S,
                "reason": f"kimlik doğrulama reddedildi ({http_status}); kimlik bilgisi kontrol edilmeli"}
    if http_status == 429:
        return {"action": "backoff", "retry_same": True, "delay_s": backoff_delay(attempt),
                "give_up_after": BACKOFF_MAX_ATTEMPTS, "reason": "oran sınırı (429)"}
    if http_status is not None and http_status >= 500:
        return {"action": "backoff", "retry_same": True, "delay_s": backoff_delay(attempt),
                "give_up_after": BACKOFF_MAX_ATTEMPTS, "reason": f"sunucu hatası ({http_status})"}
    if http_status == 409:
        # Tur özeti idempotans anahtarı runId+roundNo. Farklı gövdeyle tekrar: üzerine YAZILMAZ.
        return {"action": "conflict", "retry_same": False, "delay_s": 0,
                "reason": "409: bu tur GMS'te farklı değerlerle kayıtlı; üzerine yazılmadı",
                "stored": body if isinstance(body, dict) else None}
    if http_status == 400:
        return {"action": "halt-until-change", "retry_same": False, "delay_s": 0,
                "reason": f"400: gövde reddedildi, aynısı körlemesine tekrar gönderilmez ({_brief(body)})"}
    if http_status == 404:
        # Uç sunucuda yok. Yeniden deneme işe yaramaz (dağıtım yapılmadan düzelmez);
        # 20 sn'de bir boşa 404 üretmek yerine gönderim durur.
        return {"action": "halt-missing-route", "retry_same": False, "delay_s": 0,
                "reason": "404: uç bu sunucuda yok; GMS tarafı dağıtılana kadar gönderim durdu"}
    if http_status is not None and http_status >= 300:
        return {"action": "halt-unknown", "retry_same": False, "delay_s": backoff_delay(attempt),
                "reason": f"beklenmeyen durum kodu ({http_status})"}
    if not isinstance(body, dict):
        return {"action": "halt-unknown", "retry_same": False, "delay_s": backoff_delay(attempt),
                "reason": "yanıt gövdesi anlaşılamadı"}
    # Eski sequence: GMS 200 döner ama yazmaz. Yerel tabanı yükselt, aynı gövdeyi tekrar gönderme.
    if body.get("accepted") is False:
        stored = body.get("storedSequence")
        floor = max(int(local_sequence or 0), stored) if isinstance(stored, int) else None
        return {"action": "resync", "retry_same": False, "delay_s": 0, "sequence_floor": floor,
                "reason": f"eski sequence; yerel taban {floor if floor is not None else 'değiştirilmedi'}"}
    if body.get("created") is False:
        return {"action": "ok", "retry_same": False, "delay_s": 0,
                "reason": "aynı gövde daha önce kaydedilmiş (created:false)"}
    return {"action": "ok", "retry_same": False, "delay_s": 0, "reason": "kabul edildi"}


def _brief(body: Any) -> str:
    if isinstance(body, dict):
        for key in ("message", "detail", "error", "rejection"):
            if body.get(key):
                return str(body[key])[:160]
    if isinstance(body, str):
        return body[:160]
    return "mesaj yok"


# --- Gönderim -----------------------------------------------------------------------------


def send_json(cfg: GmsConfig, method: str, path: str, body: dict) -> dict:
    """Tek HTTPS isteği. İstisna FIRLATMAZ; ağ hatası da bir sonuçtur.

    Dönen: {"sent": bool, "status": int|None, "body": Any, "network_error": str|None}
    """
    allowed, reasons = assert_send_allowed(cfg)
    if not allowed:
        return {"sent": False, "status": None, "body": None,
                "network_error": None, "blocked": "; ".join(reasons)}

    url = cfg.base_url.rstrip("/") + path
    headers = {"Content-Type": "application/json", KEY_HEADER: cfg.key, SECRET_HEADER: cfg.secret}
    try:
        with httpx.Client(verify=_ssl_context(cfg), timeout=SEND_TIMEOUT_S) as client:
            r = client.request(method, url, json=body, headers=headers)
            raw = r.content[:MAX_RESPONSE_BYTES]
            try:
                parsed: Any = json.loads(raw.decode("utf-8", "replace")) if raw else None
            except ValueError:
                parsed = raw.decode("utf-8", "replace")
            return {"sent": True, "status": r.status_code, "body": parsed, "network_error": None}
    except Exception as exc:  # ağ/TLS hatası gönderimi durdurur, geliştirmeyi durdurmaz
        return {"sent": False, "status": None, "body": None,
                "network_error": f"{type(exc).__name__}: {exc}"[:300]}


# --- Log ----------------------------------------------------------------------------------


def log(event: str, detail: dict | None = None) -> None:
    """data/eval/gms.log'a tek satır. Giz ya da soru/cevap metni yazılmaz."""
    line = {"at": utc_now(), "event": event}
    if detail:
        line.update(detail)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass  # loglayamamak da geliştirmeyi durdurmaz
