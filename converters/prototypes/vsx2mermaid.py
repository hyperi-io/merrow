"""Visio VSSX/VSDX/VSTX -> Iconify icons, Mermaid classDefs, Mermaid flowcharts.

  masters <file.vssx> <out_dir> <prefix>   every master -> SVG + Iconify JSON + styles
  page    <file.vsdx> <page_no>            one page -> Mermaid flowchart on stdout

Stdlib only. Coordinates are Visio inches, y up; SVG output flips y.
"""

import base64
import json
import math
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

V = "{http://schemas.microsoft.com/office/visio/2012/main}"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
PATTERN_DASH = {0: None, 1: None, 2: "4 3", 3: "1 2", 4: "4 2 1 2", 9: "8 4", 10: "2 2"}


def num(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


class Pkg:
    def __init__(self, path: str):
        self.z = zipfile.ZipFile(path)
        self.styles = {}
        doc = ET.fromstring(self.z.read("visio/document.xml"))
        for ss in doc.iter(V + "StyleSheet"):
            self.styles[ss.get("ID")] = ss
        self.masters = {}
        self.master_shapes = {}
        self.cur_rels = {}
        self.cur_dir = "visio/masters/"
        if "visio/masters/masters.xml" in self.z.namelist():
            mx = ET.fromstring(self.z.read("visio/masters/masters.xml"))
            rels = self.rels("visio/masters/_rels/masters.xml.rels")
            for m in mx.iter(V + "Master"):
                rel = m.find(V + "Rel")
                t = rels[rel.get(R_ID)]
                target = t.lstrip("/") if t.startswith("/") else "visio/masters/" + t
                self.masters[m.get("ID")] = (m.get("NameU"), target, m)

    def rels(self, path):
        if path not in self.z.namelist():
            return {}
        return {r.get("Id"): r.get("Target") for r in ET.fromstring(self.z.read(path)).iter(REL)}

    def master_root(self, mid):
        name, target, _ = self.masters[mid]
        if mid not in self.master_shapes:
            root = ET.fromstring(self.z.read(target))
            shapes = {s.get("ID"): s for s in root.iter(V + "Shape")}
            self.master_shapes[mid] = (root, shapes, target)
        return self.master_shapes[mid]


def own_cell(el, name):
    for c in el.findall(V + "Cell"):
        if c.get("N") == name:
            return c.get("V")
    return None


def style_cell(pkg, style_id, name, depth=0):
    ss = pkg.styles.get(style_id)
    if ss is None or depth > 8:
        return None
    v = own_cell(ss, name)
    if v is not None:
        return v
    kind = "LineStyle" if name.startswith("Line") or name in ("Rounding", "EndArrow", "BeginArrow") else (
        "FillStyle" if name.startswith("Fill") else "TextStyle")
    parent = ss.get(kind)
    if parent and parent != style_id:
        return style_cell(pkg, parent, name, depth + 1)
    return None


def cell(pkg, shape, name, inherit=None):
    """Own cell, then the master shape's, then the style chain."""
    v = own_cell(shape, name)
    if v is not None:
        return v
    if inherit is not None:
        v = cell(pkg, inherit, name)
        if v is not None:
            return v
    kind = "LineStyle" if name.startswith("Line") or name == "Rounding" else (
        "FillStyle" if name.startswith("Fill") else "TextStyle")
    sid = shape.get(kind)
    return style_cell(pkg, sid, name) if sid else None


def char_colour(shape):
    for sec in shape.findall(V + "Section"):
        if sec.get("N") == "Character":
            for row in sec.findall(V + "Row"):
                v = own_cell(row, "Color")
                if v:
                    return v
    return None


# ---- geometry -------------------------------------------------------------


def nurbs_points(x0, y0, x1, y1, formula, w, h, steps=24):
    """Sample a Visio NURBSTo row: NURBS(knotLast, degree, xType, yType, x,y,knot,weight,...)."""
    m = re.search(r"NURBS\(([^)]*)\)", formula or "")
    if not m:
        return [(x1, y1)]
    vals = [num(v) for v in m.group(1).split(",")]
    knot_last, degree, xt, yt = vals[0], int(vals[1]), vals[2], vals[3]
    rest = vals[4:]
    pts = [(x0, y0, 0.0, 1.0)]
    for i in range(0, len(rest) - 3, 4):
        px, py, k, wt = rest[i:i + 4]
        pts.append((px * w if xt == 0 else px, py * h if yt == 0 else py, k, wt))
    pts.append((x1, y1, knot_last, 1.0))
    ctrl = [(p[0], p[1]) for p in pts]
    weights = [p[3] for p in pts]
    inner = [p[2] for p in pts[:-1]]
    knots = [inner[0]] * degree + inner + [knot_last] * (degree + 1)
    n = len(ctrl) - 1
    if len(knots) != n + degree + 2:
        return [(x1, y1)]
    out = []
    t0, t1 = knots[degree], knots[n + 1]
    for s in range(1, steps + 1):
        t = t0 + (t1 - t0) * s / steps
        k = max(i for i in range(degree, n + 1) if knots[i] <= t) if t < t1 else n
        d = [(ctrl[j][0] * weights[j], ctrl[j][1] * weights[j], weights[j]) for j in range(k - degree, k + 1)]
        for r in range(1, degree + 1):
            for j in range(degree, r - 1, -1):
                i = j + k - degree
                den = knots[i + degree - r + 1] - knots[i]
                a = 0 if den == 0 else (t - knots[i]) / den
                d[j] = tuple((1 - a) * d[j - 1][q] + a * d[j][q] for q in range(3))
        x, y, wt = d[degree]
        out.append((x / wt, y / wt) if wt else (x, y))
    return out


def ellarc(p0, p1, ctrl, angle, ratio):
    """Visio EllipticalArcTo -> SVG arc parameters (rx, ry, rot_deg, large, sweep) in y-up space."""
    ca, sa = math.cos(-angle), math.sin(-angle)

    def tf(p):
        x, y = p[0] * ca - p[1] * sa, p[0] * sa + p[1] * ca
        return (x / ratio if ratio else x, y)

    a, b, c = tf(p0), tf(ctrl), tf(p1)
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    ux = ((a[0] ** 2 + a[1] ** 2) * (b[1] - c[1]) + (b[0] ** 2 + b[1] ** 2) * (c[1] - a[1]) + (c[0] ** 2 + c[1] ** 2) * (a[1] - b[1])) / d
    uy = ((a[0] ** 2 + a[1] ** 2) * (c[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (a[0] - c[0]) + (c[0] ** 2 + c[1] ** 2) * (b[0] - a[0])) / d
    r = math.hypot(a[0] - ux, a[1] - uy)
    ang = lambda p: math.atan2(p[1] - uy, p[0] - ux)
    ta, tb, tc = ang(a), ang(b), ang(c)
    ccw = lambda s, e: (e - s) % (2 * math.pi)
    is_ccw = ccw(ta, tb) < ccw(ta, tc)
    span = ccw(ta, tc) if is_ccw else ccw(tc, ta)
    return (r * ratio, r, math.degrees(angle), int(span > math.pi), int(is_ccw))


def shape_path(shape, inherit, stats):
    """Shape-local geometry -> list of (svg_path_d_in_local_yup, nofill, noline)."""
    w = num(own_cell(shape, "Width") or (own_cell(inherit, "Width") if inherit is not None else None))
    h = num(own_cell(shape, "Height") or (own_cell(inherit, "Height") if inherit is not None else None))
    secs = [s for s in shape.findall(V + "Section") if s.get("N") == "Geometry"]
    if not secs and inherit is not None:
        secs = [s for s in inherit.findall(V + "Section") if s.get("N") == "Geometry"]
    out = []
    for sec in secs:
        if own_cell(sec, "NoShow") == "1":
            continue
        d, cur = [], (0.0, 0.0)
        for row in sec.findall(V + "Row"):
            t = row.get("T")
            g = lambda n: num(own_cell(row, n))
            stats[t] = stats.get(t, 0) + 1
            if t == "MoveTo":
                cur = (g("X"), g("Y")); d.append(("M", cur))
            elif t == "RelMoveTo":
                cur = (g("X") * w, g("Y") * h); d.append(("M", cur))
            elif t == "LineTo":
                cur = (g("X"), g("Y")); d.append(("L", cur))
            elif t == "RelLineTo":
                cur = (g("X") * w, g("Y") * h); d.append(("L", cur))
            elif t == "RelCubBezTo":
                c1 = (g("A") * w, g("B") * h); c2 = (g("C") * w, g("D") * h)
                cur = (g("X") * w, g("Y") * h); d.append(("C", c1, c2, cur))
            elif t == "RelQuadBezTo":
                c1 = (g("A") * w, g("B") * h); cur = (g("X") * w, g("Y") * h); d.append(("Q", c1, cur))
            elif t == "ArcTo":
                end = (g("X"), g("Y")); bow = g("A")
                chord = math.dist(cur, end)
                if abs(bow) < 1e-9 or chord == 0:
                    d.append(("L", end))
                else:
                    r = (chord * chord / 4 + bow * bow) / (2 * abs(bow))
                    d.append(("A", r, r, 0, int(abs(bow) > chord / 2), int(bow > 0), end))
                cur = end
            elif t == "EllipticalArcTo":
                end = (g("X"), g("Y"))
                arc = ellarc(cur, end, (g("A"), g("B")), g("C"), g("D"))
                d.append(("A", *arc, end) if arc else ("L", end)); cur = end
            elif t == "Ellipse":
                cx, cy = g("X"), g("Y")
                rx = math.dist((cx, cy), (g("A"), g("B"))); ry = math.dist((cx, cy), (g("C"), g("D")))
                rot = math.degrees(math.atan2(g("B") - cy, g("A") - cx))
                p0 = (g("A"), g("B")); p1 = (2 * cx - g("A"), 2 * cy - g("B"))
                d += [("M", p0), ("A", rx, ry, rot, 0, 1, p1), ("A", rx, ry, rot, 0, 1, p0), ("Z",)]
            elif t == "NURBSTo":
                f = next((c.get("F") for c in row.findall(V + "Cell") if c.get("N") == "E"), None)
                end = (g("X"), g("Y"))
                for p in nurbs_points(cur[0], cur[1], end[0], end[1], f, w, h):
                    d.append(("L", p))
                cur = end
            elif t == "PolylineTo":
                f = next((c.get("F") for c in row.findall(V + "Cell") if c.get("N") == "A"), "")
                m = re.search(r"POLYLINE\(([^)]*)\)", f or "")
                if m:
                    vals = [num(v) for v in m.group(1).split(",")]
                    xt, yt, rest = vals[0], vals[1], vals[2:]
                    for i in range(0, len(rest) - 1, 2):
                        d.append(("L", (rest[i] * w if xt == 0 else rest[i], rest[i + 1] * h if yt == 0 else rest[i + 1])))
                cur = (g("X"), g("Y")); d.append(("L", cur))
            elif t in ("InfiniteLine", "SplineStart", "SplineKnot"):
                stats["skipped:" + t] = stats.get("skipped:" + t, 0) + 1
        if d:
            out.append((d, own_cell(sec, "NoFill") == "1", own_cell(sec, "NoLine") == "1"))
    return out, w, h


def xform(shape, inherit):
    g = lambda n: num(own_cell(shape, n) if own_cell(shape, n) is not None else (own_cell(inherit, n) if inherit is not None else None))
    return g("PinX"), g("PinY"), g("LocPinX"), g("LocPinY"), g("Angle"), g("FlipX"), g("FlipY")


def apply(pt, tf):
    px, py, lx, ly, ang, fx, fy, w, h = tf
    x, y = pt
    if fx:
        x = w - x
    if fy:
        y = h - y
    x, y = x - lx, y - ly
    ca, sa = math.cos(ang), math.sin(ang)
    return (px + x * ca - y * sa, py + x * sa + y * ca)


def colour(v):
    if not v or v in ("Themed", "0"):
        return None
    if v.startswith("#"):
        return v.upper()
    return None


def render(pkg, shape, chain, stats, inherit_map, parent_ins=None):
    """Recursively render a shape (and group children) to SVG elements in the root frame."""
    inherit = inherit_map(shape)
    elems = []
    geo, w, h = shape_path(shape, inherit, stats)
    tf = (*xform(shape, inherit), w, h)
    tfs = chain + [tf]

    def full(p):
        for t in reversed(tfs):
            p = apply(p, t)
        return p

    line = colour(cell(pkg, shape, "LineColor", inherit)) or "#000000"
    fill = colour(cell(pkg, shape, "FillForegnd", inherit)) or "#FFFFFF"
    weight = num(cell(pkg, shape, "LineWeight", inherit), 0.01) * 72
    pattern = int(num(cell(pkg, shape, "LinePattern", inherit), 1))
    fill_pattern = int(num(cell(pkg, shape, "FillPattern", inherit), 1))
    merged = {}  # Visio fills a shape's overlapping geometry sections even-odd, so one path per paint
    for d, nofill, noline in geo:
        parts = []
        for seg in d:
            op = seg[0]
            if op in ("M", "L"):
                x, y = full(seg[1]); parts.append(f"{op}{x:.4f} {y:.4f}")
            elif op == "C":
                pts = [full(p) for p in seg[1:]]
                parts.append("C" + " ".join(f"{x:.4f} {y:.4f}" for x, y in pts))
            elif op == "Q":
                pts = [full(p) for p in seg[1:]]
                parts.append("Q" + " ".join(f"{x:.4f} {y:.4f}" for x, y in pts))
            elif op == "A":
                rx, ry, rot, large, sweep, end = seg[1:]
                x, y = full(end)
                parts.append(f"A{rx:.4f} {ry:.4f} {rot:.2f} {large} {sweep} {x:.4f} {y:.4f}")
            elif op == "Z":
                parts.append("Z")
        f = "none" if (nofill or fill_pattern == 0) else fill
        s = "none" if (noline or pattern == 0) else line
        dash = PATTERN_DASH.get(pattern)
        attrs = f'fill="{f}" stroke="{s}"' + (f' stroke-width="{weight / 72:.4f}"' if s != "none" else "")
        if dash and s != "none":
            attrs += f' stroke-dasharray="{" ".join(str(float(x) / 72 * weight) for x in dash.split())}"'
        merged.setdefault(attrs, []).extend(parts)
    for attrs, parts in merged.items():
        elems.append(f'<path d="{" ".join(parts)}" {attrs} fill-rule="evenodd"/>')
    fd = shape.find(V + "ForeignData")
    if fd is None and inherit is not None:
        fd = inherit.find(V + "ForeignData")
    if fd is not None:
        ftype = fd.get("ForeignType", "?")
        stats["foreign:" + ftype] = stats.get("foreign:" + ftype, 0) + 1
        rel = fd.find(V + "Rel")
        tgt = pkg.cur_rels.get(rel.get(R_ID)) if rel is not None else None
        mime = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(fd.get("CompressionType", ""), None)
        if tgt and mime:
            path = tgt.lstrip("/") if tgt.startswith("/") else str(Path(pkg.cur_dir, tgt)).replace("\\", "/")
            path = re.sub(r"[^/]+/\.\./", "", path)
            data = base64.b64encode(pkg.z.read(path)).decode()
            (x0, y0), (x1, y1) = full((0, 0)), full((w, h))
            xa, ya = min(x0, x1), min(y0, y1)
            elems.append(f'<image x="{xa:.4f}" y="{ya:.4f}" width="{abs(x1 - x0):.4f}" height="{abs(y1 - y0):.4f}" '
                         f'transform="translate(0 {2 * ya + abs(y1 - y0):.4f}) scale(1 -1)" href="data:{mime};base64,{data}"/>')
        else:
            stats["foreign-unrendered:" + ftype] = stats.get("foreign-unrendered:" + ftype, 0) + 1
    kids = shape.find(V + "Shapes")
    if kids is not None:
        for k in kids.findall(V + "Shape"):
            elems += render(pkg, k, tfs, stats, inherit_map)
    return elems


# ---- commands -------------------------------------------------------------


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def masters_cmd(path, out_dir, prefix):
    pkg = Pkg(path)
    out = Path(out_dir)
    (out / "svg").mkdir(parents=True, exist_ok=True)
    icons, styles, stats, failed = {}, {}, {}, []
    for mid, (name, target, meta) in pkg.masters.items():
        try:
            root, shapes, target = pkg.master_root(mid)
            pkg.cur_rels = pkg.rels(target.replace("masters/", "masters/_rels/") + ".rels")
            top = root.find(V + "Shapes").findall(V + "Shape")
            elems = []
            for s in top:
                elems += render(pkg, s, [], stats, lambda sh: None)
            if not elems:
                failed.append((name, "no geometry"))
                continue
            xs, ys = [], []
            for e in elems:
                if e.startswith("<path"):
                    d = e.split('d="')[1].split('"')[0]
                    for seg in re.findall(r"[MLCQ]([^MLCQAZ]*)", d):
                        v = [float(x) for x in seg.split()]
                        xs += v[0::2]; ys += v[1::2]
                    for seg in re.findall(r"A([^MLCQAZ]*)", d):
                        v = [float(x) for x in seg.split()]
                        xs.append(v[5]); ys.append(v[6])
                else:
                    g = {k: float(v) for k, v in re.findall(r' (x|y|width|height)="([-\d.]+)"', e)}
                    xs += [g["x"], g["x"] + g["width"]]; ys += [g["y"], g["y"] + g["height"]]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            pad = 0.02
            wv, hv = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
            body = f'<g transform="translate({pad - x0:.4f} {y1 + pad:.4f}) scale(1 -1)">' + "".join(elems) + "</g>"
            key = slug(name)
            icons[key] = {"body": body, "width": round(wv, 4), "height": round(hv, 4)}
            (out / "svg" / f"{key}.svg").write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {wv:.4f} {hv:.4f}" width="{wv * 96:.0f}" height="{hv * 96:.0f}">{body}</svg>',
                encoding="utf-8", newline="\n")
            s0 = top[0]
            styles[key] = {
                "name": name,
                "line": colour(cell(pkg, s0, "LineColor")),
                "fill": colour(cell(pkg, s0, "FillForegnd")),
                "pattern": cell(pkg, s0, "LinePattern"),
                "weight_pt": round(num(cell(pkg, s0, "LineWeight")) * 72, 2),
                "rounding_in": num(cell(pkg, s0, "Rounding")),
                "text": colour(char_colour(s0)),
                "type": s0.get("Type"),
            }
        except Exception as e:  # noqa: BLE001 -- a prototype reports every failure, never stops on one
            failed.append((name, repr(e)[:120]))
    pack = {"prefix": prefix, "icons": icons}
    (out / f"{prefix}.json").write_text(json.dumps(pack), encoding="utf-8", newline="\n")
    (out / f"{prefix}-styles.json").write_text(json.dumps(styles, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({"masters": len(pkg.masters), "icons": len(icons), "failed": failed[:10], "n_failed": len(failed), "rows": stats}, indent=1))


def page_cmd(path, page_no):
    pkg = Pkg(path)
    rels = pkg.rels("visio/pages/_rels/pages.xml.rels")
    pages = ET.fromstring(pkg.z.read("visio/pages/pages.xml")).findall(V + "Page")
    pg = pages[int(page_no) - 1]
    target = "visio/pages/" + rels[pg.find(V + "Rel").get(R_ID)]
    root = ET.fromstring(pkg.z.read(target))
    shapes = root.find(V + "Shapes").findall(V + "Shape")

    def master_of(sh):
        mid = sh.get("Master")
        if mid and mid in pkg.masters:
            _, mshapes, _ = pkg.master_root(mid)
            mroot = pkg.master_root(mid)[0].find(V + "Shapes").findall(V + "Shape")
            return mroot[0] if mroot else None
        return None

    def text(sh):
        t = sh.find(V + "Text")
        if t is None and master_of(sh) is not None:
            t = master_of(sh).find(V + "Text")
        return re.sub(r"\s+", " ", "".join(t.itertext())).strip() if t is not None else ""

    nodes, conns, ends, labels = {}, [], {}, {}
    for sh in shapes:
        sid = sh.get("ID")
        mname = pkg.masters.get(sh.get("Master"), ("", None, None))[0] or ""
        is_conn = own_cell(sh, "BeginX") is not None and own_cell(sh, "EndX") is not None
        if is_conn or "connector" in mname.lower():
            conns.append(sid)
            ends[sid] = tuple(num(own_cell(sh, c)) for c in ("BeginX", "BeginY", "EndX", "EndY"))
            labels[sid] = text(sh)
            continue
        inh = master_of(sh)
        px, py, lx, ly, *_ = xform(sh, inh)
        w = num(own_cell(sh, "Width") or (own_cell(inh, "Width") if inh is not None else 0))
        h = num(own_cell(sh, "Height") or (own_cell(inh, "Height") if inh is not None else 0))
        nodes[sid] = {
            "label": text(sh) or mname or f"shape {sid}", "master": mname,
            "box": (px - lx, py - ly, px - lx + w, py - ly + h),
            "line": colour(cell(pkg, sh, "LineColor", inh)), "fill": colour(cell(pkg, sh, "FillForegnd", inh)),
            "pattern": cell(pkg, sh, "LinePattern", inh),
        }
    edges = {}
    connects = root.find(V + "Connects")
    for c in (connects.findall(V + "Connect") if connects is not None else []):
        f, t, cellname = c.get("FromSheet"), c.get("ToSheet"), c.get("FromCell")
        if f in conns:
            edges.setdefault(f, {})["src" if cellname == "BeginX" else "dst"] = t
    # unglued connectors (template pages ship them free-floating): snap each end to the
    # smallest node box within 0.15 in of it
    def snap(x, y, tol=0.15):
        hits = [((b[2] - b[0]) * (b[3] - b[1]), k) for k, n in nodes.items() for b in [n["box"]]
                if b[0] - tol <= x <= b[2] + tol and b[1] - tol <= y <= b[3] + tol]
        return min(hits)[1] if hits else None

    inferred = 0
    for cid, (bx, by, ex, ey) in ends.items():
        if cid in edges and len(edges[cid]) == 2:
            continue
        a, b = snap(bx, by), snap(ex, ey)
        if a and b and a != b:
            edges[cid] = {"src": a, "dst": b}
            inferred += 1
    # containment: a node whose box sits inside a larger labelled node is its child
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    inside = lambda a, b: a[0] >= b[0] - 1e-6 and a[1] >= b[1] - 1e-6 and a[2] <= b[2] + 1e-6 and a[3] <= b[3] + 1e-6
    parent = {}
    for k, n in nodes.items():
        cands = [(area(m["box"]), j) for j, m in nodes.items() if j != k and area(m["box"]) > area(n["box"]) and inside(n["box"], m["box"])]
        if cands:
            parent[k] = min(cands)[1]
    has_kids = set(parent.values())
    lines = ["flowchart LR"]

    def emit(k, ind):
        n = nodes[k]
        lab = n["label"].replace('"', "'")[:60]
        kids = [j for j, p in parent.items() if p == k]
        if k in has_kids:
            lines.append(f'{ind}subgraph s{k}["{lab}"]')
            for j in kids:
                emit(j, ind + "  ")
            lines.append(f"{ind}end")
        else:
            lines.append(f'{ind}n{k}["{lab}"]')

    for k in nodes:
        if k not in parent:
            emit(k, "  ")
    for cid, e in edges.items():
        if "src" in e and "dst" in e:
            a = ("s" if e["src"] in has_kids else "n") + e["src"]
            b = ("s" if e["dst"] in has_kids else "n") + e["dst"]
            lab = labels.get(cid, "").replace('"', "'")
            lines.append(f'  {a} -->|"{lab}"| {b}' if lab else f"  {a} --> {b}")
    for k, n in nodes.items():
        st = []
        if n["fill"]:
            st.append(f"fill:{n['fill']}")
        if n["line"]:
            st.append(f"stroke:{n['line']}")
        if n["pattern"] and n["pattern"] not in ("0", "1"):
            st.append("stroke-dasharray:4 3")
        if st:
            lines.append(f"  style {'s' if k in has_kids else 'n'}{k} {','.join(st)}")
    print("\n".join(lines))
    print(f"%% page {page_no} '{pg.get('NameU')}': nodes={len(nodes)} connectors={len(conns)} glued={sum(1 for e in edges.values() if len(e) == 2) - inferred} inferred={inferred} containers={len(has_kids)}", file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1] == "masters":
        masters_cmd(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "page":
        page_cmd(sys.argv[2], sys.argv[3])
