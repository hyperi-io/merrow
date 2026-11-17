"""Vendor SVG folder -> Iconify JSON icon pack for mermaid.registerIconPacks.

  svg2iconify.py <vendor> <src_dir> <out.json>     vendor: aws | azure | gcp | k8s

Per icon: strip editor metadata and foreign namespaces, inline simple CSS class
rules (a page holds many icons, so a shared `.st1` would recolour its
neighbours), prefix every id so gradients and clip paths cannot collide, and
name it from the vendor's file name. Artwork is never altered.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)
DROP_TAGS = {"title", "desc", "metadata"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def name_for(vendor: str, path: Path, root: Path) -> str | None:
    """Icon key from the vendor's file name, or None to skip the file."""
    stem, rel = path.stem, path.relative_to(root).as_posix()
    if vendor == "aws":
        if "__MACOSX" in rel:
            return None
        m = re.match(r"Arch_(.+)_(16|32|48|64)$", stem)
        if m:
            return slug(m.group(1)) if m.group(2) == "64" else None
        m = re.match(r"Res_(.+)_48_(Light|Dark)$", stem)
        if m:
            return "res-" + slug(m.group(1)) + ("-dark" if m.group(2) == "Dark" else "")
        m = re.match(r"Res_(.+)_48$", stem)
        if m:
            return "res-" + slug(m.group(1))
        m = re.match(r"Arch-Category_(.+)_(16|32|48|64)$", stem)
        if m:
            return "category-" + slug(m.group(1)) if m.group(2) == "64" else None
        if "Architecture-Group-Icons" in rel:
            m = re.match(r"(.+)_32(_Dark)?$", stem)
            return "group-" + slug(m.group(1)) + ("-dark" if m.group(2) else "") if m else None
        return None
    if vendor == "azure":
        m = re.match(r"\d+-icon-service-(.+)$", stem)
        return slug(m.group(1)) if m else slug(stem)
    if vendor == "gcp":
        parts = rel.split("/")
        if "Unique Icons" in parts:
            return slug(parts[parts.index("Unique Icons") + 1])
        if "Category Icons" in parts:
            return "category-" + slug(parts[parts.index("Category Icons") + 1])
        if parts[0].startswith("pkg-google-cloud-legacy-icons"):
            return "legacy-" + slug(path.parent.name)
        return None
    if vendor == "k8s":
        kind = path.parent.name
        return slug(stem) + ("" if kind == "labeled" else "-unlabeled")
    raise SystemExit(f"unknown vendor {vendor}")


def parse_css(text: str) -> tuple[dict[str, dict[str, str]], bool]:
    rules, complex_sel = {}, False
    for sels, body in re.findall(r"([^{}]+)\{([^}]*)\}", text):
        decls = dict((k.strip(), v.strip()) for k, v in (d.split(":", 1) for d in body.split(";") if ":" in d))
        for sel in sels.split(","):
            sel = sel.strip()
            if re.fullmatch(r"\.[\w-]+", sel):
                rules.setdefault(sel[1:], {}).update(decls)
            elif sel:
                complex_sel = True
    return rules, complex_sel


def clean(svg_text: str, key: str) -> tuple[dict, list[str]]:
    notes = []
    root = ET.fromstring(svg_text)
    css = {}
    for st in list(root.iter(f"{{{SVG}}}style")):
        rules, cx = parse_css(st.text or "")
        css.update(rules)
        if cx:
            notes.append("complex-css")
    # drop editor metadata, <style>, and foreign-namespace elements/attributes
    for parent in list(root.iter()):
        for ch in list(parent):
            tag = ch.tag if isinstance(ch.tag, str) else ""
            ns, _, local = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
            if local in DROP_TAGS or local == "style" or (ns and ns != SVG):
                parent.remove(ch)
    for el in root.iter():
        for a in list(el.attrib):
            if a.startswith("{") and not a.startswith(f"{{{XLINK}}}"):
                del el.attrib[a]
        cls = el.attrib.pop("class", None)
        if cls:
            for c in cls.split():
                for k, v in css.get(c, {}).items():
                    el.set(k, v)
    ids = {el.get("id") for el in root.iter() if el.get("id")}
    for el in root.iter():
        if el.get("id"):
            el.set("id", f"{key}-{el.get('id')}")
        for a, v in list(el.attrib.items()):
            if "url(#" in v or (a in ("href", f"{{{XLINK}}}href") and v.startswith("#")):
                el.set(a, re.sub(r"#([^)\s\"']+)", lambda m: "#" + (f"{key}-{m.group(1)}" if m.group(1) in ids else m.group(1)), v))
    vb = root.get("viewBox")
    if vb:
        x, y, w, h = (float(v) for v in vb.replace(",", " ").split())
    else:
        x = y = 0.0
        w, h = (float(re.sub(r"[^\d.]", "", root.get(d, "0"))) for d in ("width", "height"))
        notes.append("no-viewBox")
    body = "".join(ET.tostring(ch, encoding="unicode") for ch in root)
    body = re.sub(r"\s+xmlns(:\w+)?=\"[^\"]+\"", "", body)
    body = re.sub(r">\s+<", "><", body).strip()
    icon = {"body": body, "width": w, "height": h}
    if x or y:
        icon["left"], icon["top"] = x, y
    return icon, notes


def main(vendor: str, src: str, out: str) -> None:
    root = Path(src)
    icons, failed, dup, notes = {}, [], 0, {}
    for p in sorted(root.rglob("*.svg")):
        key = name_for(vendor, p, root)
        if not key:
            continue
        if key in icons:
            dup += 1
            continue
        try:
            icons[key], n = clean(p.read_text(encoding="utf-8", errors="replace"), key)
            for x in n:
                notes[x] = notes.get(x, 0) + 1
        except ET.ParseError as e:
            failed.append((p.name, str(e)))
    pack = {"prefix": vendor, "icons": icons}
    Path(out).write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8", newline="\n")
    print(json.dumps({"vendor": vendor, "icons": len(icons), "duplicates_skipped": dup, "failed": failed, "notes": notes,
                      "bytes": Path(out).stat().st_size}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
