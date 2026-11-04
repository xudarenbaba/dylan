"""Process entry. Chat needs a key; development commands do not create a database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dylan.cli.commands import (
    run_consolidate,
    run_decay,
    run_lifecycle,
    run_prune,
    show_health,
    show_status,
)
from dylan.cli.lock import BrainLock
from dylan.clock import Clock, SystemClock
from dylan.config import Settings
from dylan.dialogue.loop import Session, run_chat
from dylan.errors import DylanError, MissingKey, MissingStore, StoreCorrupt
from dylan.memory.constants import ALL_STRATEGIES
from dylan.memory.decay import apply_decay
from dylan.memory.encode import bootstrap, reset_identity
from dylan.memory.store import MemoryStore

ROOT = Path(__file__).resolve().parents[3]
_AUTO = object()


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
    identity_file = identity_path or (ROOT / "persona" / "identity.md")
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
    if command == "chat" and not settings.deepseek_api_key.strip():
        stderr.write(f"{MissingKey('DEEPSEEK_API_KEY')}\n")
        return 1
    if command == "consolidate" and bool(args.all) == bool(args.strategy):
        stderr.write("需要 --strategy 或 --all\n")
        return 1
    db_path = Path(settings.dylan_db)
    if command != "chat" and not db_path.exists():
        stderr.write(f"{MissingStore(str(db_path))}\n")
        return 1
    lock = BrainLock(Path(str(db_path) + ".lock"))
    store: MemoryStore | None = None
    try:
        lock.acquire()
        if command in {"chat", "reset-identity"}:
            identity_text = _identity_text(identity_file)
        else:
            identity_text = ""
        store = _open_store(
            db_path,
            clock,
            identity_text,
            allow_create=command == "chat",
            require_identity=command != "reset-identity",
        )
        if command == "chat":
            if model is None:
                from dylan.llm.client import DeepSeekClient

                model = DeepSeekClient(settings)
            compressor = _compressor(settings, model)
            session = Session(store, settings, model, clock, identity_text, compressor)
            try:
                run_chat(session, stdin, stdout, stderr)
            except KeyboardInterrupt:
                return 130
            return 0
        if command == "status":
            return show_status(store, stdout)
        if command == "health":
            return show_health(store, stdout, settings.limits())
        if command == "decay":
            return run_decay(store, stdout)
        if command == "prune":
            return run_prune(store, stdout, dry_run=args.dry_run, limits=settings.limits())
        if command == "consolidate":
            names = ["all"] if args.all else [args.strategy]
            return run_consolidate(
                store,
                stdout,
                names=names,
                dry_run=args.dry_run,
                limits=settings.limits(),
                compressor=_compressor(settings, model),
            )
        if command == "lifecycle":
            return run_lifecycle(
                store,
                stdout,
                stderr,
                action=args.action,
                fiber_id=args.id,
                match=args.match,
                limits=settings.limits(),
            )
        reset_identity(store, identity_text)
        stdout.write("身份已重写\n")
        return 0
    except DylanError as exc:
        stderr.write(f"{exc.category}：{exc.detail}\n" if exc.detail else f"{exc.category}\n")
        return 1
    finally:
        if store is not None:
            store.close()
        lock.release()


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dylan")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("chat")
    sub.add_parser("status")
    sub.add_parser("health")
    sub.add_parser("decay")
    prune = sub.add_parser("prune")
    prune.add_argument("--dry-run", action="store_true")
    consolidate = sub.add_parser("consolidate")
    consolidate.add_argument("--strategy", choices=[*ALL_STRATEGIES, "dream"])
    consolidate.add_argument("--all", action="store_true")
    consolidate.add_argument("--dry-run", action="store_true")
    lifecycle = sub.add_parser("lifecycle")
    lifecycle.add_argument("action", choices=["freeze", "thaw", "recover"])
    lifecycle.add_argument("--id")
    lifecycle.add_argument("--match")
    reset = sub.add_parser("reset-identity")
    reset.add_argument("--yes", action="store_true")
    return parser.parse_args(argv)


def _open_store(
    path: Path,
    clock: Clock,
    identity_text: str,
    *,
    allow_create: bool,
    require_identity: bool,
) -> MemoryStore:
    if not path.exists():
        if not allow_create:
            raise MissingStore(str(path))
        store = MemoryStore.create(path, clock)
        bootstrap(store, identity_text)
        return store
    store = MemoryStore.open(path, clock)
    apply_decay(store)
    if require_identity and not store.identity_pinned():
        raise StoreCorrupt("缺少钉住身份，只能通过 reset-identity 恢复")
    return store


def _identity_text(path: Path) -> str:
    if not path.is_file():
        raise StoreCorrupt("缺少身份种子")
    return path.read_text(encoding="utf-8")


def _compressor(settings: Settings, model: object | None) -> object | None:
    if not settings.dylan_compress_with_model:
        return None
    if model is None and settings.deepseek_api_key.strip():
        from dylan.llm.client import DeepSeekClient

        model = DeepSeekClient(settings)
    if model is None:
        return None
    from dylan.llm.compress import ModelCompressor

    return ModelCompressor(model)  # type: ignore[arg-type]


if __name__ == "__main__":
    raise SystemExit(main())
