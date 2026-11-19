"""Fresh Sastrawi preprocessing for the Indo corpus (phase 2).

Implements the SAME rules as research v1 (`src/preprocessing/run.py` +
`src/preprocessing/build_locked.py`, see `data/DATASET_LOCK.md` stem section)
without importing anything from the frozen `src/preprocessing` package:

  1. clean : lowercase, remove URLs / mentions / hashtags, remove digits,
             remove punctuation, collapse whitespace (alay dict OFF per
             phase-2 decision — no alay normalization for this corpus).
  2. stem  : per UNIQUE word only, cache hits free; pure-alpha words <=50
             chars are stemmed with Sastrawi under a 0.3 s per-word alarm;
             timeout returns the word unchanged (v1 pathological-token rule);
             non-alpha tokens pass through untouched.
  3. mask  : Sastrawi stopword remover + custom `configs/stopwords_id.txt`,
             then token filter 2..50 chars (v1 values).
"""
import re
import signal
from pathlib import Path

from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory

REPO = Path(__file__).resolve().parents[2]
STOPWORDS_PATH = REPO / "configs/stopwords_id.txt"
STEM_TIMEOUT = 0.3  # seconds per word, identical to v1
MIN_TOKEN_LEN = 2
MAX_TOKEN_LEN = 50

_ALPHA = re.compile(r"^[a-z]+$")


def is_stemmable(word: str) -> bool:
    """v1 predicate: pure lowercase-ASCII alpha, within token-length bounds."""
    return bool(_ALPHA.match(word)) and len(word) <= MAX_TOKEN_LEN


_URL = re.compile(r"http\S+|www\S+|https\S+")
_MENTION = re.compile(r"@\w+|#\w+")
_DIGIT = re.compile(r"\d+")
_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")


class _StemTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _StemTimeout()


def clean_text(text: str) -> str:
    """v1 clean_text without alay normalization (phase-2 decision)."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = _URL.sub("", text)
    text = _MENTION.sub("", text)
    text = _DIGIT.sub("", text)
    text = _PUNCT.sub(" ", text)
    return _SPACE.sub(" ", text).strip()


def load_stopwords(path: Path = STOPWORDS_PATH) -> set:
    with open(path, "r", encoding="utf-8") as f:
        return {ln.strip() for ln in f if ln.strip()}


class IndoPreprocessor:
    """Cache-backed unique-word stemmer + v1 mask rules."""

    def __init__(self, stopwords_path: Path = STOPWORDS_PATH):
        self.stemmer = StemmerFactory().create_stemmer()
        self.stopword_remover = StopWordRemoverFactory().create_stop_word_remover()
        self.custom_stopwords = load_stopwords(stopwords_path)
        self._cache: dict[str, str] = {}
        signal.signal(signal.SIGALRM, _alarm_handler)

    def _stem_word(self, word: str) -> str:
        cached = self._cache.get(word)
        if cached is not None:
            return cached
        # The 0.3 s one-shot alarm can fire exactly while the timer is being
        # disarmed; that raise would otherwise escape this function (and kill
        # a pool worker), so the disarm itself is guarded.
        try:
            signal.setitimer(signal.ITIMER_REAL, STEM_TIMEOUT)
            out = self.stemmer.stem(word)
        except _StemTimeout:
            out = word  # pathological token: leave as-is (v1 rule)
        finally:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
            except _StemTimeout:
                pass
        self._cache[word] = out
        return out

    def _stem_doc(self, cleaned: str) -> str:
        words = cleaned.split()
        to_stem = [w for w in words if is_stemmable(w)]
        stem_map = {w: self._stem_word(w) for w in to_stem}
        return " ".join(stem_map.get(w, w) for w in words)

    def use_cache(self, stem_map: dict[str, str]) -> None:
        """Inject pre-computed stems (build phase B -> C hand-off)."""
        self._cache = dict(stem_map)

    def assemble(self, cleaned: str) -> str:
        """Join a cleaned doc with cached stems (no stemming by construction)."""
        return " ".join(self._cache.get(w, w) for w in cleaned.split())

    def mask_stemmed(self, stemmed: str) -> str:
        """Stopword removal + length filter only (v1 values)."""
        masked = self.stopword_remover.remove(stemmed)
        return " ".join(
            t for t in masked.split()
            if t not in self.custom_stopwords
            and MIN_TOKEN_LEN <= len(t) <= MAX_TOKEN_LEN)

    def process(self, text: str) -> str:
        cleaned = clean_text(text)
        if not cleaned:
            return ""
        return self.mask_stemmed(self._stem_doc(cleaned))

    def stem_many(self, words: list[str]) -> dict[str, str]:
        """Warm the cache for a sorted unique vocabulary (build-time use)."""
        for w in words:
            if is_stemmable(w):
                self._stem_word(w)
        return dict(self._cache)
