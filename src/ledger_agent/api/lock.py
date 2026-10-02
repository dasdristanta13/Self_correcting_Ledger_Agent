"""Exclusive per-data-dir process lock (one server process per LEDGER_DATA_DIR)."""
from __future__ import annotations

import atexit
import os
from pathlib import Path


class DataDirLock:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.path = self.dir / ".ledger.lock"
        self._fh = None

    def acquire(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            raise RuntimeError(f"another ledger-agent process is using {self.dir}") from None
        self._fh = fh
        try:                                    # byte 0 is the locked byte; the pid follows for diagnostics
            fh.seek(1)
            fh.truncate(1)
            fh.write(f"{os.getpid()}\n".encode())
            fh.flush()
        except OSError:
            pass
        atexit.register(self.release)

    def release(self) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            fh.close()
        atexit.unregister(self.release)
