"""Bounded-purpose atomic file replacement; not isolation from same-user processes."""
import os
from pathlib import Path
import shutil
import tempfile


def check_write_path(path):
    """Reject existing links before resolving or writing an application path."""
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked application paths are not supported')
        if part.is_file() and info.st_nlink != 1:
            raise ValueError('Hardlinked application files are not supported')


def atomic_write(path, *, source=None, data=None):
    check_write_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_write_path(path.parent)
    fd, temporary = tempfile.mkstemp(prefix='.lao-write-', dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, 'wb') as output:
            if source is not None:
                with source.open('rb') as input_file:
                    shutil.copyfileobj(input_file, output)
            else:
                output.write(data)
        check_write_path(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
