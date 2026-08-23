from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import TypeVar

from pydantic import BaseModel

from .models import Deployment, Project, RegressionRun, Workflow, WorkflowVersion


ModelT = TypeVar("ModelT", bound=BaseModel)


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, body TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS webhooks (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, deployment_version TEXT, body TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )

    def save(self, kind: str, model: BaseModel) -> None:
        body = model.model_dump_json()
        created = str(getattr(model, "created_at", ""))
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO records(kind, id, body, created_at) VALUES (?, ?, ?, ?)",
                (kind, str(getattr(model, "id")), body, created),
            )

    def get(self, kind: str, item_id: str, model: type[ModelT]) -> ModelT | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT body FROM records WHERE kind = ? AND id = ?", (kind, item_id)
            ).fetchone()
        return model.model_validate_json(row["body"]) if row else None

    def list(self, kind: str, model: type[ModelT]) -> list[ModelT]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT body FROM records WHERE kind = ? ORDER BY created_at DESC", (kind,)
            ).fetchall()
        return [model.model_validate_json(row["body"]) for row in rows]

    def projects(self) -> list[Project]:
        return self.list("project", Project)

    def deployments(self) -> list[Deployment]:
        return self.list("deployment", Deployment)

    def workflows(self) -> list[Workflow]:
        return self.list("workflow", Workflow)

    def versions(self) -> list[WorkflowVersion]:
        return self.list("workflow_version", WorkflowVersion)

    def runs(self) -> list[RegressionRun]:
        return self.list("run", RegressionRun)

    def event(self, run_id: str, event: dict) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO events(run_id, body) VALUES (?, ?)",
                (run_id, json.dumps(event, default=str)),
            )
            return int(cursor.lastrowid)

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT sequence, body FROM events WHERE run_id = ? AND sequence > ? ORDER BY sequence",
                (run_id, after),
            ).fetchall()
        return [{"sequence": row["sequence"], **json.loads(row["body"])} for row in rows]

    def webhook(self, run_id: str, deployment_version: str, body: dict) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO webhooks(run_id, deployment_version, body) VALUES (?, ?, ?)",
                (run_id, deployment_version, json.dumps(body)),
            )
            return int(cursor.lastrowid)

    def webhooks(self, run_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, deployment_version, body, created_at FROM webhooks WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "deployment_version": row["deployment_version"],
                "created_at": row["created_at"],
                **json.loads(row["body"]),
            }
            for row in rows
        ]

    def latest_passing_run(self, workflow_version_id: str, before_id: str) -> RegressionRun | None:
        for run in self.runs():
            if run.id != before_id and run.workflow_version_id == workflow_version_id and run.gate and run.gate.status == "PASS":
                return run
        return None

