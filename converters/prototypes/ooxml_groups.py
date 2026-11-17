"""Extract group-box styles from an AWS architecture-icons PPTX slide.

Each group on the deck's Groups slide is a p:grpSp holding a rectangle (the
box: line colour, dash, fill), a text label and a p:pic (the corner icon).
Emits JSON: name, stroke, dash, fill, label colour, icon media path.
"""

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
}
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
R_EMBED = "{%s}embed" % NS["r"]


def theme_colours(z: zipfile.ZipFile) -> dict[str, str]:
    name = next(n for n in z.namelist() if re.match(r"ppt/theme/theme\d+\.xml", n))
    root = ET.fromstring(z.read(name))
    out = {}
    scheme = root.find(".//a:clrScheme", NS)
    for el in scheme:
        tag = el.tag.split("}")[1]
        c = el.find("a:srgbClr", NS)
        s = el.find("a:sysClr", NS)
        out[tag] = c.get("val") if c is not None else (s.get("lastClr") if s is not None else None)
    out["tx1"], out["bg1"], out["tx2"], out["bg2"] = out["dk1"], out["lt1"], out["dk2"], out["lt2"]
    return out


def colour(el, theme):
    if el is None:
        return None
    if el.find("a:noFill", NS) is not None:
        return "none"
    sf = el.find("a:solidFill", NS)
    if sf is None:
        return None
    c = sf.find("a:srgbClr", NS)
    if c is not None:
        return "#" + c.get("val")
    c = sf.find("a:schemeClr", NS)
    if c is not None:
        return "#" + str(theme.get(c.get("val"), c.get("val")))
    return None


def rels(z, slide):
    path = slide.replace("slides/", "slides/_rels/") + ".rels"
    root = ET.fromstring(z.read(path))
    return {r.get("Id"): r.get("Target").replace("../", "ppt/") for r in root.iter(REL_NS + "Relationship")}


def group_record(g, theme, rel):
    if g.tag.endswith("}sp"):
        shapes, pics = [g], []
    else:
        shapes = g.findall("p:sp", NS)
        pics = g.findall(".//p:pic", NS)
        if not pics:
            return None
    box = label = None
    for sp in shapes:
        text = "".join(t.text or "" for t in sp.iter("{%s}t" % NS["a"])).strip()
        sppr = sp.find("p:spPr", NS)
        ln = sppr.find("a:ln", NS) if sppr is not None else None
        if ln is not None and colour(ln, theme) not in (None, "none"):
            box = (sp, text)
        if text:
            label = (sp, text)
    if box is None:
        return None
    sp, btext = box
    sppr = sp.find("p:spPr", NS)
    ln = sppr.find("a:ln", NS)
    dash = ln.find("a:prstDash", NS)
    run = (label[0] if label else sp).find(".//a:rPr", NS)
    blip = None
    if pics:
        blip = pics[0].find(".//asvg:svgBlip", NS)
        if blip is None:
            blip = pics[0].find(".//a:blip", NS)
    w = ln.get("w")
    ppr = sp.find(".//a:pPr", NS)
    descr = sp.find("p:nvSpPr/p:cNvPr", NS).get("descr", "")
    return {
        "name": (label[1] if label else btext),
        "descr": descr.strip(),
        "label_align": (ppr.get("algn") if ppr is not None else None) or "l",
        "stroke": colour(ln, theme),
        "stroke_width_pt": round(int(w) / 12700, 2) if w else None,
        "dash": dash.get("val") if dash is not None else "solid",
        "fill": colour(sppr, theme) or "none",
        "label_colour": colour(run, theme) if run is not None else None,
        "icon": rel.get(blip.get(R_EMBED)) if blip is not None else None,
    }


def main(pptx: str, slide_no: int) -> None:
    z = zipfile.ZipFile(pptx)
    theme = theme_colours(z)
    slide = f"ppt/slides/slide{slide_no}.xml"
    rel = rels(z, slide)
    root = ET.fromstring(z.read(slide))
    out, seen = [], set()
    cands = list(root.iter("{%s}grpSp" % NS["p"])) + list(root.iter("{%s}sp" % NS["p"]))
    for g in cands:
        rec = group_record(g, theme, rel)
        if not rec or not rec["name"] or len(rec["name"]) >= 40:
            continue
        key = (rec["name"], rec["stroke"], rec["dash"])
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
