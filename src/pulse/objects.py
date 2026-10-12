"""Local immutable objects; compensation is required across this store and PostgreSQL."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

_KEY = re.compile(r"[a-f0-9-]+/[a-f0-9-]+/[a-f0-9]{64}\.json\Z")


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # Anchor newly created root directory entries before accepting durable objects.
        for parent in (self.root, *self.root.parents):
            fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _path(self, key: str) -> Path:
        if not _KEY.fullmatch(key):
            raise ValueError("Invalid object key")
        result = self.root / key
        if not result.resolve().is_relative_to(self.root):
            raise ValueError("Object path escaped root")
        return result

    def put(self, policy_id: str, fetch_id: str, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        key = f"{policy_id}/{fetch_id}/{digest}.json"
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not self.verify(key, digest):
                raise OSError("Existing immutable object has different bytes")
            for directory in (target.parent, target.parent.parent, self.root):
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return key
        fd, temporary = tempfile.mkstemp(prefix=".put-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if not self.verify(key, digest):
                    raise OSError("Concurrent object hash conflict") from None
            # Every newly created directory entry in the hierarchy must be durable.
            for directory in (target.parent, target.parent.parent, self.root):
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            os.unlink(temporary)
        return key

    def read(self, key: str) -> bytes:
        with self._path(key).open("rb") as source:
            data = source.read(4194305)
        if len(data) > 4194304:
            raise OSError("Object exceeds the supported storage budget")
        return data

    def verify(self, key: str, sha256: str) -> bool:
        try:
            return hashlib.sha256(self.read(key)).hexdigest() == sha256
        except (OSError, ValueError):
            return False

    def delete(self, key: str) -> None:
        target = self._path(key)
        target.unlink(missing_ok=True)
        if target.parent.exists():
            fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def keys(self) -> list[str]:
        return sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*.json"))
