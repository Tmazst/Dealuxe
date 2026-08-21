"""
Backend print-log capture.

Redirects ``sys.stdout`` / ``sys.stderr`` to a Tee so every ``print()`` from
the Flask / gunicorn backend is written BOTH to the console AND to a capped text
file (``print_logs.txt``). The admin dashboard reads the tail of that file and
filters it in the browser.

Install once at app startup (idempotent):

    from services.log_capture import install_print_log_capture
    install_print_log_capture(file_path, max_bytes)
"""
import os
import sys


class _CappedFile:
    """Append-only writer that truncates the file when it exceeds max_bytes."""

    def __init__(self, path, max_bytes=5 * 1024 * 1024):
        self.path = path
        self.max_bytes = max_bytes
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self._fh = open(path, 'a', encoding='utf-8', errors='replace')

    def write(self, data):
        try:
            if os.path.getsize(self.path) > self.max_bytes:
                self._fh.close()
                self._fh = open(self.path, 'w', encoding='utf-8', errors='replace')
            self._fh.write(data)
            self._fh.flush()
        except Exception:
            pass

    def flush(self):
        try:
            self._fh.flush()
        except Exception:
            pass


class _Tee:
    """Duplicate a stream: write to every underlying stream."""

    def __init__(self, *streams):
        self._streams = [s for s in streams if s is not None]

    def write(self, data):
        for stream in self._streams:
            try:
                stream.write(data)
            except Exception:
                pass

    def flush(self):
        for stream in self._streams:
            try:
                stream.flush()
            except Exception:
                pass

    def isatty(self):
        return bool(self._streams and self._streams[0].isatty())

    def fileno(self):
        if self._streams and hasattr(self._streams[0], 'fileno'):
            return self._streams[0].fileno()
        raise OSError('No fileno')

    @property
    def encoding(self):
        return getattr(self._streams[0], 'encoding', 'utf-8') if self._streams else 'utf-8'


_installed = False
_installed_path = None


def install_print_log_capture(file_path=None, max_bytes=None):
    """Redirect stdout/stderr so every backend print() is also written to file.

    Idempotent -- calling twice does not double-wrap the streams. Returns the
    absolute path of the log file.
    """
    global _installed, _installed_path
    if _installed:
        return _installed_path

    path = file_path or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'logs', 'print_logs.txt',
    )
    cap = _CappedFile(path, max_bytes or 5 * 1024 * 1024)
    sys.stdout = _Tee(sys.stdout, cap)
    sys.stderr = _Tee(sys.stderr, cap)
    _installed = True
    _installed_path = path
    return path