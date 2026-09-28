#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NoReturn

SPRITE_PATH = Path(__file__).resolve().parents[1] / "app" / "static" / "icons.svg"

DROP_ATTRS = ("class", "id", "style")
CSS_OVERRIDING_ATTRS = (
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
)
ICON_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
DEFAULT_VIEWBOX = "0 0 24 24"
SVG_BLOCK_RE = re.compile(r"<svg\b.*</svg\s*>", re.DOTALL | re.IGNORECASE)
CLIPBOARD_READERS: tuple[tuple[str, ...], ...] = (
    ("wl-paste",),
    ("xclip", "-selection", "clipboard", "-o"),
    ("xsel", "--clipboard", "--output"),
    ("pbpaste",),
)
TYPO_FIXES = str.maketrans(
    {
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "-",
    }
)


def die(message: str) -> NoReturn:
    print(f"erreur: {message}", file=sys.stderr)
    raise SystemExit(1)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def escape_xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def read_clipboard() -> str:
    failures = []
    for cmd in CLIPBOARD_READERS:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, check=False
            )
        except (OSError, subprocess.SubprocessError) as err:
            failures.append(f"{cmd[0]}: {err}")
            continue
        markup = result.stdout.strip()
        if markup:
            return markup
        failures.append(f"{cmd[0]}: {result.stderr.strip() or 'presse-papiers vide'}")
    if failures:
        die("impossible de lire le presse-papiers (" + "; ".join(failures) + ")")
    die(
        "aucun utilitaire de presse-papiers trouvé "
        "(wl-paste, xclip, xsel ou pbpaste) : passe le SVG en argument ou via stdin"
    )


def resolve_markup(arg: str | None) -> tuple[str, str]:
    if arg == "-":
        return sys.stdin.read(), "stdin"
    if arg is not None:
        return arg, "argument"
    if not sys.stdin.isatty():
        return sys.stdin.read(), "stdin"
    return read_clipboard(), "presse-papiers"


def extract_svg(markup: str) -> str:
    cleaned = markup.translate(TYPO_FIXES).strip().strip("`").strip()
    found = SVG_BLOCK_RE.search(cleaned)
    return found.group(0) if found else cleaned


def parse_lucide(markup: str) -> tuple[str, list[ET.Element]]:
    try:
        root = ET.fromstring(extract_svg(markup))
    except ET.ParseError as err:
        die(f"SVG invalide: {err}")
    if local_name(root.tag) != "svg":
        die("l'argument svg doit être un élément <svg>")
    children = [child for child in root if isinstance(child.tag, str)]
    if not children:
        die("<svg> sans contenu à importer")
    return root.get("viewBox") or DEFAULT_VIEWBOX, children


def serialize_element(element: ET.Element) -> str:
    tag = local_name(element.tag)
    attrs = "".join(
        f' {local_name(key)}="{escape_xml(str(value))}"'
        for key, value in element.attrib.items()
        if local_name(key) not in DROP_ATTRS
    )
    children = [child for child in element if isinstance(child.tag, str)]
    text = element.text.strip() if element.text else ""
    if not children and not text:
        return f"<{tag}{attrs}/>"
    inner = text + "".join(serialize_element(child) for child in children)
    return f"<{tag}{attrs}>{inner}</{tag}>"


def render_symbol(icon_id: str, viewBox: str, children: list[ET.Element]) -> str:
    attrs = f' id="{icon_id}" viewBox="{viewBox}"'
    inner = "".join(serialize_element(child) for child in children)
    return f"    <symbol{attrs}>{inner}</symbol>\n"


def shadowing_attrs(elements: list[ET.Element]) -> list[str]:
    found: list[str] = []
    for element in elements:
        if not isinstance(element.tag, str):
            continue
        found.extend(
            f"{local_name(element.tag)}@{local_name(key)}"
            for key in element.attrib
            if local_name(key) in CSS_OVERRIDING_ATTRS
        )
        found.extend(shadowing_attrs(list(element)))
    return found


def find_symbol(text: str, icon_id: str) -> re.Pattern[str]:
    quoted = re.escape(f'id="{icon_id}"')
    return re.compile(
        rf"^    <symbol\b(?=[^>]*{quoted})[^>]*>.*?</symbol>\n?",
        re.DOTALL | re.MULTILINE,
    )


def insert_symbol(text: str, block: str) -> str:
    index = text.rindex("</svg>")
    return text[:index] + block + text[index:]


def update_sprite(path: Path, icon_id: str, block: str) -> bool:
    text = path.read_text(encoding="utf-8")
    pattern = find_symbol(text, icon_id)
    replaced = bool(pattern.search(text))
    if replaced:
        new_text = pattern.sub(lambda _: block, text, count=1)
    else:
        new_text = insert_symbol(text, block)
    try:
        ET.fromstring(new_text)
    except ET.ParseError as err:
        die(f"sprite généré invalide: {err}")
    path.write_text(new_text, encoding="utf-8")
    return replaced


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Ajoute ou remplace un <symbol> dans le sprite app/static/icons.svg "
        "à partir d'un <svg> Lucide copié depuis lucide.dev (presse-papiers par défaut)."
    )
    parser.add_argument("icon_id", help="identifiant du symbole, ex: confort-3")
    parser.add_argument(
        "svg",
        nargs="?",
        default=None,
        help="balisage <svg>...</svg> ; omis = presse-papiers, '-' = stdin",
    )
    parser.add_argument(
        "-c",
        "--clipboard",
        action="store_true",
        help="forcer la lecture du presse-papiers",
    )
    parser.add_argument(
        "--file", type=Path, default=SPRITE_PATH, help=argparse.SUPPRESS
    )
    args = parser.parse_args(argv)

    if not ICON_ID_RE.match(args.icon_id):
        die(f"id d'icône invalide: {args.icon_id!r}")
    if not args.file.is_file():
        die(f"sprite introuvable: {args.file}")
    if args.clipboard and args.svg:
        die("--clipboard est incompatible avec un svg passé en argument")

    if args.clipboard:
        markup, source = read_clipboard(), "presse-papiers"
    else:
        markup, source = resolve_markup(args.svg)
    viewBox, children = parse_lucide(markup)
    block = render_symbol(args.icon_id, viewBox, children)
    replaced = update_sprite(args.file, args.icon_id, block)

    text = args.file.read_text(encoding="utf-8")
    count = len(re.findall(r"<symbol\b", text))
    action = "remplacé" if replaced else "ajouté"
    print(
        f"{action}: {args.icon_id} ({source}, viewBox={viewBox}, "
        f"{count} symboles au total)"
    )

    shadowing = sorted(set(shadowing_attrs(children)))
    if shadowing:
        print(
            f"attention: {', '.join(shadowing)} écrase .icon/.icon-* de app.css",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
