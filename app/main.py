import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, indexer, ollama_client, rag, store
from .parser import parse_faq_markdown

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    indexer.start()  # önceki çalışmadan kalan indekslenmemiş kayıtlar
    yield


app = FastAPI(title="Centra AI Chatbot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


def require_admin(x_admin_token: str = Header(default="")) -> None:
    if config.ADMIN_TOKEN and x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Geçersiz admin anahtarı")


# --- Sayfalar ---

@app.get("/", include_in_schema=False)
def chat_page():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(config.STATIC_DIR / "admin.html")


# --- Sohbet ---

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@app.post("/api/chat")
def chat(req: ChatRequest):
    def events():
        try:
            for event in rag.answer_stream(req.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logging.exception("Sohbet hatası")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/health")
def health():
    return {**ollama_client.health(), "indexer": indexer.state()}


# --- Admin ---

@app.post("/api/admin/upload", dependencies=[Depends(require_admin)])
async def upload_faq(file: UploadFile):
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Dosya UTF-8 formatında olmalı")

    entries, errors = parse_faq_markdown(text)
    if not entries:
        raise HTTPException(status_code=400, detail={"message": "Dosyada geçerli SSS bulunamadı", "errors": errors})

    result = store.upsert_faqs(entries, file.filename or "upload.md")
    indexer.start()
    return {"parsed": len(entries), **result, "errors": errors}


@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    return {**store.stats(), "indexer": indexer.state(), "health": ollama_client.health()}


@app.get("/api/admin/faqs", dependencies=[Depends(require_admin)])
def admin_faqs(q: str = "", module: str = "", limit: int = 50, offset: int = 0):
    return store.list_faqs(q, module, min(limit, 500), offset)


@app.delete("/api/admin/faqs/{faq_id}", dependencies=[Depends(require_admin)])
def admin_delete_faq(faq_id: int):
    if not store.delete_faq(faq_id):
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return {"ok": True}


@app.get("/api/admin/logs", dependencies=[Depends(require_admin)])
def admin_logs(limit: int = 50):
    return store.recent_logs(min(limit, 500))
