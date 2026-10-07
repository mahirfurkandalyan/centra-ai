"""Vektörü olmayan SSS kayıtlarını arka planda indeksler."""
import logging
import threading

from . import ollama_client, store

log = logging.getLogger("centra.indexer")
_lock = threading.Lock()
_state = {"running": False, "error": None}
BATCH_SIZE = 16


def state() -> dict:
    return dict(_state)


def _run() -> None:
    try:
        while rows := store.pending_embeddings(BATCH_SIZE):
            ids = [r["id"] for r in rows]
            store.save_embeddings(ids, ollama_client.embed([r["question"] for r in rows]))
            log.info("%d kayıt indekslendi", len(ids))
        _state["error"] = None
    except Exception as exc:  # Ollama kapalıysa vb. — admin panelde gösterilir
        log.exception("İndeksleme hatası")
        _state["error"] = str(exc)
    finally:
        _state["running"] = False
        _lock.release()


def start() -> bool:
    """Çalışmıyorsa indekslemeyi başlatır; zaten çalışıyorsa False döner."""
    if not _lock.acquire(blocking=False):
        return False
    _state["running"] = True
    threading.Thread(target=_run, daemon=True).start()
    return True
