"""Limits on extracting a whole PDF (I4-P37): page failures, model timeouts and retries.

    outcome = extract_pdf_pages(PdfMenuExtractor(), pages)      # pages from PdfMenuExtractor.pages
    for page in outcome.pages:
        page.result      # ExtractionResult, or None when the page failed
        page.failure     # None, or one of FAILURES
    outcome.stopped      # None, or why the pages after some point were not tried

A photo is one model call. A PDF is up to 15 of them in a row, and the limits of one call
(6 attempts of up to 330 s each) would let one stuck file hold the background job for hours.
`extract_pdf_pages` runs the pages in order under PdfGuards:

- one attempt of the model call ends after `attempt_timeout_s`, and a page gets at most
  `page_attempts` attempts;
- all pages together get at most `document_retries` retries; once they are used every later
  page gets one attempt;
- the CLOVA call of a scanned page ends after `ocr_deadline_s`, retries included (the page then
  goes to the model without OCR lines, as a photo does);
- no page starts after the PDF's deadline, `page_budget_s` for every page of the file and never
  less than one page's own worst case (`deadline_s`), and a page that starts with less than
  one attempt's time left gets one attempt, cut at the deadline;
- after `failed_pages` failed pages no further page is tried.

So the model is called at most `pages + document_retries` times, and the run ends within
the deadline plus one page's own worst case (`page_seconds`).

A failed page never raises: it is an outcome with a `failure` code, the message and the
`raw_output` of the failure. What a failed page means for the import (fail it, or keep the
other pages) is decided by the caller; this module only reports. Pages not tried have the
failure "not_attempted" and `outcome.stopped` says why.
"""

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal

import httpx

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.adapters.pdf_extraction import PdfMenuExtractor
from app.extraction.gemini import HardTimeout
from app.extraction.pdf import PdfPage

Failure = Literal["model_timeout", "model_call_failed", "invalid_output", "page_failed", "not_attempted"]
FAILURES: tuple[Failure, ...] = ("model_timeout", "model_call_failed", "invalid_output", "page_failed", "not_attempted")
Stopped = Literal["document_deadline", "too_many_failed_pages"]

# The waits call_with_retries makes between attempts: 5 s, 10 s, 20 s, ... capped at 60 s.
_RETRY_WAITS_S = (5, 10, 20, 40, 60)


