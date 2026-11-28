"""Open Packaging Conventions: the zip of XML parts PPTX and Visio files are.

A part names its neighbours through `_rels/<part>.rels`. Zip names have no
filesystem, so the `..` in a relationship target is resolved here.
"""

import contextlib
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Generator
from pathlib import PurePosixPath

_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"

# The default cap on one part, the size `limits.member_bytes` caps a download's file at.
MAX_PART_BYTES = 5_000_000


@contextlib.contextmanager
def bad_package(kind: str) -> Generator[None]:
    """Turn what a malformed `kind` package raises into a one-line ValueError."""
    try:
        yield
    except zipfile.BadZipFile as error:
        raise ValueError(f"not a {kind} package: {error}") from error
    except KeyError as error:
        raise ValueError(f"the {kind} package has no part {error}") from error
    except ET.ParseError as error:
        raise ValueError(f"a {kind} part is not XML: {error}") from error


def read(package: zipfile.ZipFile, part: str, limit: int = MAX_PART_BYTES) -> bytes:
    """Return a part's bytes.

    Raises:
        KeyError: The package has no such part.
        ValueError: The part is over `limit` bytes uncompressed.
    """
    size = package.getinfo(part).file_size
    if size > limit:
        raise ValueError(f"{part} is {size} bytes, over the {limit} byte limit")
    return package.read(part)


def xml(package: zipfile.ZipFile, part: str, limit: int = MAX_PART_BYTES) -> ET.Element:
    """Return a part parsed as XML.

    Raises:
        KeyError: The package has no such part.
        ValueError: The part is over `limit` bytes uncompressed.
        xml.etree.ElementTree.ParseError: The part isn't well-formed XML.
    """
    return ET.fromstring(read(package, part, limit))  # noqa: S314 -- expat refuses entity expansion attacks


def resolve(part: str, target: str) -> str:
    """Return the part a relationship `target` names, relative to `part`."""
    if target.startswith("/"):
        return target.lstrip("/")
    resolved: list[str] = []
    for segment in PurePosixPath(part).parent.joinpath(target).parts:
        if segment == "..":
            if resolved:
                resolved.pop()
        elif segment != ".":
            resolved.append(segment)
    return "/".join(resolved)


def relationships(package: zipfile.ZipFile, part: str) -> dict[str, str]:
    """Return a part's relationship ids mapped to the parts they name, or none."""
    path = PurePosixPath(part)
    rels = f"{path.parent}/_rels/{path.name}.rels"
    if rels not in package.namelist():
        return {}
    return {
        rel.get("Id", ""): resolve(part, rel.get("Target", ""))
        for rel in xml(package, rels).iter(_REL)
    }
