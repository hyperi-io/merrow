"""Read the files in a download, whatever it ships as: a directory, zip or tarball.

Every converter selects its files with a regex on the path inside the download,
so a new release that moves or renames folders is a config change, never code.
"""

import re
import tarfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Member:
    """One file in a download.

    Attributes:
        path: The `/`-separated path inside the download.
        data: The bytes, or None when the file is over the size cap and unread.
    """

    path: str
    data: bytes | None


def members(
    source: Path,
    pattern: re.Pattern[str],
    max_bytes: int,
    ignore: re.Pattern[str] | None = None,
) -> Iterator[Member]:
    """Yield every file under `source` whose path matches `pattern`, sorted by path.

    A plain file is one member, named by its file name.

    A path matching `ignore` is left out, such as the `__MACOSX/` resource forks
    a zip made on a Mac carries.

    A file larger than `max_bytes` comes back with no data and is never read, so
    a bad download can't fill memory.

    Raises:
        ValueError: `source` doesn't exist.
    """
    if not source.exists():
        raise ValueError(f"{source} is not a file, directory, zip or tarball")
    if source.is_dir():
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            name = path.relative_to(source).as_posix()
            if _wanted(name, pattern, ignore):
                small = path.stat().st_size <= max_bytes
                yield Member(name, path.read_bytes() if small else None)
    elif zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for info in sorted(archive.infolist(), key=lambda i: i.filename):
                if not info.is_dir() and _wanted(info.filename, pattern, ignore):
                    small = info.file_size <= max_bytes
                    yield Member(info.filename, archive.read(info) if small else None)
    elif tarfile.is_tarfile(source):
        with tarfile.open(source) as archive:
            files = sorted(
                (m for m in archive.getmembers() if m.isfile()), key=lambda m: m.name
            )
            for info in files:
                handle = archive.extractfile(info)
                if handle and _wanted(info.name, pattern, ignore):
                    small = info.size <= max_bytes
                    yield Member(info.name, handle.read() if small else None)
    elif _wanted(source.name, pattern, ignore):
        small = source.stat().st_size <= max_bytes
        yield Member(source.name, source.read_bytes() if small else None)


def _wanted(
    path: str, pattern: re.Pattern[str], ignore: re.Pattern[str] | None
) -> bool:
    return bool(pattern.search(path)) and not (ignore and ignore.search(path))
