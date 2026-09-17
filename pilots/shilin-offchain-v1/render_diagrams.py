"""Render simple, editable SVG counterparts of the Mermaid proposal diagrams."""

from pathlib import Path
from xml.sax.saxutils import escape


STYLE = """<style>
text{font:16px Arial,sans-serif;fill:#17324d} .title{font:bold 23px Arial,sans-serif}
.box{fill:#f5f9fc;stroke:#3b7193;stroke-width:2;rx:12}
.source{fill:#e6f4ed;stroke:#2b8062}.claim{fill:#fff3df;stroke:#a56c19}
.line{fill:none;stroke:#466b83;stroke-width:2.5;marker-end:url(#arrow)}
.dash{fill:none;stroke:#a56c19;stroke-width:2;stroke-dasharray:6 5;marker-end:url(#arrow2)}
.small{font:13px Arial,sans-serif;fill:#526b7c}
</style>"""


def box(x, y, w, h, lines, cls="box"):
    out = [f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}"/>']
    top = y + h / 2 - (len(lines) - 1) * 10
    for i, line in enumerate(lines):
        out.append(f'<text text-anchor="middle" x="{x+w/2}" y="{top+i*20}">{escape(line)}</text>')
    return "\n".join(out)


def line(x1, y1, x2, y2, dash=False):
    return f'<path class="{"dash" if dash else "line"}" d="M{x1},{y1} L{x2},{y2}"/>'


def svg(title, width, height, parts):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">\n'
            f'<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="#466b83"/></marker>'
            f'<marker id="arrow2" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 Z" fill="#a56c19"/></marker></defs>\n'
            f'{STYLE}\n<text class="title" x="36" y="36">{escape(title)}</text>\n' + "\n".join(parts) + "\n</svg>\n")


def render(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    dgp = [
        box(32, 140, 170, 64, ["Creator", "submits details"], "box source"),
        box(250, 140, 170, 64, ["Launchpad", "platform"], "box source"),
        box(470, 62, 175, 64, ["Creation", "transaction/event"]),
        box(690, 62, 175, 64, ["Claire fixed", "chain snapshot"]),
        box(470, 230, 175, 64, ["Metadata URI or", "platform record"]),
        box(690, 230, 175, 64, ["Shilin response", "snapshot + hash"]),
        box(920, 140, 190, 64, ["Typed linkage", "assertion + evidence"], "box claim"),
        line(202,172,250,172), line(420,160,470,105), line(420,185,470,250),
        line(645,94,690,94), line(645,262,690,262),
        line(865,95,920,154), line(865,262,920,190),
        '<text class="small" x="32" y="332">Chain time and retrieval time are separate. Dotted relationships and absent records are explained in the caption.</text>',
    ]
    (out / "dgp.svg").write_text(svg("Off-chain data-generating process", 1140, 355, dgp))
    xs = [35, 315, 595, 875]
    top = ["Claire manifest", "Select creation", "Token queue", "Exact URI/address"]
    bottom = ["Validation report", "Evidence + links", "Parse declarations", "Request + hash"]
    flow = []
    for x, label in zip(xs, top):
        flow.append(box(x, 80, 220, 68, label.split(" ", 1) if label == "Claire manifest" else [label]))
    for x, label in zip(xs, bottom):
        flow.append(box(x, 235, 220, 68, [label], "box claim" if label == "Evidence + links" else "box"))
    for i in range(3):
        flow.append(line(xs[i]+220,114,xs[i+1],114))
    flow.append(line(xs[3]+110,148,xs[3]+110,235))
    for i in range(3,0,-1):
        flow.append(line(xs[i],269,xs[i-1]+220,269))
    flow.append('<text class="small" x="35" y="345">Checks: row counts → request failures → response digests → field pointers → foreign keys and time eligibility.</text>')
    (out / "pipeline.svg").write_text(svg("Reproducible acquisition and integration pipeline", 1140, 370, flow))


if __name__ == "__main__":
    render(Path(__file__).parent / "figures")
