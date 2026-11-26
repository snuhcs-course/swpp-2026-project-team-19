"""I5-P43: menu imports that are processed at the same time do not hold each other up.

An import's photos are read one after another (menu_import_processing._extract_all), and each
import is a sync background task, which Starlette runs in its thread pool, so several imports
call the one shared extractor from several threads at once. These tests do that with fakes; no
test calls a real API."""

import inspect
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.adapters.openrouter_extraction import OpenRouterMenuExtractor
from app.extraction import gemini, hybrid, openrouter
from app.extraction.routed import CircuitBreaker
from app.services import menu_import_processing
from tests.test_hybrid_extraction_adapter import CLOVA, OCR_RESPONSE, jpeg
from tests.test_openrouter_extraction import ROUTE, FakeGemini, failed, ok

IMPORTS = 3


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(openrouter, "sleep", lambda seconds: None)
    monkeypatch.setattr(gemini, "sleep", lambda seconds: None)
    monkeypatch.setattr(hybrid, "call_ocr", lambda settings, image, mime_type, client=None: {
        "response": OCR_RESPONSE, "sentSize": [1000, 2000], "latencyMs": 900, "attempts": 1})
    answers = FakeGemini(gemini_3_8_flash=ok().json()["choices"][0]["message"]["content"],
                         gemini_3_5_flash_lite=ok().json()["choices"][0]["message"]["content"])
    monkeypatch.setattr(gemini, "make_client", lambda settings: answers)


def extractor_with(monkeypatch, post, breaker=None):
    monkeypatch.setattr(openrouter.httpx, "post", post)
    return OpenRouterMenuExtractor(ROUTE, CLOVA, breaker)


def read_at_once(extractor, photos=IMPORTS):
    with ThreadPoolExecutor(max_workers=photos) as pool:
        futures = [pool.submit(extractor.extract, jpeg(), "image/jpeg", f"menu-{n}.jpg") for n in range(photos)]
        return [future.result(timeout=10) for future in futures]


def test_an_import_is_a_sync_task_and_reads_its_photos_in_order():
    # Starlette runs a sync background task in its thread pool, so imports do not wait for each other;
    # inside one import the photos are a plain loop.
    assert not inspect.iscoroutinefunction(menu_import_processing.process_menu_import)
    source = inspect.getsource(menu_import_processing._extract_all)
    assert "for image in menu_import.images:" in source and "extractor.extract(" in source


def test_three_imports_have_their_model_calls_in_flight_at_the_same_time(monkeypatch):
    # Every call waits until all three are inside `post`. If the extractor let only one call run at a
    # time, the barrier would never fill and the test would fail on its timeout.
    together = threading.Barrier(IMPORTS, timeout=5)

    def post(url, **kwargs):
        together.wait()
        return ok()

    results = read_at_once(extractor_with(monkeypatch, post))

    assert [result.raw_output["route"]["stage"] for result in results] == [0, 0, 0]
    assert not together.broken


def test_a_slow_photo_of_one_import_does_not_delay_another_import(monkeypatch):
    release, slow_started = threading.Event(), threading.Event()

    def post(url, **kwargs):
        # The first call is the slow one. (The call runs in the extractor's own worker thread, so
        # the calling thread cannot be told from here.)
        if not slow_started.is_set():
            slow_started.set()
            assert release.wait(5)
        return ok()

    extractor = extractor_with(monkeypatch, post)
    slow = threading.Thread(target=extractor.extract, args=(jpeg(), "image/jpeg", None))
    slow.start()
    try:
        assert slow_started.wait(5)
        quick = extractor.extract(jpeg(), "image/jpeg", None)  # answers while the slow call is still open
        assert quick.raw_output["route"]["stage"] == 0 and slow.is_alive()
    finally:
        release.set()
        slow.join(5)
    assert not slow.is_alive()


def test_imports_failing_together_open_the_breaker_once_and_all_fall_back(monkeypatch):
    together, posts = threading.Barrier(IMPORTS, timeout=5), []

    def post(url, **kwargs):
        posts.append(url)
        if len(posts) <= IMPORTS:
            together.wait()
        return failed(402)

    breaker = CircuitBreaker(3, 600)
    extractor = extractor_with(monkeypatch, post, breaker)

    results = read_at_once(extractor)

    assert [result.raw_output["route"]["stage"] for result in results] == [2, 2, 2]
    assert len(posts) == IMPORTS and not breaker.allows()
    after = extractor.extract(jpeg(), "image/jpeg", None)
    assert after.raw_output["route"]["skipped"] == [{"stage": 0, "reason": "circuit_open"}] and len(posts) == IMPORTS
