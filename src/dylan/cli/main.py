"""Process entry. Chat needs a key; dev commands never create a brain."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dylan.cli.commands import show_status
from dylan.cli.lock import BrainLock
from dylan.clock import Clock, SystemClock, zone
from dylan.config import Settings
from dylan.dialogue.loop import Conversation, be_born, be_reborn, run_chat, sleep_pending
from dylan.errors import DylanError, MissingKey, MissingStore, StoreCorrupt
from dylan.memory.life import letter_changed
from dylan.memory.maintain import maintain
from dylan.memory.store import MemoryStore

ROOT = Path(__file__).resolve().parents[3]
_AUTO = object()
LETTER_CHANGED = (
    "身份信和她出生时读到的不一样了。她仍按出生时的那封信生活；"
    "确实要改她的天性，退出后执行 dylan reset-identity --yes"
)
_NEEDS_KEY = frozenset({"chat", "sleep", "reset-identity"})


def main(
    argv: list[str] | None = None,
    *,
    clock: Clock | None = None,
    model: object | None = None,
    stdin: object | None = None,
    stdout: object | None = None,
    stderr: object | None = None,
    settings: Settings | None = None,
    env_file: Path | None | object = _AUTO,
    identity_path: Path | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    stdin = stdin or sys.stdin
    clock = clock or SystemClock()
    letter_file = identity_path or (ROOT / "persona" / "identity.md")
    try:
        args = _parse(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as exc:
        code = exc.code
        return 1 if code is None else int(code)
    if env_file is _AUTO:
        env_file = ROOT / ".env"
    if settings is None:
        if env_file is not None:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        settings = Settings()
    command = args.command or "chat"
    if command == "reset-identity" and not args.yes:
        stderr.write("拒绝执行：需要 --yes\n")
        return 1
    if command in _NEEDS_KEY and not settings.deepseek_api_key.strip():
        stderr.write(f"{MissingKey('DEEPSEEK_API_KEY')}\n")
        return 1
    db_path = Path(settings.dylan_db)
    if command != "chat" and not db_path.exists():
        stderr.write(f"{MissingStore(str(db_path))}\n")
        return 1
    if command == "memory":
        from dylan.viz.server import serve

        try:
            return serve(db_path, port=args.port, stdout=stdout, tz=zone(settings.dylan_timezone))
        except KeyboardInterrupt:
            return 130
        except DylanError as exc:
            stderr.write(_error(exc))
            return 1
    lock = BrainLock(Path(str(db_path) + ".lock"))
    store: MemoryStore | None = None
    try:
        lock.acquire()
        if command in {"chat", "reset-identity"}:
            letter = _letter(letter_file)
        else:
            letter = ""
        if model is None and command in _NEEDS_KEY:
            from dylan.llm.client import DeepSeekClient

            model = DeepSeekClient(settings)
        if command == "chat":
            store = _open_for_chat(db_path, clock, letter, model, settings, stderr)
            if store is None:
                return 1
            conversation = Conversation(store, settings, model, clock)
            try:
                run_chat(conversation, stdin, stdout, stderr)
            except KeyboardInterrupt:
                return 130
            return 0
        store = MemoryStore.open(db_path, clock)
        if not store.born():
            raise StoreCorrupt("这块大脑还没有出生，请删除后重新启动对话")
        if command == "status":
            return show_status(store, stdout, zone(settings.dylan_timezone))
        if command == "sleep":
            done = sleep_pending(store, model, settings, stderr)
            stdout.write(f"整理了 {done} 次会话\n")
            return 0
        if command == "maintain":
            result = maintain(store)
            stdout.write(
                f"结算 {result.settled} 条，清理连线 {result.links} 条、"
                f"记忆 {result.memories} 条、节点 {result.nodes} 个\n"
            )
            return 0
        be_reborn(store, letter, model, settings)
        stdout.write("天性已重写，她的经历和成长都还在\n")
        return 0
    except DylanError as exc:
        stderr.write(_error(exc))
        return 1
    finally:
        if store is not None:
            store.close()
        lock.release()


def _open_for_chat(
    path: Path,
    clock: Clock,
    letter: str,
    model: object,
    settings: Settings,
    stderr: object,
) -> MemoryStore | None:
    if not path.exists():
        store = MemoryStore.create(path, clock)
        try:
            be_born(store, letter, model, settings)
        except DylanError:
            store.discard()
            raise
        return store
    store = MemoryStore.open(path, clock)
    if not store.born():
        store.close()
        raise StoreCorrupt("这块大脑没有完成出生，请把它改名备份后重新启动")
    if letter_changed(store, letter):
        stderr.write(LETTER_CHANGED + "\n")  # type: ignore[attr-defined]
    sleep_pending(store, model, settings, stderr)
    return store


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dylan")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("chat")
    sub.add_parser("status")
    sub.add_parser("sleep")
    sub.add_parser("maintain")
    reset = sub.add_parser("reset-identity")
    reset.add_argument("--yes", action="store_true")
    memory = sub.add_parser("memory")
    memory.add_argument("--port", type=int, default=8765)
    return parser.parse_args(argv)


def _letter(path: Path) -> str:
    if not path.is_file():
        raise StoreCorrupt("缺少身份信")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise StoreCorrupt("身份信是空的")
    return text


def _error(exc: DylanError) -> str:
    return f"{exc.category}：{exc.detail}\n" if exc.detail else f"{exc.category}\n"


if __name__ == "__main__":
    raise SystemExit(main())