@dataclass(frozen=True)
class PdfGuards:
    """The defaults come from the photo runs of I4 (15 photos x 3 runs per prompt): one call took
    18 to 22 s at the median and 58 to 83 s at the 95th percentile. An attempt that is not back
    after 120 s is taken for stuck. 90 s a page lets every page of a PDF be as slow as the 95th
    percentile (15 pages: 1,245 s of 1,350 s); a fixed limit would cut the last pages of a long
    PDF on a slow day."""

    page_attempts: int = 3
    attempt_timeout_s: float = 120
    ocr_deadline_s: float = 60
    document_retries: int = 6
    page_budget_s: float = 90
    failed_pages: int = 3
    # A fixed deadline for the whole PDF in place of the one worked out from its pages.
    document_deadline_s: float | None = None

    def __post_init__(self) -> None:
        for name in ("page_attempts", "failed_pages"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.document_retries < 0:
            raise ValueError("document_retries must not be negative")
        for name in ("attempt_timeout_s", "ocr_deadline_s", "page_budget_s", "document_deadline_s"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")

    @property
    def page_seconds(self) -> float:
        """The longest one page can take: its OCR call, every attempt timing out, and the waits
        between the attempts."""
        waits = sum(_RETRY_WAITS_S[min(i, len(_RETRY_WAITS_S) - 1)] for i in range(self.page_attempts - 1))
        return self.ocr_deadline_s + self.page_attempts * self.attempt_timeout_s + waits

    def deadline_s(self, pages: int) -> float:
        """After this long no further page of a PDF of `pages` pages is started: `page_budget_s`
        a page, and at least one page's worst case, so a short PDF keeps its retries."""
        if self.document_deadline_s is not None:
            return self.document_deadline_s
        return max(pages * self.page_budget_s, self.page_seconds)


@dataclass(frozen=True)
class PageOutcome:
    page: int
    result: ExtractionResult | None = None
    failure: Failure | None = None
    message: str | None = None
    # Model attempts this page used (0 for a page that was not tried or failed before the call).
    attempts: int = 0
    raw_output: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None


@dataclass(frozen=True)
class PdfExtraction:
    pages: tuple[PageOutcome, ...]
    stopped: Stopped | None = None

    @property
    def ok(self) -> bool:
        """Every page was extracted."""
        return all(page.ok for page in self.pages)

    @property
    def model_attempts(self) -> int:
        return sum(page.attempts for page in self.pages)


def _causes(error: BaseException) -> Iterable[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__


def classify(error: ExtractionError) -> Failure:
    """The failure code of a page from the error chain, not from its message."""
    chain = list(_causes(error))
    if any(isinstance(cause, extraction.InvalidModelOutputError) for cause in chain):
        return "invalid_output"
    if any(isinstance(cause, extraction.ModelCallError) for cause in chain):
        timed_out = any(isinstance(cause, (HardTimeout, httpx.TimeoutException)) for cause in chain)
        return "model_timeout" if timed_out else "model_call_failed"
    return "page_failed"


def _attempts(raw_output: dict[str, Any] | None) -> int:
    value = (raw_output or {}).get("attempts")
    return value if isinstance(value, int) and value > 0 else 0


def _for_page(extractor: PdfMenuExtractor, guards: PdfGuards, attempts: int, timeout_s: float) -> PdfMenuExtractor:
    """The extractor with this page's limits. Nothing is read from the environment or opened here."""
    hybrid = extractor.hybrid
    settings = replace(hybrid.settings, max_attempts=attempts, request_timeout_s=timeout_s, wall_timeout_s=timeout_s)
    clova = replace(hybrid.clova, deadline_s=guards.ocr_deadline_s)
    return PdfMenuExtractor(HybridMenuExtractor(settings, clova, prompt=hybrid.prompt))


def extract_pdf_pages(
    extractor: PdfMenuExtractor,
    pages: Iterable[PdfPage],
    guards: PdfGuards | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> PdfExtraction:
    """Extract the pages in order under `guards`. Never raises for a page that fails."""
    guards = guards or PdfGuards()
    pages = list(pages)
    deadline = guards.deadline_s(len(pages))
    started = clock()
    retries_left = guards.document_retries
    failed = 0
    outcomes: list[PageOutcome] = []
    stopped: Stopped | None = None
    for page in pages:
        remaining = deadline - (clock() - started)
        if stopped is None and failed >= guards.failed_pages:
            stopped = "too_many_failed_pages"
        if stopped is None and remaining <= 0:
            stopped = "document_deadline"
        if stopped is not None:
            reason = ("the PDF's time limit was reached" if stopped == "document_deadline"
                      else f"{failed} pages of the PDF had failed")
            outcomes.append(PageOutcome(page.number, failure="not_attempted", message=f"not tried: {reason}"))
            continue

        short = remaining < guards.attempt_timeout_s
        allowed = 1 if short else min(guards.page_attempts, 1 + retries_left)
        limited = _for_page(extractor, guards, allowed, min(guards.attempt_timeout_s, remaining))
        try:
            result = limited.extract_page(page)
        except ExtractionError as error:
            used = _attempts(error.raw_output)
            outcomes.append(PageOutcome(page.number, failure=classify(error), message=str(error), attempts=used,
                                        raw_output=error.raw_output))
            failed += 1
        else:
            used = _attempts(result.raw_output)
            outcomes.append(PageOutcome(page.number, result=result, attempts=used, raw_output=result.raw_output))
        retries_left -= max(0, min(used, allowed) - 1)
    return PdfExtraction(tuple(outcomes), stopped)
