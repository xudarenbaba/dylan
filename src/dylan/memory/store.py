"""SQLite brain. One connection, explicit transactions, no ORM."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from dylan.clock import Clock, dump_time
from dylan.errors import MissingStore, StoreCorrupt
from dylan.memory.constants import BRAIN_NAME, DEFAULT_BASELINE_MOOD, RELATIONS, SCHEMA_VERSION
from dylan.memory.model import Emotion, Fiber, Mood, Neuron, Session, Synapse, Turn
from dylan.memory.text import key_of

_SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
_META_COLUMNS = frozenset(
    {
        "privacy_notice_shown",
        "identity_text",
        "identity_hash",
        "user_id",
        "self_id",
        "baseline_mood",
        "mood",
        "settled_at",
        "slept_at",
        "last_session_end",
    }
)
_FIBER_COLUMNS = (
    "anchor_id",
    "memory_type",
    "about",
    "statement",
    "detail",
    "gist",
    "evidence",
    "source",
    "importance",
    "emotion",
    "confidence",
    "strength",
    "stage",
    "detail_level",
    "state",
    "occurred_start",
    "occurred_end",
    "due_at",
    "trigger",
    "valid_until",
    "session_id",
    "created_at",
    "updated_at",
    "state_changed_at",
    "last_recalled_at",
    "recall_count",
    "recall_days",
    "settled_at",
)


def new_id() -> str:
    return str(uuid4())


class MemoryStore:
    def __init__(
        self, connection: sqlite3.Connection, clock: Clock, path: Path, readonly: bool = False
    ) -> None:
        self.conn = connection
        self.clock = clock
        self.path = path
        self.readonly = readonly
        self._tx = 0

    @classmethod
    def create(cls, path: Path, clock: Clock) -> MemoryStore:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise StoreCorrupt("文件已存在")
        conn = _connect(path)
        try:
            conn.executescript(_SCHEMA)
            now = dump_time(clock.now())
            conn.execute(
                """
                INSERT INTO meta (id, schema_version, brain_name, created_at, settled_at,
                                  baseline_mood)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (SCHEMA_VERSION, BRAIN_NAME, now, now, DEFAULT_BASELINE_MOOD),
            )
        except Exception:
            conn.close()
            _unlink(path)
            raise
        return cls(conn, clock, path)

    @classmethod
    def open(cls, path: Path, clock: Clock) -> MemoryStore:
        if not path.exists():
            raise MissingStore(str(path))
        try:
            conn = _plain(path)
        except sqlite3.DatabaseError as exc:
            raise StoreCorrupt("无法读取") from exc
        _check(conn)
        try:
            _tune(conn)
        except sqlite3.DatabaseError as exc:
            conn.close()
            raise StoreCorrupt("无法读取") from exc
        return cls(conn, clock, path)

    @classmethod
    def open_readonly(cls, path: Path, clock: Clock) -> MemoryStore:
        """Read a brain without the writer lock and without creating the file."""
        if not path.exists():
            raise MissingStore(str(path))
        uri = path.resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=True)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA busy_timeout=5000")
        except sqlite3.DatabaseError as exc:
            conn.close()
            raise StoreCorrupt("无法读取") from exc
        _check(conn)
        return cls(conn, clock, path, readonly=True)

    def close(self) -> None:
        try:
            if not self.readonly:
                self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            self.conn.close()

    def discard(self) -> None:
        """Close and remove a brain that never finished being born."""
        self.conn.close()
        _unlink(self.path)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        started = False
        if self._tx == 0:
            self.conn.execute("BEGIN")
            started = True
        self._tx += 1
        try:
            yield
            self._tx -= 1
            if started and self._tx == 0:
                self.conn.execute("COMMIT")
        except Exception:
            self._tx = 0
            self.conn.execute("ROLLBACK")
            raise

    def now(self) -> str:
        return dump_time(self.clock.now())

    # meta

    def meta(self) -> sqlite3.Row:
        return self.conn.execute("SELECT * FROM meta WHERE id = 1").fetchone()

    def set_meta(self, **values: object) -> None:
        for column in values:
            if column not in _META_COLUMNS:
                raise ValueError(column)
        assignments = ", ".join(f"{column} = ?" for column in values)
        self.conn.execute(f"UPDATE meta SET {assignments} WHERE id = 1", tuple(values.values()))

    def born(self) -> bool:
        row = self.meta()
        return bool(row["identity_text"]) and bool(row["self_id"]) and bool(row["user_id"])

    def privacy_shown(self) -> bool:
        return bool(self.meta()["privacy_notice_shown"])

    def mark_privacy_shown(self) -> None:
        with self.transaction():
            self.set_meta(privacy_notice_shown=1)

    def mood(self) -> Mood | None:
        raw = self.meta()["mood"]
        return Mood.model_validate_json(raw) if raw else None

    def set_mood(self, mood: Mood | None) -> None:
        self.set_meta(mood=None if mood is None else mood.model_dump_json())

    # neurons

    def ensure_neuron(self, kind: str, name: str, *, innate: bool = False) -> Neuron:
        key = key_of(name)
        row = self.conn.execute(
            "SELECT * FROM neurons WHERE kind = ? AND name_key = ?", (kind, key)
        ).fetchone()
        if row is not None:
            if innate and not row["innate"]:
                self.conn.execute("UPDATE neurons SET innate = 1 WHERE id = ?", (row["id"],))
                return self.neuron(row["id"])  # type: ignore[return-value]
            return _neuron(row)
        neuron = Neuron(
            id=new_id(), kind=kind, name=name, name_key=key, innate=innate, created_at=self.now()
        )
        self.conn.execute(
            "INSERT INTO neurons (id, kind, name, name_key, innate, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (neuron.id, neuron.kind, neuron.name, neuron.name_key, int(innate), neuron.created_at),
        )
        return neuron

    def neuron(self, neuron_id: str) -> Neuron | None:
        row = self.conn.execute("SELECT * FROM neurons WHERE id = ?", (neuron_id,)).fetchone()
        return None if row is None else _neuron(row)

    def neurons(self) -> list[Neuron]:
        rows = self.conn.execute("SELECT * FROM neurons ORDER BY created_at")
        return [_neuron(row) for row in rows]

    def find_nodes(self, name: str) -> list[Neuron]:
        key = key_of(name)
        rows = self.conn.execute(
            """
            SELECT DISTINCT n.* FROM neurons n
            LEFT JOIN aliases a ON a.neuron_id = n.id
            WHERE n.kind != 'memory' AND (n.name_key = ? OR a.alias_key = ?)
            ORDER BY n.innate DESC, n.created_at
            """,
            (key, key),
        ).fetchall()
        return [_neuron(row) for row in rows]

    def add_alias(self, neuron_id: str, alias: str) -> None:
        text = alias.strip()
        if not text:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO aliases (neuron_id, alias, alias_key) VALUES (?, ?, ?)",
            (neuron_id, text, key_of(text)),
        )

    def aliases(self) -> dict[str, list[str]]:
        found: dict[str, list[str]] = defaultdict(list)
        for row in self.conn.execute("SELECT neuron_id, alias FROM aliases ORDER BY alias"):
            found[row["neuron_id"]].append(row["alias"])
        return dict(found)

    def name_index(self) -> dict[str, set[str]]:
        """Name and alias keys of every node, for exact lookups during recall."""
        index: dict[str, set[str]] = defaultdict(set)
        for row in self.conn.execute("SELECT id, name_key FROM neurons WHERE kind != 'memory'"):
            index[row["name_key"]].add(row["id"])
        for row in self.conn.execute("SELECT neuron_id, alias_key FROM aliases"):
            index[row["alias_key"]].add(row["neuron_id"])
        return dict(index)

    def delete_neuron(self, neuron_id: str) -> None:
        self.conn.execute("DELETE FROM neurons WHERE id = ?", (neuron_id,))

    def set_kind(self, neuron_id: str, kind: str) -> Neuron | None:
        """A vague topic becomes a person, place or pet once she knows what it is."""
        current = self.neuron(neuron_id)
        if current is None:
            return None
        clash = self.conn.execute(
            "SELECT 1 FROM neurons WHERE kind = ? AND name_key = ?", (kind, current.name_key)
        ).fetchone()
        if clash is None:
            self.conn.execute("UPDATE neurons SET kind = ? WHERE id = ?", (kind, neuron_id))
        return self.neuron(neuron_id)

    def rename_neuron(self, neuron_id: str, name: str) -> None:
        """Keep the old name as an alias so earlier mentions still find the same node."""
        current = self.neuron(neuron_id)
        if current is None or key_of(name) == current.name_key:
            return
        clash = self.conn.execute(
            "SELECT 1 FROM neurons WHERE kind = ? AND name_key = ? AND id != ?",
            (current.kind, key_of(name), neuron_id),
        ).fetchone()
        if clash is not None:
            self.add_alias(neuron_id, name)
            return
        self.conn.execute(
            "UPDATE neurons SET name = ?, name_key = ? WHERE id = ?",
            (name, key_of(name), neuron_id),
        )
        self.add_alias(neuron_id, current.name)

    def mark_innate(self, neuron_id: str) -> None:
        self.conn.execute("UPDATE neurons SET innate = 1 WHERE id = ?", (neuron_id,))

    # synapses

    def add_synapse(
        self,
        source_id: str,
        target_id: str,
        synapse_type: str,
        *,
        base_weight: float,
        label: str = "",
        innate: bool = False,
    ) -> tuple[Synapse, bool]:
        if source_id == target_id:
            raise ValueError("synapse ends must differ")
        if RELATIONS[synapse_type][2] and target_id < source_id:
            source_id, target_id = target_id, source_id
        existing = self.synapse_between(source_id, target_id, synapse_type)
        if existing is not None:
            if innate and not existing.innate:
                self.conn.execute("UPDATE synapses SET innate = 1 WHERE id = ?", (existing.id,))
                existing.innate = True
            if label and not existing.label:
                self.conn.execute(
                    "UPDATE synapses SET label = ? WHERE id = ?", (label, existing.id)
                )
                existing.label = label
            return existing, False
        now = self.now()
        synapse = Synapse(
            id=new_id(),
            source_id=source_id,
            target_id=target_id,
            type=synapse_type,
            label=label,
            base_weight=max(0.0, min(1.0, base_weight)),
            innate=innate,
            created_at=now,
            last_activated_at=now,
        )
        self.conn.execute(
            """
            INSERT INTO synapses (id, source_id, target_id, type, label, base_weight,
                                  rehearsal_count, innate, created_at, last_activated_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                synapse.id,
                source_id,
                target_id,
                synapse_type,
                label,
                synapse.base_weight,
                int(innate),
                now,
                now,
            ),
        )
        return synapse, True

    def synapse_between(self, source_id: str, target_id: str, synapse_type: str) -> Synapse | None:
        if RELATIONS.get(synapse_type, ("", "", False))[2] and target_id < source_id:
            source_id, target_id = target_id, source_id
        row = self.conn.execute(
            "SELECT * FROM synapses WHERE source_id = ? AND target_id = ? AND type = ?",
            (source_id, target_id, synapse_type),
        ).fetchone()
        return None if row is None else _synapse(row)

    def synapses(self) -> list[Synapse]:
        return [_synapse(row) for row in self.conn.execute("SELECT * FROM synapses")]

    def save_synapse(self, synapse: Synapse) -> None:
        self.conn.execute(
            """
            UPDATE synapses SET base_weight = ?, rehearsal_count = ?, last_activated_at = ?,
                                label = ?, innate = ?
            WHERE id = ?
            """,
            (
                synapse.base_weight,
                synapse.rehearsal_count,
                synapse.last_activated_at,
                synapse.label,
                int(synapse.innate),
                synapse.id,
            ),
        )

    def delete_synapse(self, synapse_id: str) -> None:
        self.conn.execute("DELETE FROM synapses WHERE id = ?", (synapse_id,))

    def synapse_owners(self) -> dict[str, list[str]]:
        owners: dict[str, list[str]] = defaultdict(list)
        for row in self.conn.execute("SELECT fiber_id, synapse_id FROM fiber_synapses"):
            owners[row["synapse_id"]].append(row["fiber_id"])
        return dict(owners)

    # fibers

    def insert_fiber(self, fiber: Fiber) -> None:
        columns = ("id", *_FIBER_COLUMNS)
        marks = ", ".join("?" for _ in columns)
        self.conn.execute(
            f"INSERT INTO fibers ({', '.join(columns)}) VALUES ({marks})",
            (fiber.id, *_fiber_values(fiber)),
        )
        self.add_members(fiber.id, fiber.neuron_ids)
        for synapse_id in fiber.synapse_ids:
            self.link_fiber_synapse(fiber.id, synapse_id)
        self.add_cues(fiber.id, fiber.cues)

    def save_fiber(self, fiber: Fiber) -> None:
        assignments = ", ".join(f"{column} = ?" for column in _FIBER_COLUMNS)
        self.conn.execute(
            f"UPDATE fibers SET {assignments} WHERE id = ?",
            (*_fiber_values(fiber), fiber.id),
        )

    def fiber(self, fiber_id: str) -> Fiber | None:
        found = self._load("WHERE id = ?", (fiber_id,))
        return found[0] if found else None

    def fibers(self, states: Iterable[str] | None = None) -> list[Fiber]:
        if states is None:
            return self._load("", ())
        wanted = tuple(states)
        marks = ", ".join("?" for _ in wanted)
        return self._load(f"WHERE state IN ({marks})", wanted)

    def fiber_by_anchor(self, anchor_id: str) -> Fiber | None:
        found = self._load("WHERE anchor_id = ?", (anchor_id,))
        return found[0] if found else None

    def add_members(self, fiber_id: str, neuron_ids: Iterable[str]) -> None:
        current = [
            row["neuron_id"]
            for row in self.conn.execute(
                "SELECT neuron_id FROM fiber_neurons WHERE fiber_id = ? ORDER BY position",
                (fiber_id,),
            )
        ]
        position = len(current)
        for neuron_id in neuron_ids:
            if neuron_id in current:
                continue
            self.conn.execute(
                "INSERT INTO fiber_neurons (fiber_id, position, neuron_id) VALUES (?, ?, ?)",
                (fiber_id, position, neuron_id),
            )
            current.append(neuron_id)
            position += 1

    def link_fiber_synapse(self, fiber_id: str, synapse_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO fiber_synapses (fiber_id, synapse_id) VALUES (?, ?)",
            (fiber_id, synapse_id),
        )

    def add_cues(self, fiber_id: str, cues: Iterable[str]) -> None:
        for cue in cues:
            term = cue.strip()
            if not term:
                continue
            self.conn.execute(
                "INSERT OR IGNORE INTO cues (fiber_id, term, term_key) VALUES (?, ?, ?)",
                (fiber_id, term, key_of(term)),
            )

    def clear_cues(self, fiber_id: str) -> None:
        self.conn.execute("DELETE FROM cues WHERE fiber_id = ?", (fiber_id,))

    def cue_index(self) -> dict[str, set[str]]:
        index: dict[str, set[str]] = defaultdict(set)
        for row in self.conn.execute("SELECT fiber_id, term_key FROM cues"):
            index[row["term_key"]].add(row["fiber_id"])
        return dict(index)

    def delete_fiber(self, fiber_id: str) -> None:
        """Gone for good, including what the journal said about it."""
        row = self.conn.execute("SELECT anchor_id FROM fibers WHERE id = ?", (fiber_id,)).fetchone()
        self.conn.execute("DELETE FROM fibers WHERE id = ?", (fiber_id,))
        self.conn.execute(
            "UPDATE journal SET label = '', reason = '' WHERE fiber_id = ?", (fiber_id,)
        )
        if row is not None:
            self.delete_neuron(row["anchor_id"])

    def _load(self, where: str, params: tuple[object, ...]) -> list[Fiber]:
        query = f"SELECT * FROM fibers {where} ORDER BY created_at"
        rows = self.conn.execute(query, params).fetchall()
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        members: dict[str, list[str]] = defaultdict(list)
        links: dict[str, list[str]] = defaultdict(list)
        cues: dict[str, list[str]] = defaultdict(list)
        single = len(ids) == 1
        suffix = " WHERE fiber_id = ?" if single else ""
        args: tuple[object, ...] = (ids[0],) if single else ()
        for item in self.conn.execute(
            f"SELECT fiber_id, neuron_id FROM fiber_neurons{suffix} ORDER BY position", args
        ):
            members[item["fiber_id"]].append(item["neuron_id"])
        for item in self.conn.execute(
            f"SELECT fiber_id, synapse_id FROM fiber_synapses{suffix}", args
        ):
            links[item["fiber_id"]].append(item["synapse_id"])
        for item in self.conn.execute(
            f"SELECT fiber_id, term FROM cues{suffix} ORDER BY term", args
        ):
            cues[item["fiber_id"]].append(item["term"])
        return [_fiber(row, members[row["id"]], links[row["id"]], cues[row["id"]]) for row in rows]

    # co-recall

    def bump_coactivation(self, left: str, right: str) -> int:
        first, second = sorted((left, right))
        self.conn.execute(
            """
            INSERT INTO coactivations (neuron_a, neuron_b, count, last_on) VALUES (?, ?, 1, ?)
            ON CONFLICT(neuron_a, neuron_b)
            DO UPDATE SET count = count + 1, last_on = excluded.last_on
            """,
            (first, second, self.now()),
        )
        row = self.conn.execute(
            "SELECT count FROM coactivations WHERE neuron_a = ? AND neuron_b = ?", (first, second)
        ).fetchone()
        return int(row["count"])

    # sessions and turns

    def start_session(self) -> Session:
        session = Session(id=new_id(), started_at=self.now())
        self.conn.execute(
            "INSERT INTO sessions (id, started_at) VALUES (?, ?)", (session.id, session.started_at)
        )
        return session

    def session(self, session_id: str) -> Session | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return None if row is None else _session(row)

    def sessions(self) -> list[Session]:
        rows = self.conn.execute("SELECT * FROM sessions ORDER BY started_at").fetchall()
        return [_session(row) for row in rows]

    def set_session_summary(self, session_id: str, summary: str) -> None:
        self.conn.execute("UPDATE sessions SET summary = ? WHERE id = ?", (summary, session_id))

    def end_session(self, session_id: str, at: str | None = None) -> None:
        moment = at or self.now()
        self.conn.execute(
            "UPDATE sessions SET ended_at = COALESCE(ended_at, ?) WHERE id = ?",
            (moment, session_id),
        )
        row = self.conn.execute(
            "SELECT ended_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        last = self.meta()["last_session_end"]
        if row is not None and (last is None or row["ended_at"] > last):
            self.set_meta(last_session_end=row["ended_at"])

    def delete_session(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def forget_turns(self, session_id: str) -> None:
        """After sleep the raw words go; what mattered already lives in memory."""
        self.conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))

    def mark_slept(self, session_id: str) -> None:
        self.conn.execute("UPDATE sessions SET slept = 1 WHERE id = ?", (session_id,))

    def bump_sleep_attempts(self, session_id: str) -> int:
        self.conn.execute(
            "UPDATE sessions SET sleep_attempts = sleep_attempts + 1 WHERE id = ?", (session_id,)
        )
        row = self.conn.execute(
            "SELECT sleep_attempts FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return int(row["sleep_attempts"]) if row is not None else 0

    def add_turn(self, session_id: str, user_text: str, reply_text: str) -> Turn:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM turns WHERE session_id = ?", (session_id,)
        ).fetchone()
        turn = Turn(
            id=new_id(),
            session_id=session_id,
            position=int(row["n"]),
            at=self.now(),
            user_text=user_text,
            reply_text=reply_text,
        )
        self.conn.execute(
            """
            INSERT INTO turns (id, session_id, position, at, user_text, reply_text, noted, attempts)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (turn.id, session_id, turn.position, turn.at, user_text, reply_text),
        )
        return turn

    def turns(self, session_id: str) -> list[Turn]:
        rows = self.conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY position", (session_id,)
        ).fetchall()
        return [_turn(row) for row in rows]

    def pending_turns(self) -> list[Turn]:
        rows = self.conn.execute(
            "SELECT * FROM turns WHERE noted = 0 ORDER BY at, position"
        ).fetchall()
        return [_turn(row) for row in rows]

    def mark_noted(self, turn_id: str) -> None:
        self.conn.execute("UPDATE turns SET noted = 1 WHERE id = ?", (turn_id,))

    def bump_attempts(self, turn_id: str) -> int:
        self.conn.execute("UPDATE turns SET attempts = attempts + 1 WHERE id = ?", (turn_id,))
        row = self.conn.execute("SELECT attempts FROM turns WHERE id = ?", (turn_id,)).fetchone()
        return int(row["attempts"])

    # journal

    def log(
        self,
        phase: str,
        op: str,
        status: str,
        *,
        fiber_id: str | None = None,
        label: str = "",
        reason: str = "",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO journal (at, phase, op, fiber_id, label, status, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (self.now(), phase, op, fiber_id, label, status, reason),
        )

    def journal(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def initiative_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT at, op, fiber_id, reason, label FROM journal
            WHERE phase = 'initiative' AND op IN ('speak', 'heard')
            ORDER BY id
            """
        ).fetchall()

    def mark_he_replied(self) -> None:
        """His real sentence clears an initiative he had not answered."""
        rows = self.initiative_rows()
        if rows and rows[-1]["op"] == "speak":
            self.log("initiative", "heard", "ok")

    def touched_since(self, moment: str) -> list[str]:
        """Memories written or changed since a moment, most recent first."""
        rows = self.conn.execute(
            """
            SELECT fiber_id, MAX(id) AS last FROM journal
            WHERE at >= ? AND fiber_id IS NOT NULL AND status != 'rejected'
            GROUP BY fiber_id ORDER BY last DESC
            """,
            (moment,),
        ).fetchall()
        return [row["fiber_id"] for row in rows]

    # checks

    def counts(self) -> dict[str, int]:
        found: dict[str, int] = {}
        for table in ("neurons", "synapses", "fibers", "sessions", "turns", "journal"):
            row = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            found[table] = int(row["n"])
        return found

    def search_text(self, needle: str) -> bool:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        targets = (
            ("neurons", "name"),
            ("aliases", "alias"),
            ("synapses", "label"),
            ("fibers", "statement"),
            ("fibers", "detail"),
            ("fibers", "gist"),
            ("fibers", "evidence"),
            ("fibers", "trigger"),
            ("fibers", "emotion"),
            ("cues", "term"),
            ("sessions", "summary"),
            ("turns", "user_text"),
            ("turns", "reply_text"),
            ("journal", "label"),
            ("journal", "reason"),
            ("meta", "identity_text"),
            ("meta", "mood"),
        )
        for table, column in targets:
            row = self.conn.execute(
                f"SELECT 1 FROM {table} WHERE {column} LIKE ? ESCAPE '\\' LIMIT 1", (like,)
            ).fetchone()
            if row is not None:
                return True
        return False


def _plain(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=True)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    return conn


def _tune(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")


def _connect(path: Path) -> sqlite3.Connection:
    conn = _plain(path)
    _tune(conn)
    return conn


def _check(conn: sqlite3.Connection) -> None:
    try:
        row = conn.execute("SELECT schema_version, brain_name FROM meta WHERE id = 1").fetchone()
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise StoreCorrupt("无法读取") from exc
    if row is None:
        conn.close()
        raise StoreCorrupt("缺少大脑记录")
    version = int(row["schema_version"])
    if version > SCHEMA_VERSION:
        conn.close()
        raise StoreCorrupt("模式版本不受支持")
    if row["brain_name"] != BRAIN_NAME:
        conn.close()
        raise StoreCorrupt("大脑名不是 dylan")
    if version < SCHEMA_VERSION:
        conn.close()
        raise StoreCorrupt("记忆库版本过旧，请把它改名备份后重新启动")


def _unlink(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def _neuron(row: sqlite3.Row) -> Neuron:
    return Neuron(
        id=row["id"],
        kind=row["kind"],
        name=row["name"],
        name_key=row["name_key"],
        innate=bool(row["innate"]),
        created_at=row["created_at"],
    )


def _synapse(row: sqlite3.Row) -> Synapse:
    return Synapse(
        id=row["id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        type=row["type"],
        label=row["label"],
        base_weight=row["base_weight"],
        rehearsal_count=row["rehearsal_count"],
        innate=bool(row["innate"]),
        created_at=row["created_at"],
        last_activated_at=row["last_activated_at"],
    )


def _fiber_values(fiber: Fiber) -> tuple[object, ...]:
    values: list[object] = []
    for column in _FIBER_COLUMNS:
        value = getattr(fiber, column)
        if column == "emotion":
            value = None if value is None else value.model_dump_json()
        elif column == "recall_days":
            value = json.dumps(value, ensure_ascii=False)
        values.append(value)
    return tuple(values)


def _fiber(row: sqlite3.Row, members: list[str], links: list[str], cues: list[str]) -> Fiber:
    data = {column: row[column] for column in _FIBER_COLUMNS}
    data["emotion"] = Emotion.model_validate_json(row["emotion"]) if row["emotion"] else None
    data["recall_days"] = json.loads(row["recall_days"])
    return Fiber(id=row["id"], neuron_ids=members, synapse_ids=links, cues=cues, **data)


def _session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        summary=row["summary"],
        slept=bool(row["slept"]),
    )


def _turn(row: sqlite3.Row) -> Turn:
    return Turn(
        id=row["id"],
        session_id=row["session_id"],
        position=row["position"],
        at=row["at"],
        user_text=row["user_text"],
        reply_text=row["reply_text"],
        noted=bool(row["noted"]),
        attempts=row["attempts"],
    )
