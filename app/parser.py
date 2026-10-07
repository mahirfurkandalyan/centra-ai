"""SSS .md dosyasını (## Soru / **Modül:** / ### Cevap) kayıtlara ayırır.

Eski gap dosyalarında (ör. Pack 14) "### Chatbot Cevabı (sorunlu kısım)" ve "### Sorun" gibi ek
bölümler de bulunuyor; bunlar bilgi tabanına girmemeli, yalnızca "### Cevap" bölümü alınır.
"""
import re
from dataclasses import dataclass

_SORU = re.compile(r"^##\s+Soru\s*$", re.M)
_ALT_BASLIK = re.compile(r"^###\s+(.+?)\s*$", re.M)
_MODUL = re.compile(r"^\*\*Modül:\*\*\s*(.+?)\s*$", re.M)
_TRAILING_RULE = re.compile(r"\n\s*-{3,}\s*$")


@dataclass
class FaqEntry:
    question: str
    module: str
    answer: str


def _sections(block: str) -> tuple[str, dict[str, str]]:
    """Bloğu (### öncesi metin, {alt başlık: içerik}) olarak böler."""
    heads = list(_ALT_BASLIK.finditer(block))
    intro = block[: heads[0].start()] if heads else block
    sections = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(block)
        sections[h.group(1).casefold()] = block[h.end():end]
    return intro, sections


def parse_faq_markdown(text: str) -> tuple[list[FaqEntry], list[str]]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    entries: list[FaqEntry] = []
    errors: list[str] = []

    for i, block in enumerate(_SORU.split(text)[1:], 1):
        intro, sections = _sections(block)
        if "cevap" not in sections:
            errors.append(f"Blok {i}: '### Cevap' başlığı bulunamadı")
            continue

        # Modül satırı genelde sorunun altında, ama farklı bir bölüme de düşmüş olabilir
        m_modul = _MODUL.search(intro) or _MODUL.search(block)
        module = m_modul.group(1).strip() if m_modul else "Genel"
        question = " ".join(_MODUL.sub("", intro).split())
        answer = _TRAILING_RULE.sub("", _MODUL.sub("", sections["cevap"])).strip()

        if not question or not answer:
            errors.append(f"Blok {i}: soru veya cevap boş")
            continue
        entries.append(FaqEntry(question, module, answer))

    return entries, errors
