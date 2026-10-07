import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("CENTRA_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "centra.db"
STATIC_DIR = BASE_DIR / "static"

# Ollama
# "localhost" Windows'ta önce IPv6'yı deniyor ve her istekte ~2 sn kaybettiriyor
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3:4b-instruct")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
# Modeller bellekte açık kalsın. Ollama sayıyı saniye, metni süre ("10m") olarak okur;
# "-1" gibi birimsiz bir metni 400 hatasıyla reddeder, bu yüzden sayıya çevrilir.
_keep_alive = os.getenv("KEEP_ALIVE", "-1")
KEEP_ALIVE: int | str = int(_keep_alive) if _keep_alive.lstrip("-").isdigit() else _keep_alive
NUM_CTX = int(os.getenv("NUM_CTX", "4096"))
# Sohbet modelinin GPU'ya alınacak katman sayısı. 0 = yalnızca CPU.
# Küçük GPU'larda (ör. MX150, 2 GB) iki model aynı belleğe sığmayıp sürekli birbirini
# bellekten atıyor; arama modeli GPU'da, sohbet modeli CPU'da kalınca bu bekleme bitiyor.
# Boş bırakılırsa karar Ollama'ya kalır (güçlü GPU'lu sunucuda boş bırakın).
_chat_num_gpu = os.getenv("CHAT_NUM_GPU", "0")
CHAT_NUM_GPU: int | None = int(_chat_num_gpu) if _chat_num_gpu.strip() else None

# Arama eşikleri (cosine benzerliği, 0-1)
DIRECT_THRESHOLD = float(os.getenv("DIRECT_THRESHOLD", "0.82"))  # üstü: SSS cevabı aynen döner
RAG_THRESHOLD = float(os.getenv("RAG_THRESHOLD", "0.60"))  # üstü: LLM, SSS'lerle cevap üretir
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "2"))
CONTEXT_CHARS = int(os.getenv("CONTEXT_CHARS", "800"))  # LLM'e verilen her kaynağın azami uzunluğu

# Boşsa admin uçları korumasız (sadece yerel MVP için)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

CONTACT_TEXT = os.getenv(
    "CONTACT_TEXT", "0262 643 44 33 numaralı telefondan veya info@centra.com.tr adresinden"
)
