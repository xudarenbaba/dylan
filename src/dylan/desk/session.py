"""One worker owns the brain. The window thread only queues text."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from pathlib import Path

from dylan.cli.main import LETTER_CHANGED
from dylan.clock import Clock
from dylan.config import Settings
from dylan.dialogue.loop import Conversation, be_born, sleep_pending
from dylan.errors import DylanError, StoreCorrupt
from dylan.memory.constants import PRIVACY_NOTICE
from dylan.memory.life import letter_changed
from dylan.memory.store import MemoryStore
from dylan.memory.text import mask_secrets

SETTLING = "在整理这次相处"
_FAILED = "这次没有完成"


class DeskClosed(Exception):
    """Raised while a reply is still streaming, so this turn is not stored."""


class ReplyWriter:
    """What Conversation prints. Closing the window aborts the turn before it is stored."""

    def __init__(self, events: queue.Queue[dict[str, str]], stop: threading.Event) -> None:
        self._events = events
        self._stop = stop

    def write(self, text: str) -> int:
        if self._stop.is_set():
            raise DeskClosed()
        if text:
            self._events.put({"kind": "chunk", "text": text})
        return len(text)

    def flush(self) -> None:
        if self._stop.is_set():
            raise DeskClosed()


class NoticeStream:
    """Terminal keeps every warning. The window skips mind dumps, which start with 〔."""

    def __init__(self, real: object, events: queue.Queue[dict[str, str]]) -> None:
        self._real = real
        self._events = events

    def write(self, text: str) -> int:
        self._real.write(text)  # type: ignore[attr-defined]
        self.flush()
        visible = text.lstrip()
        if visible and not visible.startswith("〔"):
            self._events.put({"kind": "notice", "text": visible.strip()})
        return len(text)

    def flush(self) -> None:
        flush = getattr(self._real, "flush", None)
        if callable(flush):
            flush()


def _public(exc: DylanError, api_key: str) -> str:
    detail = exc.detail.strip()
    if not detail:
        return exc.category
    _shown, hidden = mask_secrets(detail, api_key)
    if hidden:
        return exc.category
    return f"{exc.category}：{detail}"


def _tell(events: queue.Queue[dict[str, str]], stderr: object, text: str) -> None:
    stderr.write(text + "\n")  # type: ignore[attr-defined]
    flush = getattr(stderr, "flush", None)
    if callable(flush):
        flush()
    events.put({"kind": "notice", "text": text})


def _open_store(
    path: Path,
    clock: Clock,
    letter: str,
    model: object,
    settings: Settings,
    stderr: object,
) -> MemoryStore:
    if not path.exists():
        store = MemoryStore.create(path, clock)
        try:
            be_born(store, letter, model, settings)
        except DylanError:
            store.discard()
            raise
        return store
    store = MemoryStore.open(path, clock)
    try:
        if not store.born():
            raise StoreCorrupt("这块大脑没有完成出生，请把它改名备份后重新启动")
        if letter_changed(store, letter):
            stderr.write(LETTER_CHANGED + "\n")  # type: ignore[attr-defined]
        sleep_pending(store, model, settings, stderr)
    except Exception:
        store.close()
        raise
    return store


class DeskSession:
    """Queues sentences onto the worker that holds the database connection."""

    def __init__(
        self,
        *,
        path: Path,
        clock: Clock,
        letter: str,
        model: object,
        settings: Settings,
        stderr: object,
    ) -> None:
        self._inbox: queue.Queue[str | None] = queue.Queue()
        self._events: queue.Queue[dict[str, str]] = queue.Queue()
        self._stop = threading.Event()
        self._done = threading.Event()
        self._gate = threading.Lock()
        self._on_settled: Callable[[], None] | None = None
        self._fired = False
        self._thread = threading.Thread(
            target=self._run,
            args=(path, clock, letter, model, settings, stderr),
            name="dylan-desk",
            daemon=False,
        )
        self._thread.start()

    def send(self, text: str) -> None:
        if self._stop.is_set():
            return
        stripped = text.strip()
        if not stripped:
            return
        self._inbox.put(stripped)

    def poll(self) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        while True:
            try:
                found.append(self._events.get_nowait())
            except queue.Empty:
                return found

    def request_stop(self) -> None:
        self._stop.set()
        self._inbox.put(None)

    def set_on_settled(self, callback: Callable[[], None]) -> None:
        with self._gate:
            self._on_settled = callback
        self._fire()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def alive(self) -> bool:
        return self._thread.is_alive()

    def _fire(self) -> None:
        with self._gate:
            if self._fired or not self._done.is_set() or self._on_settled is None:
                return
            self._fired = True
            callback = self._on_settled
        try:
            callback()
        except Exception:
            return

    def _converse(self, conversation: Conversation, notices: NoticeStream) -> None:
        writer = ReplyWriter(self._events, self._stop)
        while not self._stop.is_set():
            item = self._inbox.get()
            if item is None or self._stop.is_set():
                return
            try:
                conversation.turn(item, writer, notices)
            except DeskClosed:
                return
            except Exception:
                notices.write(_FAILED + "\n")
                return
            self._events.put({"kind": "end"})

    def _run(
        self,
        path: Path,
        clock: Clock,
        letter: str,
        model: object,
        settings: Settings,
        stderr: object,
    ) -> None:
        store: MemoryStore | None = None
        conversation: Conversation | None = None
        notices = NoticeStream(stderr, self._events)
        try:
            store = _open_store(path, clock, letter, model, settings, notices)
            conversation = Conversation(store, settings, model, clock)
            if not store.privacy_shown():
                self._events.put({"kind": "privacy", "text": PRIVACY_NOTICE})
                store.mark_privacy_shown()
            self._converse(conversation, notices)
        except DylanError as exc:
            _tell(self._events, stderr, _public(exc, settings.deepseek_api_key))
        except Exception:
            _tell(self._events, stderr, _FAILED)
        finally:
            try:
                if conversation is not None:
                    self._events.put({"kind": "status", "text": SETTLING})
                    try:
                        conversation.finish(notices)
                    except DylanError as exc:
                        _tell(self._events, stderr, _public(exc, settings.deepseek_api_key))
                    except Exception:
                        _tell(self._events, stderr, _FAILED)
            finally:
                if store is not None:
                    store.close()
                self._events.put({"kind": "closed"})
                self._done.set()
                self._fire()
