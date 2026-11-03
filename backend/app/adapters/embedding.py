"""Text embedders for the embedding candidate step of menu matching (`app.matching.embedding`), and its settings.

The step is off unless EMBEDDING_ENABLED=true. A provider turns the catalog texts into an index
(`TextIndex`) that scores menu line names against every text by cosine similarity. The P24
decision memo (ai/docs/p24_embedding_decision.md, "P40 서버 단계 어댑터 제안"; #78, I3-P24,
not merged yet) plans two providers behind this interface, so changing one for the other is a
setting (EMBEDDING_MODEL) plus its floor:

  tfidf  stage 1, now: character 1-3-gram TF-IDF fitted on the catalog texts, in plain Python.
         No model file and no extra package, so it fits the small API server.
  e5     stage 2, later: multilingual-e5-small int8 (ONNX) once the server has the memory.

`CharTfidfProvider` is the P24 harness's `CharTfidf` (ai/eval/p24_embedding_compare.py, also in
#78) with the same n-gram range, text folding and weighting, so the offline numbers and the 0.38
floor describe what the server runs. The numbers the server relies on are summarised in
docs/menu_ai_matching_flow.md 6 ("임베딩 후보 단계"). Tests use fakes.
"""

import math
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

# The similarity floor per model: candidates below it are dropped. Each model has its own scale
# (P24 dev values, #78: TF-IDF 0.38, e5-small int8 about 0.91), so the floor goes with the model.
DEFAULT_MIN_SIMILARITY = {"tfidf": 0.38}
SUPPORTED_MODELS = tuple(DEFAULT_MIN_SIMILARITY)


class TextIndex(Protocol):
    def similarities(self, queries: Sequence[str]) -> list[list[float]]:
        """Cosine similarity of each query to each indexed text, in index order. Raises on failure."""
        ...


class EmbeddingProvider(Protocol):
    # Recorded in candidate evidence ("model") so a stored candidate says what produced it.
    model_id: str

    def build_index(self, texts: Sequence[str]) -> TextIndex:
        """Embed the catalog texts (fitting on them first if the method needs it). Raises on failure."""
        ...


class CharTfidfProvider:
    """Character n-gram TF-IDF (n = 1..3 over the lowercased text without spaces), fitted on the
    indexed texts: sublinear tf, smooth idf, L2-normalized sparse vectors, cosine.

    The text is not passed through `app.core.normalize`, as in the P24 harness: normalizing both
    sides lowered the dev recall and moved the floor (shown candidates @5 0.951 -> 0.929 at 0.38).
    """

    model_id = "tfidf-char"

    def __init__(self, n_min: int = 1, n_max: int = 3) -> None:
        self.n_min, self.n_max = n_min, n_max

    def build_index(self, texts: Sequence[str]) -> "CharTfidfIndex":
        document_frequency: Counter[str] = Counter()
        for text in texts:
            document_frequency.update(set(self._grams(text)))
        n = len(texts)
        idf = {gram: math.log((1 + n) / (1 + count)) + 1 for gram, count in document_frequency.items()}
        return CharTfidfIndex(self, idf, texts)

    def _grams(self, text: str) -> Counter[str]:
        s = re.sub(r"\s+", "", text.lower())
        return Counter(s[i : i + n] for n in range(self.n_min, self.n_max + 1) for i in range(len(s) - n + 1))

    def _vector(self, text: str, idf: dict[str, float]) -> dict[str, float]:
        weights = {g: (1 + math.log(c)) * idf[g] for g, c in self._grams(text).items() if g in idf}
        norm = math.sqrt(sum(w * w for w in weights.values()))
        return {g: w / norm for g, w in weights.items()} if norm else {}


class CharTfidfIndex:
    """The fitted vocabulary and the texts' vectors as postings (gram -> [(text position, weight)])."""

    def __init__(self, provider: CharTfidfProvider, idf: dict[str, float], texts: Sequence[str]) -> None:
        self._provider = provider
        self._idf = idf
        self._size = len(texts)
        self._postings: dict[str, list[tuple[int, float]]] = {}
        for position, text in enumerate(texts):
            for gram, weight in provider._vector(text, idf).items():
                self._postings.setdefault(gram, []).append((position, weight))

    def similarities(self, queries: Sequence[str]) -> list[list[float]]:
        rows = []
        for query in queries:
            row = [0.0] * self._size
            for gram, weight in self._provider._vector(query, self._idf).items():
                for position, other in self._postings.get(gram, ()):
                    row[position] += weight * other
            rows.append(row)
        return rows


@dataclass(frozen=True)
class EmbeddingSettings:
    enabled: bool = False
    model: str = "tfidf"
    min_similarity: float = DEFAULT_MIN_SIMILARITY["tfidf"]


def load_embedding_settings() -> EmbeddingSettings:
    """Read the EMBEDDING_* variables; raise RuntimeError for an unknown model or an invalid floor.

    Checked at start-up even while the step is off, like MATCHING_LLM_MAX_CALLS, so a typo is found
    before someone turns it on.
    """
    enabled = (os.getenv("EMBEDDING_ENABLED") or "false").lower()
    if enabled not in ("true", "false"):
        raise RuntimeError(f"EMBEDDING_ENABLED must be true or false, got {enabled!r}")
    model = os.getenv("EMBEDDING_MODEL") or "tfidf"
    if model not in SUPPORTED_MODELS:
        raise RuntimeError(f"Unsupported EMBEDDING_MODEL: {model!r} (supported: {', '.join(SUPPORTED_MODELS)})")
    raw = os.getenv("EMBEDDING_MIN_SIMILARITY")
    min_similarity = DEFAULT_MIN_SIMILARITY[model]
    if raw:
        try:
            min_similarity = float(raw)
        except ValueError:
            min_similarity = math.nan
        if not 0 <= min_similarity <= 1:  # also rejects nan
            raise RuntimeError(f"EMBEDDING_MIN_SIMILARITY must be a number from 0 to 1, got {raw!r}")
    return EmbeddingSettings(enabled=enabled == "true", model=model, min_similarity=min_similarity)


def make_embedding_provider(settings: EmbeddingSettings) -> EmbeddingProvider:
    """The provider for a model that `load_embedding_settings` accepted."""
    if settings.model == "tfidf":
        return CharTfidfProvider()
    raise RuntimeError(f"Unsupported EMBEDDING_MODEL: {settings.model!r}")
