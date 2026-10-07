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
KEEP_ALIVE = os.getenv("KEEP_ALIVE", "-1")  # modeller bellekte açık kalsın
NUM_CTX = int(os.getenv("NUM_CTX", "4096"))

# Arama eşikleri (cosine benzerliği, 0-1)
DIRECT_THRESHOLD = float(os.getenv("DIRECT_THRESHOLD", "0.82"))  # üstü: SSS cevabı aynen döner
RAG_THRESHOLD = float(os.getenv("RAG_THRESHOLD", "0.60"))  # üstü: LLM, SSS'lerle cevap üretir
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "2"))

# Boşsa admin uçları korumasız (sadece yerel MVP için)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

CONTACT_TEXT = os.getenv(
    "CONTACT_TEXT", "0262 643 44 33 numaralı telefondan veya info@centra.com.tr adresinden"
)
