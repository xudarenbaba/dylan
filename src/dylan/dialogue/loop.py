"""One turn, then a clean exit. Ctrl-C leaves before the session episode."""

from __future__ import annotations

from dylan.clock import Clock, dump_time
from dylan.config import Settings
from dylan.dialogue.buffer import Buffer
from dylan.dialogue.depth import choose_depth
from dylan.dialogue.extract import plan_turn
from dylan.dialogue.prompt import build_messages, hot_entries, pack_hot, pack_recall
from dylan.dialogue.rules import extract_rules
from dylan.dialogue.secrets import has_secret
from dylan.dialogue.thought import Thought, build_thought
from dylan.errors import DylanError
from dylan.memory.compress import visible_text
from dylan.memory.consolidate.habits import strengthen_online
from dylan.memory.consolidate.runner import short_consolidation
from dylan.memory.constants import HOT_TYPES, PRIVACY_NOTICE
from dylan.memory.encode import forget_fragment, write_drafts, write_episode
from dylan.memory.lifecycle import expire_due
from dylan.memory.recall import Recall, persist_recall, recall
from dylan.memory.store import MemoryStore, day_key


class Session:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings,
        model: object,
        clock: Clock,
        identity_text: str,
        compressor: object | None = None,
    ) -> None:
        self.store = store
        self.settings = settings
        self.model = model
        self.clock = clock
        self.identity_text = identity_text
        self.compressor = compressor
        self.buffer = Buffer(settings.dylan_buffer_turns)
        self.seen_orders: set[str] = set()
        self.touched: set[str] = set()
        self.turns_done = False
        self.pending = ""
        self.last_thought: Thought | None = None

    def turn(self, text: str, stdout: object, stderr: object) -> None:
        if self.pending:
            stderr.write(self.pending + "\n")  # type: ignore[attr-defined]
            self.pending = ""
        with self.store.transaction():
            expire_due(self.store)
        depth, hops, window = choose_depth(text)
        result = recall(
            self.store,
            text,
            depth=depth,
            max_hops=hops,
            window_days=window,
            limits=self.settings.limits(),
            persist=False,
        )
        preview, _forgets = extract_rules(text)
        novel = [
            draft.summary
            for draft in preview
            if not has_secret(draft.summary, self.settings.deepseek_api_key)
        ]
        now = dump_time(self.clock.now())
        thought = build_thought(result, novel, now_text=now)
        self.last_thought = thought
        if self.settings.dylan_show_thought:
            stderr.write(thought.model_dump_json() + "\n")  # type: ignore[attr-defined]
        messages = build_messages(
            identity_text=self.identity_text,
            hot_text=pack_hot(hot_entries(self.store.fibers()), self.settings.dylan_hot_chars),
            thought=thought,
            recall_text=_recall_text(result, self.clock, self.settings.dylan_recall_chars),
            buffer=self.buffer,
            user_text=text,
        )
        chunks: list[str] = []
        try:
            for chunk in self.model.stream_reply(messages):  # type: ignore[attr-defined]
                chunks.append(chunk)
                stdout.write(chunk)  # type: ignore[attr-defined]
                stdout.flush()  # type: ignore[attr-defined]
        except DylanError as exc:
            stderr.write(exc.category + "\n")  # type: ignore[attr-defined]
            if chunks and not str(chunks[-1]).endswith("\n"):
                stdout.write("\n")  # type: ignore[attr-defined]
            return
        answer = "".join(chunks)
        if not answer.endswith("\n"):
            stdout.write("\n")  # type: ignore[attr-defined]
        try:
            self._commit(text, answer, result, stderr)
        except Exception:
            self.pending = "上一轮没有记住"
            stderr.write("上一轮没有记住\n")  # type: ignore[attr-defined]

    def _commit(self, user: str, answer: str, result: Recall, stderr: object) -> None:
        drafts, forgets, warnings = plan_turn(
            user, answer, self.model, self.settings.deepseek_api_key
        )
        for warning in warnings:
            stderr.write(warning + "\n")  # type: ignore[attr-defined]
        spilled = self.buffer.spill()
        with self.store.transaction():
            persist_recall(self.store, result)
            if spilled is not None:
                pair = _pair_text(*spilled)
                if not has_secret(pair, self.settings.deepseek_api_key):
                    write_episode(self.store, pair, [], auto_session=False)
            for fragment in forgets:
                for message in forget_fragment(self.store, fragment):
                    stderr.write(message + "\n")  # type: ignore[attr-defined]
            written = write_drafts(self.store, drafts, self.settings.limits())
            self._note_habits(written)
            for hit in result.hits:
                self.touched.update(hit.fiber.neuron_ids)
            for fiber in written:
                self.touched.update(fiber.neuron_ids)
        self.buffer.commit(user, answer)
        self.turns_done = True

    def _note_habits(self, written: list) -> None:
        day = day_key(dump_time(self.clock.now()))
        for fiber in written:
            ids: list[str] = []
            for neuron_id in fiber.neuron_ids:
                neuron = self.store.neuron(neuron_id)
                if neuron is not None and neuron.kind in {"concept", "entity"}:
                    ids.append(neuron.id)
            if len(ids) < 2:
                continue
            signature = ">".join(ids)
            self.store.observe_sequence(signature, day)
            if signature in self.seen_orders:
                strengthen_online(self.store, ids)
            self.seen_orders.add(signature)

    def finish(self) -> None:
        if self.turns_done:
            pairs = []
            for user, answer in self.buffer.turns:
                pair = _pair_text(user, answer)
                if has_secret(pair, self.settings.deepseek_api_key):
                    continue
                pairs.append(pair)
            if pairs:
                with self.store.transaction():
                    write_episode(
                        self.store,
                        "\n".join(pairs),
                        list(self.touched),
                        auto_session=True,
                    )
        short_consolidation(
            self.store,
            auto_dream=self.settings.dylan_auto_dream,
            compressor=self.compressor,  # type: ignore[arg-type]
            limits=self.settings.limits(),
        )


def run_chat(session: Session, stdin: object, stdout: object, stderr: object) -> None:
    if not session.store.privacy_shown():
        stdout.write(PRIVACY_NOTICE + "\n")  # type: ignore[attr-defined]
        stdout.flush()  # type: ignore[attr-defined]
        session.store.mark_privacy_shown()
    while True:
        line = stdin.readline()  # type: ignore[attr-defined]
        if line == "":
            session.finish()
            return
        stripped = line.strip()
        if stripped == "":
            continue
        if stripped in {"exit", "quit"}:
            session.finish()
            return
        session.turn(stripped, stdout, stderr)


def _recall_text(result: Recall, clock: Clock, budget: int) -> str:
    now = clock.now()
    items = [
        (hit.score, visible_text(hit.fiber, now))
        for hit in result.hits
        if hit.fiber.memory_type not in HOT_TYPES
    ]
    return pack_recall(items, budget)


def _pair_text(user: str, answer: str) -> str:
    return f"用户：{user}\ndylan：{answer}"
