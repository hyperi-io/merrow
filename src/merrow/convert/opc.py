"""Open Packaging Conventions: the zip of XML parts PPTX and Visio files are.

A part names its neighbours through `_rels/<part>.rels`. Zip names have no
filesystem, so the `..` in a relationship target is resolved here.
"""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import PurePosixPath

_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


def xml(package: zipfile.ZipFile, part: str) -> ET.Element:
    """Return a part parsed as XML."""
    return ET.fromstring(package.read(part))  # noqa: S314 -- expat refuses entity expansion attacks


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
