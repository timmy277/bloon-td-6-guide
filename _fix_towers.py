#!/usr/bin/env python3
"""Split tower cards by id markers and rebuild clean structure."""
import re
from pathlib import Path

ROOT = Path(__file__).parent

TOWERS = {
    "primary.html": ["dart", "boom", "bomb", "tack", "ice", "glue"],
    "military.html": ["snip", "sub", "buck", "ace", "heli", "mort", "dart2"],
    "magic.html": ["wiz", "super", "ninja", "alch", "druid"],
    "support.html": ["vil", "spike", "farm", "eng", "beast"],
}


def extract_div(html: str, class_name: str) -> str:
    m = re.search(rf'<div class="{class_name}"', html)
    if not m:
        return ""
    pos = m.start()
    depth = 0
    i = pos
    while i < len(html):
        if html.startswith("<div", i):
            depth += 1
            i = html.find(">", i) + 1
        elif html.startswith("</div>", i):
            depth -= 1
            i += 6
            if depth == 0:
                return html[pos:i]
        else:
            i += 1
    return ""


def extract_three_cols(card: str) -> str:
    grid = extract_div(card, "upgrade-grid")
    if not grid:
        return ""
    inner = grid[len('<div class="upgrade-grid">'): -len("</div>")]
    cols = []
    pos = 0
    while len(cols) < 3:
        m = re.search(r'<div class="upgrade-col">', inner[pos:])
        if not m:
            break
        col_start = pos + m.start()
        col = extract_div(inner[col_start:], "upgrade-col")
        if not col:
            break
        if "en-desc" in col:
            cols.append(col)
        pos = col_start + len(col)
    if not cols:
        return ""
    return '<div class="upgrade-grid">\n' + "\n".join(cols) + "\n              </div>"


def remove_orphan_short_block(card: str) -> str:
    """Remove vi-only short tiers between full grid close and skin-block."""
    return re.sub(
        r"(</div>\s*</div>\s*\n)(\s*(?:<div class=\"upgrade-col\">|<div class=\"upgrade-tier\">).*?)(\s*<div class=\"skin-block\">)",
        lambda m: m.group(1) + m.group(3)
        if "en-desc" not in m.group(2)
        or not re.search(
            r'<div class="upgrade-tier">\s*\n\s*<b>T\d</b>\s*<span class="en-name">[^<]+</span\s*>\s*<span class="vi-desc">',
            m.group(2),
        )
        else m.group(0),
        card,
        count=1,
        flags=re.DOTALL,
    )


def rebuild_card(card: str, tid: str) -> str:
    card = remove_orphan_short_block(card)

    header_m = re.search(r'<div class="tower-header".*?</div>\s*', card, re.DOTALL)
    meta = extract_div(card, "tower-meta")
    path_row = extract_div(card, "path-row")
    title_m = re.search(r'<b class="upgrade-block-title">.*?</b>\s*', card, re.DOTALL)
    grid = extract_three_cols(card)
    skin = extract_div(card, "skin-block")
    tail_m = re.search(
        r'<p style="margin-bottom: 8px">.*',
        card,
        re.DOTALL,
    )
    if not all([header_m, meta, path_row, title_m, grid, skin, tail_m]):
        raise ValueError(f"missing parts in tc-{tid}")

    tail = tail_m.group(0)
    # trim tail to close tower-body + tower-card only
    tail = re.sub(
        r"(</div>\s*</div>)\s*<!--.*",
        r"\1",
        tail,
        count=1,
        flags=re.DOTALL,
    )
    if tail.count("<div") - tail.count("</div>") != 2:
        # expect combo/tags divs + tower-body + tower-card closes
        pass

    return (
        f'        <div class="tower-card" id="tc-{tid}">\n'
        f"          {header_m.group(0).strip()}\n"
        f'          <div class="tower-body" id="tb-{tid}">\n'
        f"            {meta}\n"
        f"            {path_row}\n"
        f'            <div class="upgrade-block">\n'
        f"              {title_m.group(0).strip()}\n"
        f"              {grid}\n"
        f"            </div>\n"
        f"            {skin}\n"
        f"            {tail.strip()}\n"
    )


def split_cards(text: str, ids: list[str]) -> dict[str, str]:
    chunks = {}
    for i, tid in enumerate(ids):
        start = text.find(f'id="tc-{tid}"')
        if start < 0:
            continue
        start = text.rfind("<div", 0, start)
        if i + 1 < len(ids):
            end = text.find(f'id="tc-{ids[i+1]}"')
            end = text.rfind("<div", start + 1, end)
        else:
            end = text.find("\n      </div>\n    </main>", start)
        chunks[tid] = text[start:end]
    return chunks


def update_nav(text: str, fname: str) -> str:
    nav = re.search(
        r'<nav aria-label="Điều hướng">.*?</nav>',
        (ROOT / "index.html").read_text(encoding="utf-8"),
        re.DOTALL,
    ).group(0)
    nav = re.sub(r'class="nav-btn active"', 'class="nav-btn"', nav)
    nav = nav.replace(f'href="{fname}"', f'href="{fname}" class="nav-btn active"', 1)
    nav = re.sub(r'class="nav-btn"\s+class="nav-btn active"', 'class="nav-btn active"', nav)
    return re.sub(r'<nav aria-label="Điều hướng">.*?</nav>', nav, text, count=1, flags=re.DOTALL)


def process(fname: str):
    p = ROOT / fname
    text = p.read_text(encoding="utf-8")
    ids = TOWERS[fname]
    chunks = split_cards(text, ids)
    sec = re.search(r'<div class="sec-header">.*?</div>\s*\n', text, re.DOTALL)
    prefix = text[: sec.end()]
    suffix = "\n      </div>\n    </main>" + text[text.find("</main>", text.find("page-content")):]

    rebuilt = []
    for tid in ids:
        if tid not in chunks:
            print(f"  missing tc-{tid}")
            continue
        try:
            rebuilt.append(rebuild_card(chunks[tid], tid))
        except ValueError as e:
            print(f"  {fname} tc-{tid}: {e}")
            rebuilt.append(chunks[tid])

    new_text = prefix + "\n".join(rebuilt) + suffix
    # fix suffix: keep footer from original
    foot_start = text.find("<footer>")
    new_text = prefix + "\n".join(rebuilt) + "\n" + text[text.find("\n      </div>\n    </main>", foot_start - 5000):]
    new_text = update_nav(new_text, fname)
    p.write_text(new_text, encoding="utf-8")

    for tid in ids:
        m = re.search(
            rf'<div class="tower-card" id="tc-{tid}">.*?(?=<div class="tower-card" id="tc-|\n      </div>\s*\n    </main>)',
            new_text,
            re.DOTALL,
        )
        if m:
            ch = m.group(0)
            d = ch.count("<div") - ch.count("</div>")
            nested = len(re.findall(r'<div class="tower-card"', ch)) > 1
            if d != 0 or nested:
                print(f"  {fname} tc-{tid}: div diff={d}, nested={nested}, len={len(ch)}")
    print(f"{fname}: {new_text.count('path-label')} labels, {new_text.count('en-desc')} en-desc")


def main():
    for f in TOWERS:
        process(f)


if __name__ == "__main__":
    main()
