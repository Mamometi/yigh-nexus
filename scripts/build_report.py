"""Build the self-contained report.html (and slides.html when present) by embedding every screenshot as base64.

    python -m scripts.build_report
"""
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report"


def embed(src: Path, out: Path) -> None:
    html = src.read_text()

    def img(m):
        f = SRC / "img" / f"{m.group(1)}.jpg"
        return "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()
    html = re.sub(r"\{\{IMG:([\w-]+)\}\}", img, html)
    if "{{DIAGRAM}}" in html:  # the agent diagram is kept once, in the report source
        rep = (SRC / "report_source.html").read_text()
        svg = rep[rep.index('<svg viewBox="0 0 720 300"'):rep.index("</svg>") + 6].replace("<svg ", '<svg class="diagram" ', 1)
        html = html.replace("{{DIAGRAM}}", svg)
    out.write_text(html)
    print(f"wrote {out.name} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    embed(SRC / "report_source.html", ROOT / "report.html")
    if (SRC / "slides_source.html").exists():
        embed(SRC / "slides_source.html", ROOT / "slides.html")
