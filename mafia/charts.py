"""Static SVG charts for the README and the quality report, built with the standard library only.

Each function takes plain data and returns an SVG string. The charts follow one small design system: thin
marks, 4px rounded data ends, 2px gaps between touching segments, hairline gridlines, text in text colors
(never the data color), a status palette only where a color means good or bad (with an icon and a label), and
gray context with a single blue accent where one result is the point. Light and dark colors are both defined,
and the file switches with the viewer's color scheme. Every chart also carries a text description of its data.
"""
from __future__ import annotations

from html import escape

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'
GOOD, WARN, CRIT = "#0ca30c", "#fab219", "#d03b3b"   # status palette, the same in both modes
STATUS = (("sound", GOOD), ("weak", WARN), ("illogical", CRIT))
CSS = f"""
:root {{ --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7; --accent:#2a78d6; --accent2:#eb6834; --border:rgba(11,11,11,.10); }}
@media (prefers-color-scheme: dark) {{
  :root {{ --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835; --accent:#3987e5; --accent2:#d95926; --border:rgba(255,255,255,.10); }}
}}
text {{ font-family:{FONT}; }}
.h {{ fill:var(--ink); font-size:16px; font-weight:600; }}
.sub {{ fill:var(--ink2); font-size:12.5px; }}
.lab {{ fill:var(--ink); font-size:13px; }}
.lab2 {{ fill:var(--ink2); font-size:12px; }}
.mut {{ fill:var(--muted); font-size:11px; }}
.val {{ fill:var(--ink); font-size:12.5px; font-weight:600; }}
.big {{ fill:var(--ink); font-size:30px; font-weight:600; }}
.grid {{ stroke:var(--grid); stroke-width:1; }}
.axis {{ stroke:var(--axis); stroke-width:1; }}
"""


