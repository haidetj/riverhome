#!/usr/bin/env python3
"""
Bake web/index.html + web/data/*.json into a single self-contained web/preview.html.

The display normally fetches its JSON from data/ at runtime (the GitHub Pages path).
That needs a web server and sibling files, so it can't be opened as a lone file or
shipped as a single-file artifact. This injects the current data as
`window.__HD2_DATA__` ahead of the app script — index.html already prefers that
object when present — producing one openable HTML file with the war state frozen in.

    python3 sourcing/build_preview.py        # -> web/preview.html

Regenerate after every `refresh.py` run to snapshot fresh data into the preview.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DATA = WEB / "data"


def main():
    html = (WEB / "index.html").read_text()
    bundle = {
        "planets": json.loads((DATA / "planets.json").read_text()),
        "rules": json.loads((DATA / "rules.json").read_text()),
        "live": json.loads((DATA / "live.json").read_text()) if (DATA / "live.json").exists() else None,
        "mos": json.loads((DATA / "major_orders.json").read_text()) if (DATA / "major_orders.json").exists() else None,
        "meta": json.loads((DATA / "meta.json").read_text()) if (DATA / "meta.json").exists() else {},
    }
    # </ inside JSON would prematurely close the <script>; escape it.
    payload = json.dumps(bundle, ensure_ascii=False).replace("</", "<\\/")
    inject = f'<script>window.__HD2_DATA__={payload};</script>\n<script>\n"use strict";'

    marker = '<script>\n"use strict";'
    if marker not in html:
        raise SystemExit("could not find the app <script> marker in index.html")
    out = html.replace(marker, inject, 1)

    dest = WEB / "preview.html"
    dest.write_text(out)
    kb = len(out.encode("utf-8")) / 1024
    print(f"wrote {dest} ({kb:.0f} KB, self-contained, {len(bundle['planets'])} planets)")


if __name__ == "__main__":
    main()
