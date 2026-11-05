"""macOS WebKit window. It never touches the brain; the worker does."""

from __future__ import annotations

import threading
from pathlib import Path

from dylan.clock import Clock
from dylan.config import Settings
from dylan.desk.session import DeskSession

_PAGE = Path(__file__).with_name("page.html").read_text(encoding="utf-8")
_WIDTH = 360
_HEIGHT = 560
_MARGIN_X = 24
_MARGIN_Y = 72


class _Api:
    """Exposed to the page. Methods only move text between queues."""

    def __init__(self, session: DeskSession) -> None:
        self._session = session

    def send(self, text: object = "") -> None:
        self._session.send("" if text is None else str(text))

    def poll(self) -> list[dict[str, str]]:
        return self._session.poll()


class _Host:
    """Keep the window up while she settles, then let it close."""

    def __init__(self, session: DeskSession) -> None:
        self._session = session
        self._window: object | None = None
        self._leave = False
        self._ready = False
        self._lock = threading.Lock()

    def bind(self, window: object) -> None:
        self._window = window

    def on_closing(self) -> bool:
        with self._lock:
            if self._ready or self._leave:
                return True
            self._leave = True
        self._session.request_stop()
        return False

    def settle(self) -> None:
        with self._lock:
            self._ready = True
            leave = self._leave
            window = self._window
        if not leave or window is None:
            return
        try:
            window.destroy()  # type: ignore[attr-defined]
        except Exception:
            return

    def place(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            import webview

            screens = webview.screens
            if not screens:
                return
            screen = max(screens, key=lambda item: item.width * item.height)
            x = screen.width - _WIDTH - _MARGIN_X
            y = screen.height - _HEIGHT - _MARGIN_Y
            if x < 8 or y < 8:
                return
            window.move(x, y)  # type: ignore[attr-defined]
        except Exception:
            return


def run_desk(
    path: Path,
    clock: Clock,
    letter: str,
    model: object,
    settings: Settings,
    stderr: object,
) -> int:
    try:
        import webview
    except ModuleNotFoundError:
        stderr.write("缺少窗口组件：pywebview\n")  # type: ignore[attr-defined]
        return 1
    session = DeskSession(
        path=path,
        clock=clock,
        letter=letter,
        model=model,
        settings=settings,
        stderr=stderr,
    )
    code = 0
    try:
        # The library turns selection off unless this is set.
        window = webview.create_window(
            "dylan",
            html=_PAGE,
            js_api=_Api(session),
            width=_WIDTH,
            height=_HEIGHT,
            min_size=(300, 400),
            resizable=True,
            fullscreen=False,
            on_top=False,
            text_select=True,
            background_color="#F4F0E8",
            zoomable=False,
        )
        if window is None:
            stderr.write("窗口没有打开\n")  # type: ignore[attr-defined]
            return 1
        host = _Host(session)
        host.bind(window)
        session.set_on_settled(host.settle)
        window.events.closing += host.on_closing
        window.events.shown += host.place
        webview.start(private_mode=True)
    except KeyboardInterrupt:
        code = 130
    finally:
        session.request_stop()
        session.join()
    return code