def _lum(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ink_on(fill: str) -> str:
    """Dark or white text, whichever has the higher contrast on this fill."""
    contrast = lambda a, b: (max(a, b) + 0.05) / (min(a, b) + 0.05)
    return "#0b0b0b" if contrast(_lum(fill), _lum("#0b0b0b")) >= contrast(_lum(fill), 1.0) else "#ffffff"


def _text_w(s: str, size: float) -> float:
    return len(s) * size * 0.56   # a conservative estimate of system sans width


def _head(w: int, h: int, title: str, desc: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">',
        f"<title id=\"t\">{escape(title)}</title><desc id=\"d\">{escape(desc)}</desc>",
        f"<style>{CSS}</style>",
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="var(--surface)" stroke="var(--border)"/>',
    ]


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def _glyph(kind: str, x: float, y: float, stroke: str) -> str:
    """A 14px icon so a status color never carries meaning alone."""
    p = {"sound": "M3 7.5 L6 10.5 L11 4", "weak": "M3.5 7 H10.5", "illogical": "M3.8 3.8 L10.2 10.2 M10.2 3.8 L3.8 10.2"}[kind]
    return f'<path d="{p}" transform="translate({x},{y})" fill="none" stroke="{stroke}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'


def _legend_status(x: float, y: float) -> list[str]:
    out = []
    for name, color in STATUS:
        out.append(f'<rect x="{x}" y="{y}" width="14" height="14" rx="3" fill="{color}"/>')
        out.append(_glyph(name, x, y, ink_on(color)))
        out.append(f'<text class="lab2" x="{x + 20}" y="{y + 11.5}">{name}</text>')
        x += 20 + _text_w(name, 12) + 26
    return out


def kpi_row(tiles: list[dict], title: str, width: int = 760) -> str:
    """Headline numbers. Each tile: label, value, note."""
    n = len(tiles)
    gap = 12
    tw = (width - 2 * 20 - gap * (n - 1)) / n
    h = 152
    desc = title + ". " + " ".join(f"{t['label']}: {t['value']} ({t['note']})." for t in tiles)
    out = _head(width, h, title, desc)
    out.append(f'<text class="h" x="20" y="30">{escape(title)}</text>')
    for i, t in enumerate(tiles):
        x = 20 + i * (tw + gap)
        out.append(f'<rect x="{x:.1f}" y="46" width="{tw:.1f}" height="90" rx="10" fill="none" stroke="var(--grid)"/>')
        out.append(f'<text class="lab2" x="{x + 14:.1f}" y="68">{escape(t["label"])}</text>')
        out.append(f'<text class="big" x="{x + 14:.1f}" y="103">{escape(t["value"])}</text>')
        out.append(f'<text class="mut" x="{x + 14:.1f}" y="124">{escape(t["note"])}</text>')
    out.append("</svg>")
    return "\n".join(out)


def stacked_bars(title: str, subtitle: str, rows: list[dict], width: int = 760) -> str:
    """Share of decisions rated sound, weak, or illogical. Each row: label, n_label, sound, weak, illogical (percent)."""
    x0, x1 = 176, width - 52
    top, pitch, bar_h = 104, 46, 22
    plot_h = pitch * len(rows)
    h = top + plot_h + 38
    X = lambda v: x0 + v / 100 * (x1 - x0)
    desc = title + ". " + " ".join(
        f"{r['label']} ({r['n_label']}): sound {_pct(r['sound'])}, weak {_pct(r['weak'])}, illogical {_pct(r['illogical'])}." for r in rows)
    out = _head(width, h, title, desc)
    out.append(f'<text class="h" x="20" y="30">{escape(title)}</text>')
    out.append(f'<text class="sub" x="20" y="50">{escape(subtitle)}</text>')
    out += _legend_status(20, 66)
    for t in range(0, 101, 25):
        out.append(f'<line class="grid" x1="{X(t):.1f}" y1="{top - 8}" x2="{X(t):.1f}" y2="{top + plot_h}"/>')
        out.append(f'<text class="mut" x="{X(t):.1f}" y="{top + plot_h + 18}" text-anchor="middle">{t}%</text>')
    out.append(f'<line class="axis" x1="{x0}" y1="{top - 8}" x2="{x0}" y2="{top + plot_h}"/>')
    for i, r in enumerate(rows):
        yb = top + i * pitch + (pitch - bar_h) / 2
        out.append(f'<text class="lab" x="20" y="{yb + 10:.1f}">{escape(r["label"])}</text>')
        out.append(f'<text class="mut" x="20" y="{yb + 25:.1f}">{escape(r["n_label"])}</text>')
        cum = 0.0
        segs = [(name, color, r[name] or 0.0) for name, color in STATUS if (r[name] or 0.0) > 0]
        for j, (name, color, v) in enumerate(segs):
            a, b = X(cum) + (1 if j else 0), X(cum + v) - (1 if j < len(segs) - 1 else 0)
            w = max(b - a, 1.0)
            last = j == len(segs) - 1
            rad = min(4.0, w / 2)
            if last:   # square at the baseline side, 4px rounded at the data end
                path = f"M{a:.1f},{yb:.1f} H{a + w - rad:.1f} Q{a + w:.1f},{yb:.1f} {a + w:.1f},{yb + rad:.1f} V{yb + bar_h - rad:.1f} Q{a + w:.1f},{yb + bar_h:.1f} {a + w - rad:.1f},{yb + bar_h:.1f} H{a:.1f} Z"
                out.append(f'<path d="{path}" fill="{color}"><title>{name} {_pct(v)}</title></path>')
            else:
                out.append(f'<rect x="{a:.1f}" y="{yb:.1f}" width="{w:.1f}" height="{bar_h}" fill="{color}"><title>{name} {_pct(v)}</title></rect>')
            label = _pct(v)
            if _text_w(label, 12.5) + 14 <= w:
                out.append(f'<text class="val" x="{a + w / 2:.1f}" y="{yb + 15:.1f}" text-anchor="middle" style="fill:{ink_on(color)}">{label}</text>')
            elif last:   # the label would not fit inside, so it goes outside the bar end
                out.append(f'<text class="val" x="{a + w + 6:.1f}" y="{yb + 15:.1f}">{label}</text>')
            cum += v
    out.append("</svg>")
    return "\n".join(out)


def dumbbell(title: str, subtitle: str, rows: list[dict], width: int = 760, second_label: str = "") -> str:
    """Before and after per item, against chance. Each row: label, before, after, chance (percent).

    A row may also have after2, a second result after the change (another model), drawn as an orange dot.
    """
    second = any("after2" in r for r in rows)
    x0, x1 = 196, width - 150
    top, pitch = 112, 50 if second else 46
    plot_h = pitch * len(rows)
    h = top + plot_h + 38
    vmax = 100
    X = lambda v: x0 + v / vmax * (x1 - x0)
    desc = title + ". " + " ".join(
        f"{r['label']}: {r['before']:.1f}% before, {r['after']:.1f}% after" + (f", {r['after2']:.1f}% for {second_label}" if "after2" in r else "") + f", chance {r['chance']:.1f}%."
        for r in rows)
    out = _head(width, h, title, desc)
    out.append(f'<text class="h" x="20" y="30">{escape(title)}</text>')
    out.append(f'<text class="sub" x="20" y="50">{escape(subtitle)}</text>')
    lx = 20
    entries = [("before", "before the shuffle"), ("after", "after the shuffle")] + ([("after2", second_label)] if second else []) + [("chance", "chance")]
    for kind, text in entries:
        if kind == "before":
            out.append(f'<circle cx="{lx + 6}" cy="73" r="5" fill="var(--muted)" stroke="var(--surface)" stroke-width="2"/>')
        elif kind == "after":
            out.append(f'<circle cx="{lx + 6}" cy="73" r="5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>')
        elif kind == "after2":
            out.append(f'<circle cx="{lx + 6}" cy="73" r="5" fill="var(--accent2)" stroke="var(--surface)" stroke-width="2"/>')
        else:
            out.append(f'<line x1="{lx + 6}" y1="66" x2="{lx + 6}" y2="80" stroke="var(--ink)" stroke-width="2"/>')
        out.append(f'<text class="lab2" x="{lx + 18}" y="77">{escape(text)}</text>')
        lx += 18 + _text_w(text, 12) + 24
    for t in range(0, 101, 25):
        out.append(f'<line class="grid" x1="{X(t):.1f}" y1="{top - 10}" x2="{X(t):.1f}" y2="{top + plot_h}"/>')
        out.append(f'<text class="mut" x="{X(t):.1f}" y="{top + plot_h + 18}" text-anchor="middle">{t}%</text>')
    out.append(f'<line class="axis" x1="{x0}" y1="{top - 10}" x2="{x0}" y2="{top + plot_h}"/>')
    for i, r in enumerate(rows):
        cy = top + i * pitch + pitch / 2 - 4
        out.append(f'<text class="lab" x="20" y="{cy + 4:.1f}">{escape(r["label"])}</text>')
        out.append(f'<line x1="{X(r["before"]):.1f}" y1="{cy:.1f}" x2="{X(r["after"]):.1f}" y2="{cy:.1f}" stroke="var(--muted)" stroke-width="2" stroke-linecap="round"/>')
        out.append(f'<line x1="{X(r["chance"]):.1f}" y1="{cy - 9:.1f}" x2="{X(r["chance"]):.1f}" y2="{cy + 9:.1f}" stroke="var(--ink)" stroke-width="2"><title>chance {r["chance"]:.1f}%</title></line>')
        out.append(f'<circle cx="{X(r["before"]):.1f}" cy="{cy:.1f}" r="5.5" fill="var(--muted)" stroke="var(--surface)" stroke-width="2"><title>before {r["before"]:.1f}%</title></circle>')
        out.append(f'<circle cx="{X(r["after"]):.1f}" cy="{cy:.1f}" r="5.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"><title>after {r["after"]:.1f}%</title></circle>')
        if "after2" in r:
            out.append(f'<circle cx="{X(r["after2"]):.1f}" cy="{cy:.1f}" r="5.5" fill="var(--accent2)" stroke="var(--surface)" stroke-width="2"><title>{escape(second_label)} {r["after2"]:.1f}%</title></circle>')
            out.append(f'<text class="mut" x="{x1 + 22}" y="{cy + 20:.1f}">{escape(second_label)}: {r["after2"]:.0f}%</text>')
        out.append(f'<text class="val" x="{x1 + 22}" y="{cy + 4:.1f}">{r["before"]:.0f}% to {r["after"]:.0f}%</text>')
    out.append("</svg>")
    return "\n".join(out)


def bars_with_range(title: str, subtitle: str, rows: list[dict], highlight: str, note: str, vmax: float = 25, width: int = 760) -> str:
    """Horizontal bars with a 95% range whisker. Each row: key, label, sub, value, lo, hi (percent). The highlighted row is blue."""
    x0, x1 = 196, width - 190
    top, pitch, bar_h = 84, 52, 22
    plot_h = pitch * len(rows)
    h = top + plot_h + 38 + 26
    X = lambda v: x0 + v / vmax * (x1 - x0)
    desc = title + ". " + " ".join(f"{r['label']} ({r['sub']}): {r['value']:.1f}%, 95% range {r['lo']:.1f}% to {r['hi']:.1f}%." for r in rows) + " " + note
    out = _head(width, h, title, desc)
    out.append(f'<text class="h" x="20" y="30">{escape(title)}</text>')
    out.append(f'<text class="sub" x="20" y="50">{escape(subtitle)}</text>')
    for t in range(0, int(vmax) + 1, 5):
        out.append(f'<line class="grid" x1="{X(t):.1f}" y1="{top - 8}" x2="{X(t):.1f}" y2="{top + plot_h}"/>')
        out.append(f'<text class="mut" x="{X(t):.1f}" y="{top + plot_h + 18}" text-anchor="middle">{t}%</text>')
    out.append(f'<line class="axis" x1="{x0}" y1="{top - 8}" x2="{x0}" y2="{top + plot_h}"/>')
    for i, r in enumerate(rows):
        yb = top + i * pitch + (pitch - bar_h) / 2
        cy = yb + bar_h / 2
        fill = "var(--accent)" if r["key"] == highlight else "var(--muted)"
        out.append(f'<text class="lab" x="20" y="{yb + 10:.1f}">{escape(r["label"])}</text>')
        out.append(f'<text class="mut" x="20" y="{yb + 25:.1f}">{escape(r["sub"])}</text>')
        w = X(r["value"]) - x0
        if w >= 1:
            rad = min(4.0, w / 2)
            path = f"M{x0},{yb:.1f} H{x0 + w - rad:.1f} Q{x0 + w:.1f},{yb:.1f} {x0 + w:.1f},{yb + rad:.1f} V{yb + bar_h - rad:.1f} Q{x0 + w:.1f},{yb + bar_h:.1f} {x0 + w - rad:.1f},{yb + bar_h:.1f} H{x0} Z"
            out.append(f'<path d="{path}" fill="{fill}"><title>{r["label"]} {r["value"]:.1f}%</title></path>')
        else:   # a zero is still a result, so it gets a visible marker on the baseline
            out.append(f'<circle cx="{x0}" cy="{cy:.1f}" r="5" fill="{fill}" stroke="var(--surface)" stroke-width="2"><title>{r["label"]} 0.0%</title></circle>')
        lo, hi = X(r["lo"]), X(r["hi"])
        out.append(f'<line x1="{lo:.1f}" y1="{cy:.1f}" x2="{hi:.1f}" y2="{cy:.1f}" stroke="var(--ink2)" stroke-width="1.5"/>')
        for xx in (lo, hi):
            out.append(f'<line x1="{xx:.1f}" y1="{cy - 5:.1f}" x2="{xx:.1f}" y2="{cy + 5:.1f}" stroke="var(--ink2)" stroke-width="1.5"/>')
        out.append(f'<text class="val" x="{hi + 10:.1f}" y="{cy + 4.5:.1f}">{r["value"]:.1f}%</text>')
    out.append(f'<text class="mut" x="20" y="{top + plot_h + 42}">{escape(note)}</text>')
    out.append("</svg>")
    return "\n".join(out)
