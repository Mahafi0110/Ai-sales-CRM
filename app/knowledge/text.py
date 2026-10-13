"""Plain-text helpers: split a document into passages, and turn words into comparable search terms."""
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings

STOPWORDS = frozenset("""a about above after again all also am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have having he her here
hers him his how i if in into is it its just me more most my no nor not now of off on once only or other our out over
own same she should so some such than that the their them then there these they this those through to too under until
up very was we were what when where which while who whom why will with would you your yours""".split())

_WORD = re.compile(r"\w+", re.UNICODE)


def stem(word: str) -> str:
    """A deliberately simple English suffix trimmer so 'pricing', 'prices' and 'price' look alike.
    It is applied to both the question and the documents, so small mistakes cancel out."""
    for suffix in ("ing", "edly", "ed", "ly", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    words = _WORD.findall(text.lower())
    return [stem(w) for w in words if w not in STOPWORDS and (len(w) > 1 or w.isdigit())]


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_text(text: str) -> list[str]:
    settings = get_settings()
    size = max(settings.knowledge_chunk_size, 50)
    overlap = max(0, min(settings.knowledge_chunk_overlap, size // 2))  # a bad setting must not break uploads
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap,
                                              separators=["\n\n", "\n", ". ", " ", ""])
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]
