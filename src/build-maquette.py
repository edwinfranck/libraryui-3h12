#!/usr/bin/env python3
"""Assemble la maquette 3 H 12 à partir des composants LibraryUI d'origine.

Chaque composant de composants/ garde son CSS d'origine, isolé sous la classe
.lui-<clé> (l'équivalent de l'encapsulation d'Angular). La source
maquette.src.html n'utilise que le markup de ces composants, avec le contenu d'Olla.

    python3 build-maquette.py   ->  _sorties/maquette.html
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPOSANTS = ROOT / "composants"
SORTIE = ROOT / "_sorties"

# Composants affichés en pleine page : on garde leurs règles body/html.
PLEINE_PAGE = {"onb", "cs", "login", "forgot", "reset", "nf"}

# Thème « nuit » : les couleurs claires des composants passent sur la palette sombre.
# Ces composants sont déjà sombres, ou doivent rester clairs (la feuille du PDF).
SANS_NUIT = {"side", "code", "pdf", "cs", "foot"}
PAGE, SURFACE, SURFACE_2, SURFACE_3 = "#070b16", "#0f1627", "#151e34", "#1d2843"
TEXTE, TEXTE_2, TEXTE_3 = "#e8ebf4", "#a3acc2", "#7c869e"
COULEUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\bwhite\b")
PROPS_FOND = ("background", "background-color", "background-image")
PROPS_TEXTE = ("color", "-webkit-text-fill-color", "fill", "caret-color")
PROPS_BORD = ("border", "border-color", "border-top", "border-bottom", "border-left", "border-right",
              "border-top-color", "border-bottom-color", "border-left-color", "border-right-color",
              "outline", "outline-color")


def rgba(c):
    c = c.strip().lower()
    if c == "white":
        return 255, 255, 255, 1.0
    if c.startswith("#"):
        h = c[1:]
        if len(h) in (3, 4):
            h = "".join(x * 2 for x in h)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a
    parts = [p.strip() for p in re.split(r"[,/\s]+", c[c.index("(") + 1:-1]) if p.strip()]
    try:
        r, g, b = (float(p) for p in parts[:3])
        a = float(parts[3].rstrip("%")) / (100 if parts[3].endswith("%") else 1) if len(parts) > 3 else 1.0
    except ValueError:
        return None
    return r, g, b, a


def hsl(r, g, b):
    r, g, b = r / 255, g / 255, b / 255
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0, 0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > .5 else d / (mx + mn)
    h = {r: (g - b) / d % 6, g: (b - r) / d + 2, b: (r - g) / d + 4}[mx] * 60
    return h, s, l


def teinte(h, s, l, a):
    import colorsys
    r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
    return f"rgba({round(r * 255)},{round(g * 255)},{round(b * 255)},{a})"


def nuit_couleur(c, famille, racine):
    v = rgba(c)
    if not v or v[3] < .3:
        return c
    h, s, l = hsl(*v[:3])
    if famille == "fond":
        if s < .15:
            if l > .93:
                return PAGE if racine else SURFACE
            if l > .85:
                return SURFACE_2
            if l > .6:
                return SURFACE_3
            return c
        return teinte(h, max(s, .6), .6, .16) if l > .82 else c
    if famille == "texte":
        if s < .2:
            return TEXTE if l < .3 else TEXTE_2 if l < .55 else TEXTE_3 if l < .75 else c
        return teinte(h, s, .74, 1) if l < .4 else c
    if s < .15:
        return "rgba(255,255,255,.09)" if l > .7 else c
    return teinte(h, max(s, .6), .6, .35) if l > .8 else c


def nuit(selecteurs, corps, portee):
    racine = selecteurs.strip() == portee
    def decl(m):
        prop, val = m.group(1).strip().lower(), m.group(2)
        famille = "fond" if prop in PROPS_FOND else "texte" if prop in PROPS_TEXTE else "bord" if prop in PROPS_BORD else None
        if prop.startswith("--") and COULEUR.search(val):
            # Variable de couleur : on devine son rôle à son nom.
            famille = ("fond" if re.search(r"bg|background|surface|page|card|fill", prop)
                       else "bord" if re.search(r"line|border|divider|stroke", prop) else "texte")
        if not famille:
            return m.group(0)
        return m.group(1) + ":" + COULEUR.sub(lambda c: nuit_couleur(c.group(0), famille, racine), val)
    return re.sub(r"([\w-]+)\s*:([^;]*)", decl, corps)


def css_du_composant(cle):
    fichier = next(COMPOSANTS.glob(f"{cle}--*.html"))
    html = fichier.read_text(encoding="utf-8")
    css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S))
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def blocs(css):
    """Découpe une feuille en (prélude, corps) au premier niveau d'accolades."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        if prelude.startswith("@import") or prelude.startswith("@charset"):
            k = css.find(";", i)
            yield css[i:k + 1].strip(), None
            i = k + 1
            continue
        prof, k = 1, j + 1
        while k < n and prof:
            prof += {"{": 1, "}": -1}.get(css[k], 0)
            k += 1
        yield prelude, css[j + 1:k - 1]
        i = k


