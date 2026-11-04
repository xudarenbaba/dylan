"""SQLite brain. One connection, explicit transactions, no ORM."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from dylan.clock import Clock, dump_time, load_time
from dylan.errors import MissingStore, StoreCorrupt
from dylan.memory.constants import BRAIN_NAME, SCHEMA_VERSION
from dylan.memory.decay import effective_weight
from dylan.memory.jaccard import content_key
from dylan.memory.model import Fiber, Neuron, Provenance, Synapse

_SCHEMA = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")


class MemoryStore:
    def __init__(self, connection: sqlite3.Connection, clock: Clock, path: Path) -> None:
        self.conn = connection
        self.clock = clock
        self.path = path
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
                INSERT INTO meta (id, schema_version, brain_name, created_at, privacy_notice_shown)
                VALUES (1, ?, ?, ?, 0)
                """,
                (SCHEMA_VERSION, BRAIN_NAME, now),
            )
        except Exception:
            conn.close()
            if path.exists():
                path.unlink()
            raise
        return cls(conn, clock, path)

    @classmethod
    def open(cls, path: Path, clock: Clock) -> MemoryStore:
        if not path.exists():
            raise MissingStore(str(path))
        conn: sqlite3.Connection | None = None
        try:
            conn = _connect(path)
            row = conn.execute(
                "SELECT schema_version, brain_name FROM meta WHERE id = 1"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            if conn is not None:
                conn.close()
            raise StoreCorrupt("无法读取") from exc
        if row is None:
            conn.close()
            raise StoreCorrupt("缺少大脑记录")
        if int(row["schema_version"]) > SCHEMA_VERSION:
            conn.close()
            raise StoreCorrupt("模式版本不受支持")
        if row["brain_name"] != BRAIN_NAME:
            conn.close()
            raise StoreCorrupt("大脑名不是 dylan")
        if int(row["schema_version"]) < SCHEMA_VERSION:
            conn.close()
            raise StoreCorrupt("缺少可用迁移")
        return cls(conn, clock, path)

    def close(self) -> None:
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            self.conn.close()

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

    def rollback_outer(self) -> None:
        if self._tx:
            self.conn.execute("ROLLBACK")
            self._tx = 0

    def hold_transaction(self) -> None:
        if self._tx == 0:
            self.conn.execute("BEGIN")
            self._tx = 1

    def privacy_shown(self) -> bool:
        row = self.conn.execute("SELECT privacy_notice_shown FROM meta WHERE id = 1").fetchone()
        return bool(row["privacy_notice_shown"])

    def mark_privacy_shown(self) -> None:
        with self.transaction():
            self.conn.execute("UPDATE meta SET privacy_notice_shown = 1 WHERE id = 1")

    def identity_pinned(self) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM fibers
            WHERE memory_type = 'identity' AND pinned = 1 AND state = 'active'
            LIMIT 1
            """
        ).fetchone()
        return row is not None

    def counts(self) -> tuple[int, int]:
        fibers = self.conn.execute("SELECT COUNT(*) AS n FROM fibers").fetchone()["n"]
        neurons = self.conn.execute("SELECT COUNT(*) AS n FROM neurons").fetchone()["n"]
        return int(fibers), int(neurons)

    def ensure_neuron(self, kind: str, content: str, *, pinned: bool = False) -> Neuron:
        key = content_key(content)
        row = self.conn.execute(
            "SELECT * FROM neurons WHERE kind = ? AND content_key = ?",
            (kind, key),
        ).fetchone()
        if row is not None:
            return _neuron(row)
        now = dump_time(self.clock.now())
        neuron = Neuron(
            id=str(uuid4()),
            kind=kind,
            content=content,
            content_key=key,
            pinned=pinned,
            state="active",
            created_at=now,
        )
        self.conn.execute(
            """
            INSERT INTO neurons (id, kind, content, content_key, pinned, state, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                neuron.id,
                neuron.kind,
                neuron.content,
                neuron.content_key,
                int(neuron.pinned),
                neuron.state,
                neuron.created_at,
            ),
        )
        return neuron

    def neuron(self, neuron_id: str) -> Neuron | None:
        row = self.conn.execute("SELECT * FROM neurons WHERE id = ?", (neuron_id,)).fetchone()
        return None if row is None else _neuron(row)

    def neurons(self) -> list[Neuron]:
        rows = self.conn.execute("SELECT * FROM neurons").fetchall()
        return [_neuron(row) for row in rows]

    def find_neurons_contained(self, text: str) -> list[Neuron]:
        found: list[Neuron] = []
        for neuron in self.neurons():
            if neuron.state != "active":
                continue
            if len(neuron.content) >= 2 and neuron.content in text:
                found.append(neuron)
        return found

    def add_synapse(
        self,
        source_id: str,
        target_id: str,
        synapse_type: str,
        *,
        direction: str,
        base_weight: float,
    ) -> Synapse:
        if source_id == target_id:
            raise ValueError("synapse ends must differ")
        row = self.conn.execute(
            """
            SELECT * FROM synapses
            WHERE source_id = ? AND target_id = ? AND type = ?
            """,
            (source_id, target_id, synapse_type),
        ).fetchone()
        if row is not None:
            return self._synapse(row)
        now = dump_time(self.clock.now())
        synapse = Synapse(
            id=str(uuid4()),
            source_id=source_id,
            target_id=target_id,
            type=synapse_type,
            direction=direction,
            base_weight=base_weight,
            weight=base_weight,
            rehearsal_count=0,
            last_activated_at=now,
            decay_cursor=now,
            created_at=now,
        )
        synapse.weight = effective_weight(synapse, self.clock.now())
        self.conn.execute(
            """
            INSERT INTO synapses (
                id, source_id, target_id, type, direction, base_weight, weight,
                rehearsal_count, last_activated_at, decay_cursor, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                synapse.id,
                synapse.source_id,
                synapse.target_id,
                synapse.type,
                synapse.direction,
                synapse.base_weight,
                synapse.weight,
                synapse.rehearsal_count,
                synapse.last_activated_at,
                synapse.decay_cursor,
                synapse.created_at,
            ),
        )
        return synapse

    def synapses(self) -> list[Synapse]:
        rows = self.conn.execute("SELECT * FROM synapses").fetchall()
        return [self._synapse(row) for row in rows]

    def save_synapse(self, synapse: Synapse) -> None:
        self.conn.execute(
            """
            UPDATE synapses
            SET base_weight = ?, weight = ?, rehearsal_count = ?,
                last_activated_at = ?, decay_cursor = ?
            WHERE id = ?
            """,
            (
                synapse.base_weight,
                synapse.weight,
                synapse.rehearsal_count,
                synapse.last_activated_at,
                synapse.decay_cursor,
                synapse.id,
            ),
        )

    def delete_synapse(self, synapse_id: str) -> None:
        self.conn.execute("DELETE FROM fiber_synapses WHERE synapse_id = ?", (synapse_id,))
        self.conn.execute("DELETE FROM synapses WHERE id = ?", (synapse_id,))

    def insert_fiber(self, fiber: Fiber) -> None:
        self.conn.execute(
            """
            INSERT INTO fibers (
                id, anchor_neuron_id, conductivity, base_conductivity, coherence, salience,
                frequency, summary, essence, ghost, body, compression_tier, stage, memory_type,
                priority, tier, state, pinned, time_start, time_end, expires_at, rehearsal_count,
                last_conducted_at, last_activated_at, created_at, decay_cursor, deleted_at,
                provenance, recall_dates, confidence_value, auto_session
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                fiber.id,
                fiber.anchor_neuron_id,
                fiber.conductivity,
                fiber.base_conductivity,
                fiber.coherence,
                fiber.salience,
                fiber.frequency,
                fiber.summary,
                fiber.essence,
                fiber.ghost,
                fiber.body,
                fiber.compression_tier,
                fiber.stage,
                fiber.memory_type,
                fiber.priority,
                fiber.tier,
                fiber.state,
                int(fiber.pinned),
                fiber.time_start,
                fiber.time_end,
                fiber.expires_at,
                fiber.rehearsal_count,
                fiber.last_conducted_at,
                fiber.last_activated_at,
                fiber.created_at,
                fiber.decay_cursor,
                fiber.deleted_at,
                fiber.provenance.model_dump_json(),
                json.dumps(fiber.recall_dates, ensure_ascii=False),
                fiber.confidence_value,
                int(fiber.auto_session),
            ),
        )
        for position, neuron_id in enumerate(fiber.neuron_ids):
            self.conn.execute(
                "INSERT INTO fiber_neurons (fiber_id, position, neuron_id) VALUES (?, ?, ?)",
                (fiber.id, position, neuron_id),
            )
        for synapse_id in fiber.synapse_ids:
            self.conn.execute(
                "INSERT INTO fiber_synapses (fiber_id, synapse_id) VALUES (?, ?)",
                (fiber.id, synapse_id),
            )
        for tag in fiber.tags:
            self.conn.execute(
                "INSERT INTO fiber_tags (fiber_id, tag) VALUES (?, ?)",
                (fiber.id, tag),
            )

    def save_fiber(self, fiber: Fiber) -> None:
        self.conn.execute(
            """
            UPDATE fibers SET
                anchor_neuron_id = ?, conductivity = ?, base_conductivity = ?, coherence = ?,
                salience = ?, frequency = ?, summary = ?, essence = ?, ghost = ?, body = ?,
                compression_tier = ?, stage = ?, memory_type = ?, priority = ?, tier = ?,
                state = ?, pinned = ?, time_start = ?, time_end = ?, expires_at = ?,
                rehearsal_count = ?, last_conducted_at = ?, last_activated_at = ?,
                decay_cursor = ?, deleted_at = ?, provenance = ?, recall_dates = ?,
                confidence_value = ?, auto_session = ?
            WHERE id = ?
            """,
            (
                fiber.anchor_neuron_id,
                fiber.conductivity,
                fiber.base_conductivity,
                fiber.coherence,
                fiber.salience,
                fiber.frequency,
                fiber.summary,
                fiber.essence,
                fiber.ghost,
                fiber.body,
                fiber.compression_tier,
                fiber.stage,
                fiber.memory_type,
                fiber.priority,
                fiber.tier,
                fiber.state,
                int(fiber.pinned),
                fiber.time_start,
                fiber.time_end,
                fiber.expires_at,
                fiber.rehearsal_count,
                fiber.last_conducted_at,
                fiber.last_activated_at,
                fiber.decay_cursor,
                fiber.deleted_at,
                fiber.provenance.model_dump_json(),
                json.dumps(fiber.recall_dates, ensure_ascii=False),
                fiber.confidence_value,
                int(fiber.auto_session),
                fiber.id,
            ),
        )

    def fibers(self) -> list[Fiber]:
        rows = self.conn.execute("SELECT * FROM fibers").fetchall()
        return [self._fiber(row) for row in rows]

    def fiber(self, fiber_id: str) -> Fiber | None:
        row = self.conn.execute("SELECT * FROM fibers WHERE id = ?", (fiber_id,)).fetchone()
        return None if row is None else self._fiber(row)

    def delete_fiber(self, fiber_id: str) -> None:
        self.conn.execute("DELETE FROM fiber_tags WHERE fiber_id = ?", (fiber_id,))
        self.conn.execute("DELETE FROM fiber_synapses WHERE fiber_id = ?", (fiber_id,))
        self.conn.execute("DELETE FROM fiber_neurons WHERE fiber_id = ?", (fiber_id,))
        self.conn.execute("DELETE FROM fibers WHERE id = ?", (fiber_id,))

    def replace_fiber_members(
        self, fiber_id: str, neuron_ids: list[str], synapse_ids: list[str]
    ) -> None:
        self.conn.execute("DELETE FROM fiber_neurons WHERE fiber_id = ?", (fiber_id,))
        self.conn.execute("DELETE FROM fiber_synapses WHERE fiber_id = ?", (fiber_id,))
        for position, neuron_id in enumerate(neuron_ids):
            self.conn.execute(
                "INSERT INTO fiber_neurons (fiber_id, position, neuron_id) VALUES (?, ?, ?)",
                (fiber_id, position, neuron_id),
            )
        for synapse_id in synapse_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO fiber_synapses (fiber_id, synapse_id) VALUES (?, ?)",
                (fiber_id, synapse_id),
            )
        if neuron_ids:
            self.conn.execute(
                "UPDATE fibers SET anchor_neuron_id = ? WHERE id = ?",
                (neuron_ids[0], fiber_id),
            )

    def set_tags(self, fiber_id: str, tags: list[str]) -> None:
        self.conn.execute("DELETE FROM fiber_tags WHERE fiber_id = ?", (fiber_id,))
        for tag in tags:
            self.conn.execute(
                "INSERT INTO fiber_tags (fiber_id, tag) VALUES (?, ?)",
                (fiber_id, tag),
            )

    def link_synapse(self, fiber_id: str, synapse_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO fiber_synapses (fiber_id, synapse_id) VALUES (?, ?)",
            (fiber_id, synapse_id),
        )

    def bump_coactivation(self, left: str, right: str) -> None:
        first, second = sorted((left, right))
        now = dump_time(self.clock.now())
        self.conn.execute(
            """
            INSERT INTO coactivations (neuron_a, neuron_b, count, last_on)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(neuron_a, neuron_b)
            DO UPDATE SET count = count + 1, last_on = excluded.last_on
            """,
            (first, second, now),
        )

    def coactivations(self) -> list[tuple[str, str, int]]:
        rows = self.conn.execute(
            "SELECT neuron_a, neuron_b, count FROM coactivations"
        ).fetchall()
        return [(row["neuron_a"], row["neuron_b"], int(row["count"])) for row in rows]

    def observe_sequence(self, signature: str, day: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO sequence_observations (signature, day) VALUES (?, ?)",
            (signature, day),
        )

    def sequence_days(self, signature: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT day FROM sequence_observations WHERE signature = ? ORDER BY day",
            (signature,),
        ).fetchall()
        return [row["day"] for row in rows]

    def sequence_signatures(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT signature FROM sequence_observations"
        ).fetchall()
        return [row["signature"] for row in rows]

    def add_recall_run(self, neuron_ids: list[str]) -> None:
        run_id = str(uuid4())
        now = dump_time(self.clock.now())
        self.conn.execute(
            "INSERT INTO recall_runs (run_id, created_at) VALUES (?, ?)",
            (run_id, now),
        )
        for neuron_id in set(neuron_ids):
            self.conn.execute(
                "INSERT INTO recall_hits (run_id, neuron_id) VALUES (?, ?)",
                (run_id, neuron_id),
            )

    def recall_hit_sets(self) -> list[set[str]]:
        runs = self.conn.execute("SELECT run_id FROM recall_runs").fetchall()
        sets: list[set[str]] = []
        for run in runs:
            rows = self.conn.execute(
                "SELECT neuron_id FROM recall_hits WHERE run_id = ?",
                (run["run_id"],),
            ).fetchall()
            sets.append({row["neuron_id"] for row in rows})
        return sets

    def search_text(self, needle: str) -> bool:
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        for table, column in (
            ("neurons", "content"),
            ("fibers", "summary"),
            ("fibers", "body"),
            ("fibers", "essence"),
            ("fibers", "ghost"),
        ):
            row = self.conn.execute(
                f"SELECT 1 FROM {table} WHERE {column} LIKE ? ESCAPE '\\' LIMIT 1",
                (like,),
            ).fetchone()
            if row is not None:
                return True
        return False

    def _synapse(self, row: sqlite3.Row) -> Synapse:
        synapse = Synapse(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            type=row["type"],
            direction=row["direction"],
            base_weight=row["base_weight"],
            weight=row["weight"],
            rehearsal_count=row["rehearsal_count"],
            last_activated_at=row["last_activated_at"],
            decay_cursor=row["decay_cursor"],
            created_at=row["created_at"],
        )
        synapse.weight = effective_weight(synapse, self.clock.now())
        return synapse

    def _fiber(self, row: sqlite3.Row) -> Fiber:
        members = self.conn.execute(
            """
            SELECT neuron_id FROM fiber_neurons
            WHERE fiber_id = ? ORDER BY position
            """,
            (row["id"],),
        ).fetchall()
        synapses = self.conn.execute(
            "SELECT synapse_id FROM fiber_synapses WHERE fiber_id = ?",
            (row["id"],),
        ).fetchall()
        tags = self.conn.execute(
            "SELECT tag FROM fiber_tags WHERE fiber_id = ? ORDER BY tag",
            (row["id"],),
        ).fetchall()
        provenance = Provenance.model_validate_json(row["provenance"])
        return Fiber(
            id=row["id"],
            anchor_neuron_id=row["anchor_neuron_id"],
            neuron_ids=[item["neuron_id"] for item in members],
            synapse_ids=[item["synapse_id"] for item in synapses],
            conductivity=row["conductivity"],
            base_conductivity=row["base_conductivity"],
            coherence=row["coherence"],
            salience=row["salience"],
            frequency=row["frequency"],
            summary=row["summary"],
            essence=row["essence"],
            ghost=row["ghost"],
            body=row["body"],
            compression_tier=row["compression_tier"],
            stage=row["stage"],
            memory_type=row["memory_type"],
            priority=row["priority"],
            tier=row["tier"],
            state=row["state"],
            pinned=bool(row["pinned"]),
            time_start=row["time_start"],
            time_end=row["time_end"],
            expires_at=row["expires_at"],
            rehearsal_count=row["rehearsal_count"],
            last_conducted_at=row["last_conducted_at"],
            last_activated_at=row["last_activated_at"],
            created_at=row["created_at"],
            decay_cursor=row["decay_cursor"],
            deleted_at=row["deleted_at"],
            provenance=provenance,
            recall_dates=json.loads(row["recall_dates"]),
            confidence_value=row["confidence_value"],
            tags=[item["tag"] for item in tags],
            auto_session=bool(row["auto_session"]),
        )


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=True)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _neuron(row: sqlite3.Row) -> Neuron:
    return Neuron(
        id=row["id"],
        kind=row["kind"],
        content=row["content"],
        content_key=row["content_key"],
        pinned=bool(row["pinned"]),
        state=row["state"],
        created_at=row["created_at"],
        deleted_at=row["deleted_at"],
    )


def day_key(moment_text: str) -> str:
    return load_time(moment_text).strftime("%Y-%m-%d")
