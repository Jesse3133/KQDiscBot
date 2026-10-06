"""Stops two copies of the bot running against the same database.

Two copies would post every reminder twice. The lock is an OS file lock, so
it's released automatically if the process dies, even without cleanup.
Standard library only (the supervisor uses it too).
"""

import os
from pathlib import Path


class AlreadyRunning(Exception):
    pass


class InstanceLock:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._file = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = open(self.path, "a+")  # held open for as long as we hold the lock
        try:
            if os.name == "nt":
                import msvcrt

                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            raise AlreadyRunning(str(self.path)) from None
        self._file = file

    def release(self) -> None:
        if self._file is not None:
            self._file.close()  # closing releases the lock
            self._file = None

    def __enter__(self) -> "InstanceLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