def isoler_selecteur(sel, portee, garder_body):
    sel = sel.strip()
    racine = re.match(r"^(html\s+body|html|body|:root|:host)\b(.*)$", sel)
    if racine:
        if not garder_body and racine.group(1) in ("html", "body", "html body") and not racine.group(2).strip():
            return None
        return portee + racine.group(2)
    if sel.startswith("*") or sel.startswith("::"):
        return f"{portee}, {portee} {sel}" if sel == "*" else f"{portee} {sel}"
    return f"{portee} {sel}"


def isoler(css, cle, imports, animations):
    portee = f".lui-{cle}"
    garder_body = cle in PLEINE_PAGE
    sortie = []
    for prelude, corps in blocs(css):
        if corps is None:
            imports.add(prelude)
        elif prelude.startswith("@keyframes") or prelude.startswith("@-webkit-keyframes"):
            nom = prelude.split()[1]
            animations[nom] = f"{nom}--{cle}"
            sortie.append(f"{prelude.split()[0]} {nom}--{cle}{{{corps}}}")
        elif prelude.startswith("@font-face"):
            sortie.append(f"{prelude}{{{corps}}}")
        elif prelude.startswith("@"):
            sortie.append(f"{prelude}{{{isoler(corps, cle, imports, animations)}}}")
        else:
            sels = [s for s in (isoler_selecteur(x, portee, garder_body) for x in prelude.split(",")) if s]
            if sels:
                corps = corps.strip() if cle in SANS_NUIT else nuit(", ".join(sels), corps.strip(), portee)
                sortie.append(f"{', '.join(sels)}{{{corps}}}")
    return "\n".join(sortie)


def renommer_animations(css, animations):
    def remplace(m):
        valeur = m.group(2)
        for ancien, neuf in animations.items():
            valeur = re.sub(rf"(?<![\w-]){re.escape(ancien)}(?![\w-])", neuf, valeur)
        return m.group(1) + valeur
    return re.sub(r"(animation(?:-name)?\s*:)([^;}]*)", remplace, css)


def main():
    source = (ROOT / "maquette.src.html").read_text(encoding="utf-8")
    cles = sorted(set(re.findall(r"\blui-([a-z]+)\b", source)))
    imports, feuilles = set(), []
    for cle in cles:
        animations = {}
        css = isoler(css_du_composant(cle), cle, imports, animations)
        feuilles.append(f"/* ===== {cle} ===== */\n{renommer_animations(css, animations)}")
    bloc = "<style>\n" + "\n".join(sorted(imports)) + "\n" + "\n".join(feuilles) + "\n</style>"
    page = source.replace("<!--LUI-CSS-->", bloc)
    SORTIE.mkdir(exist_ok=True)
    (SORTIE / "maquette.html").write_text(page, encoding="utf-8")
    # Version publique : sans le panneau dev, qui permet de sauter les étapes.
    debut = page.index("/* ===================== panneau dev")
    fin = page.index("/* ===================== démarrage")
    prod = (page[:debut] + page[fin:]).replace('<div id="dev"></div>\n', "")
    (SORTIE / "index.html").write_text(prod, encoding="utf-8")
    print(f"{len(cles)} composants : {', '.join(cles)}")
    print(f"-> {SORTIE / 'maquette.html'} (avec panneau dev)")
    print(f"-> {SORTIE / 'index.html'} (publique)")


if __name__ == "__main__":
    main()
