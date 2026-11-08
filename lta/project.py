"""Жизненный цикл проекта LTA: ключ, зашифрованный словарь соответствий.

Каталог проекта (например, my_project.lta/):
  project.json   — метаданные: версия, salt, KDF-параметры, верификатор,
                   схема столбцов (без ПДн).
  mapping.db     — SQLite: псевдоним -> зашифрованное ПДн (AES-256-GCM).
"""
import json
import os
import secrets
import shutil
import sqlite3
import stat
import threading
import time
from pathlib import Path

from . import crypto

PROJECT_EXT = ".lta"
_META_FILE = "project.json"
_MAP_FILE = "mapping.db"

KDF = {"n": crypto.SCRYPT_N, "r": crypto.SCRYPT_R, "p": crypto.SCRYPT_P, "dklen": 32}


class ProjectError(Exception):
    pass


class WrongPassword(ProjectError):
    pass


def _map_key(master: bytes) -> bytes:
    return crypto.hkdf(master, b"mapping")


def _canon_key(master: bytes) -> bytes:
    return crypto.hkdf(master, b"canon-index")


class Project:
    def __init__(self, path: Path, meta: dict, master: bytes):
        self.path = Path(path)
        self.meta = meta
        self.master = master
        self.map_key = _map_key(master)
        self.canon_key = _canon_key(master)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path / _MAP_FILE), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")

    # ----------------------------------------------------------- создание

    @classmethod
    def create(cls, path, password: str):
        path = Path(path)
        if path.exists():
            raise ProjectError(f"Проект уже существует: {path}")
        if len(password) < 8:
            raise ProjectError("Пароль должен содержать минимум 8 символов")
        path.mkdir(parents=True)
        salt = secrets.token_bytes(16)
        master = crypto.derive_master(password, salt)
        meta = {
            "version": 1,
            "app": "LocalTableAnonymizer",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "kdf": KDF,
            "salt": salt.hex(),
            "verifier": crypto.verifier(master),
            "columns": {},  # header -> {mode, prefix, kind}
        }
        (path / _META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        p = cls(path, meta, master)
        p._db.execute(
            """CREATE TABLE IF NOT EXISTS mapping (
                column_id TEXT NOT NULL,
                index_val TEXT NOT NULL,
                canon_hmac TEXT NOT NULL,
                orig_enc BLOB NOT NULL,
                PRIMARY KEY (column_id, index_val)
            )"""
        )
        p._db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_canon ON mapping(column_id, canon_hmac)")
        p._db.commit()
        return p

    @classmethod
    def open(cls, path, password: str):
        path = Path(path)
        meta_path = path / _META_FILE
        if not meta_path.exists():
            raise ProjectError(f"Не найден файл проекта: {meta_path}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        salt = bytes.fromhex(meta["salt"])
        master = crypto.derive_master(password, salt)
        if crypto.verifier(master) != meta["verifier"]:
            raise WrongPassword("Неверный пароль")
        return cls(path, meta, master)

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    # ------------------------------------------------------------ ключ/схема

    def col_key(self, column_id: str) -> bytes:
        return crypto.hkdf(self.master, b"col:" + column_id.encode("utf-8"))

    def set_columns(self, columns: dict):
        with self._lock:
            self.meta["columns"] = columns
            self._save_meta()

    def _save_meta(self):
        (self.path / _META_FILE).write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def change_password(self, old_password: str, new_password: str):
        """Перешифровка словаря новым ключом."""
        if crypto.verifier(crypto.derive_master(old_password, bytes.fromhex(self.meta["salt"]))) != self.meta["verifier"]:
            raise WrongPassword("Текущий пароль неверен")
        if len(new_password) < 8:
            raise ProjectError("Новый пароль должен содержать минимум 8 символов")
        rows = self._db.execute("SELECT column_id, index_val, canon_hmac, orig_enc FROM mapping").fetchall()
        decrypted = [
            (cid, idx, ch, crypto.decrypt(self.map_key, enc)) for cid, idx, ch, enc in rows
        ]
        salt = secrets.token_bytes(16)
        master = crypto.derive_master(new_password, salt)
        self.map_key = _map_key(master)
        self.canon_key = _canon_key(master)
        self.master = master
        self.meta["salt"] = salt.hex()
        self.meta["verifier"] = crypto.verifier(master)
        self._save_meta()
        with self._lock:
            self._db.execute("DELETE FROM mapping")
            self._db.executemany(
                "INSERT INTO mapping(column_id, index_val, canon_hmac, orig_enc) VALUES (?,?,?,?)",
                [(cid, idx, ch, crypto.encrypt(self.map_key, orig)) for cid, idx, ch, orig in decrypted],
            )
            self._db.commit()

    # ------------------------------------------------------------- словарь

    def _canon_hmac(self, column_id: str, canonical: str) -> str:
        return crypto.mac(self.canon_key, f"{column_id}\x00{canonical}")

    def get_or_create_index(self, column_id: str, canonical: str, original: str, prefix: str) -> str:
        """Возвращает псевдоним; при коллизии HMAC — счётчик."""
        h = self._canon_hmac(column_id, canonical)
        with self._lock:
            row = self._db.execute(
                "SELECT index_val FROM mapping WHERE column_id=? AND canon_hmac=?", (column_id, h)
            ).fetchone()
            if row:
                return row[0]
            counter = 0
            while True:
                idx = f"{prefix}_{crypto.index_hmac(self.col_key(column_id), canonical, counter)}"
                row = self._db.execute(
                    "SELECT canon_hmac FROM mapping WHERE column_id=? AND index_val=?", (column_id, idx)
                ).fetchone()
                if row is None:
                    self._db.execute(
                        "INSERT INTO mapping(column_id, index_val, canon_hmac, orig_enc) VALUES (?,?,?,?)",
                        (column_id, idx, h, crypto.encrypt(self.map_key, original.encode("utf-8"))),
                    )
                    self._db.commit()
                    return idx
                if row[0] == h:
                    return idx
                counter += 1

    def lookup_index(self, column_id: str, index_val: str):
        """Псевдоним -> исходное значение (или None, если не найдено)."""
        with self._lock:
            row = self._db.execute(
                "SELECT orig_enc FROM mapping WHERE column_id=? AND index_val=?", (column_id, index_val)
            ).fetchone()
        if row is None:
            return None
        return crypto.decrypt(self.map_key, row[0]).decode("utf-8")

    def stats(self) -> dict:
        with self._lock:
            rows = self._db.execute(
                "SELECT column_id, COUNT(*) FROM mapping GROUP BY column_id"
            ).fetchall()
        return {cid: n for cid, n in rows}

    # ----------------------------------------------------------- уничтожение

    def destroy(self):
        """Криптографическое стирание словаря + удаление проекта."""
        db_path = self.path / _MAP_FILE
        self.close()
        if db_path.exists():
            size = db_path.stat().st_size
            with open(db_path, "r+b") as f:
                f.write(secrets.token_bytes(size))
                f.flush()
                os.fsync(f.fileno())
            os.chmod(db_path, stat.S_IWUSR | stat.S_IRUSR)
        shutil.rmtree(self.path, ignore_errors=True)


def list_projects(root) -> list:
    """Список каталогов-проектов (*.lta) в каталоге данных."""
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and p.name.endswith(PROJECT_EXT))
