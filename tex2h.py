#!/usr/bin/env python3
"""
tex2h.py - Convertit un .tex en doc.h (texte lisible) pour l'app NumWorks "Lecteur TeX".

    python tex2h.py cours.tex                 # écrit doc.h à côté du script
    python tex2h.py cours.tex --ascii         # symboles/accents -> ASCII pur
    python tex2h.py cours.tex --txt apercu.txt  # aperçu du texte converti

Marqueurs internes (premier octet d'une ligne) : 1/2/3 = titres, 4 = formule.
"""
import argparse, os, re, sys, unicodedata

H, M = "\x05", "\x06"           # séparateur de paragraphe / saut de ligne forcé
DOLLAR, LB, RB, BS = "\x0e", "\x0f", "\x10", "\x11"

SYM = {  # nom: (unicode, ascii)
 **{n: (u, n) for n, u in dict(alpha="α", beta="β", gamma="γ", delta="δ", epsilon="ε", varepsilon="ε",
    zeta="ζ", eta="η", theta="θ", vartheta="θ", iota="ι", kappa="κ", lambda_="λ", mu="μ", nu="ν", xi="ξ",
    pi="π", rho="ρ", sigma="σ", tau="τ", phi="φ", varphi="φ", chi="χ", psi="ψ", omega="ω", Gamma="Γ",
    Delta="Δ", Theta="Θ", Lambda="Λ", Xi="Ξ", Pi="Π", Sigma="Σ", Phi="Φ", Psi="Ψ", Omega="Ω").items()},
 "lambda": ("λ", "lambda"),
 "le": ("≤", "<="), "leq": ("≤", "<="), "ge": ("≥", ">="), "geq": ("≥", ">="),
 "neq": ("≠", "!="), "ne": ("≠", "!="), "approx": ("≈", "~="), "equiv": ("≡", "=="), "sim": ("~", "~"),
 "infty": ("∞", "inf"), "to": ("→", "->"), "rightarrow": ("→", "->"), "leftarrow": ("←", "<-"),
 "Rightarrow": ("⇒", "=>"), "implies": ("⇒", "=>"), "Leftrightarrow": ("⇔", "<=>"), "iff": ("⇔", "<=>"),
 "leftrightarrow": ("↔", "<->"), "mapsto": ("↦", "|->"), "pm": ("±", "+-"), "mp": ("∓", "-+"),
 "times": ("×", "x"), "cdot": ("·", "*"), "cdots": ("...", "..."), "ldots": ("...", "..."), "dots": ("...", "..."),
 "in": ("∈", " in "), "notin": ("∉", " notin "), "subset": ("⊂", " c "), "subseteq": ("⊆", " c= "),
 "cup": ("∪", " U "), "cap": ("∩", " n "), "emptyset": ("∅", "{}"), "varnothing": ("∅", "{}"),
 "forall": ("∀", "forall "), "exists": ("∃", "exists "), "nabla": ("∇", "nabla"), "partial": ("∂", "d"),
 "sum": ("Σ", "sum"), "prod": ("Π", "prod"), "int": ("∫", "int"), "iint": ("∬", "int2"), "oint": ("∮", "oint"),
 "neg": ("¬", "not "), "land": ("∧", " and "), "lor": ("∨", " or "), "wedge": ("∧", " and "), "vee": ("∨", " or "),
 "perp": ("⊥", " _|_ "), "parallel": ("∥", "||"), "angle": ("∠", "angle "), "degree": ("°", "deg"),
 "circ": ("∘", "o"), "langle": ("<", "<"), "rangle": (">", ">"), "lfloor": ("⌊", "["), "rfloor": ("⌋", "]"),
 "lceil": ("⌈", "["), "rceil": ("⌉", "]"), "vert": ("|", "|"), "mid": ("|", "|"), "colon": (":", ":"),
 "prime": ("'", "'"), "ell": ("l", "l"), "hbar": ("ħ", "h"), "propto": ("∝", " ~ "), "ll": ("≪", "<<"), "gg": ("≫", ">>"),
 "quad": (" ", " "), "qquad": ("  ", "  "), "bullet": ("•", "*"), "star": ("*", "*"), "ast": ("*", "*"),
 "over": ("/", "/"), "setminus": ("\\", "\\"), "oplus": ("⊕", "(+)"), "otimes": ("⊗", "(x)"),
}
KEEP_ACCENTS = "àâäçéèêëîïôöùûüœÀÂÇÉÈÊ"
TEXT_SUBST = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00ab": '"', "\u00bb": '"',
              "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u00a0": " ", "\u2026": "...", "\ufb01": "fi", "\ufb02": "fl"}

THM_FR = dict(theorem="Théorème", thm="Théorème", lemma="Lemme", lem="Lemme", proposition="Proposition",
    prop="Proposition", corollary="Corollaire", cor="Corollaire", definition="Définition", defn="Définition",
    remark="Remarque", rem="Remarque", example="Exemple", ex="Exemple", proof="Preuve", abstract="Résumé",
    claim="Affirmation", conjecture="Conjecture", notation="Notation", exercise="Exercice", fact="Fait")
THM_EN = dict(theorem="Theorem", thm="Theorem", lemma="Lemma", lem="Lemma", proposition="Proposition",
    prop="Proposition", corollary="Corollary", cor="Corollary", definition="Definition", defn="Definition",
    remark="Remark", rem="Remark", example="Example", ex="Example", proof="Proof", abstract="Abstract",
    claim="Claim", conjecture="Conjecture", notation="Notation", exercise="Exercise", fact="Fact")

# ---------------------------------------------------------------- utilitaires
def grab(s, i):
    """s[i] == '{' -> (contenu, index après l'accolade fermante)"""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{": depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0: return s[i + 1:j], j + 1
    return s[i + 1:], len(s)

def grab_arg(s, i):
    while i < len(s) and s[i] == " ": i += 1
    if i >= len(s): return "", i
    if s[i] == "{": return grab(s, i)
    if s[i] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", s[i:])
        return m.group(0), i + len(m.group(0))
    return s[i], i + 1

def apply_cmd(s, names, fn):
    """Remplace \\name[opt]{arg} par fn(opt, arg), en rescannant le résultat."""
    rx = re.compile(r"\\(?:%s)(?![A-Za-z@])\*?" % "|".join(names))
    pos = 0
    while True:
        m = rx.search(s, pos)
        if not m: return s
        i = m.end(); opt = None; j = i
        while j < len(s) and s[j] == " ": j += 1
        if j < len(s) and s[j] == "[":
            k = s.find("]", j)
            if k != -1: opt, i = s[j + 1:k], k + 1
        arg, i = grab_arg(s, i)
        rep = fn(opt, arg)
        s = s[:m.start()] + rep + s[i:]
        pos = m.start()

def simple(a):
    return re.fullmatch(r"[A-Za-z0-9.]+", a.strip()) is not None

# ---------------------------------------------------------------- maths
def mats(s):
    s = re.sub(r"\\begin\{[pbvVB]?matrix\}(.*?)\\end\{[pbvVB]?matrix\}", lambda m: "[" + "; ".join(
        " ".join(c.strip() for c in r.split("&")) for r in re.split(r"\\\\", m.group(1)) if r.strip()) + "]", s, flags=re.S)
    return re.sub(r"\\begin\{cases\}(.*?)\\end\{cases\}", lambda m: "{ " + "; ".join(
        r.replace("&", ",").strip() for r in re.split(r"\\\\", m.group(1)) if r.strip()) + " }", s, flags=re.S)

def m2t(s, uni):
    s = s.replace("\n", " ")
    s = mats(s)
    s = s.replace("\\{", LB).replace("\\}", RB).replace("\\\\", " ").replace("\\|", "||")
    while True:  # fractions et binomiaux
        m = re.search(r"\\(?:[dt]?frac|binom)(?![A-Za-z])", s)
        if not m: break
        a, i = grab_arg(s, m.end()); b, i = grab_arg(s, i)
        if m.group(0).endswith("binom"):
            rep = "C(%s,%s)" % (a, b)
        else:
            rep = (a if simple(a) else "(" + a + ")") + "/" + (b if simple(b) else "(" + b + ")")
        s = s[:m.start()] + rep + s[i:]
    while True:  # racines
        m = re.search(r"\\sqrt(?![A-Za-z])", s)
        if not m: break
        j = m.end(); opt = None
        if s[j:j + 1] == "[":
            k = s.find("]", j); opt, j = s[j + 1:k], k + 1
        a, i = grab_arg(s, j)
        if opt: rep = (opt + "√(" + a + ")") if uni else "root(%s,%s)" % (opt, a)
        else: rep = ("√(" if uni else "sqrt(") + a + ")"
        s = s[:m.start()] + rep + s[i:]
    for names, fn in (
        (["vec", "overrightarrow"], lambda o, a: "vec(" + a + ")"),
        (["hat", "widehat"], lambda o, a: "hat(" + a + ")"),
        (["bar", "overline"], lambda o, a: "bar(" + a + ")"),
        (["tilde", "widetilde"], lambda o, a: "tilde(" + a + ")"),
        (["dot"], lambda o, a: "dot(" + a + ")"), (["ddot"], lambda o, a: "ddot(" + a + ")"),
        (["mathbb", "mathcal", "mathrm", "mathbf", "mathit", "mathsf", "mathfrak", "text", "textrm", "textbf",
          "textit", "operatorname", "boldsymbol", "bm", "mbox", "underline", "mathscr"], lambda o, a: a)):
        s = apply_cmd(s, names, fn)
    s = apply_cmd(s, ["label", "tag", "nonumber", "notag"], lambda o, a: "")
    s = re.sub(r"\\(?:left|right|displaystyle|textstyle|big|Big|bigg|Bigg|limits|nolimits)(?![A-Za-z])", "", s)
    s = re.sub(r"\\[,;:! ]", " ", s).replace("\\!", "")
    def sym(m):
        e = SYM.get(m.group(1))
        return (e[0] if uni else e[1]) if e else m.group(1)
    s = re.sub(r"\\([A-Za-z]+)\*?", sym, s)
    for ch, fmt in (("^", "^"), ("_", "_")):
        rx = re.compile(re.escape(ch) + r"\{([^{}]*)\}")
        prev = None
        while prev != s:
            prev = s
            s = rx.sub(lambda m: fmt + (m.group(1).strip() if simple(m.group(1)) else "(" + m.group(1).strip() + ")"), s)
    s = s.replace("{", "").replace("}", "").replace(LB, "{").replace(RB, "}").replace("&", " ")
    return re.sub(r" +", " ", s).strip()

def display(s, uni):
    s = apply_cmd(mats(s), ["intertext"], lambda o, a: "")
    rows = [m2t(r, uni) for r in re.split(r"\\\\", s)]
    rows = [r for r in rows if r]
    return H + M.join("\x04" + r for r in rows) + H if rows else ""

# ---------------------------------------------------------------- texte
def fix_accents(s):
    acc = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303"}
    s = re.sub(r"\\([\'`^\"~])\s*\{?\s*(\\i|[A-Za-z])\s*\}?",
               lambda m: unicodedata.normalize("NFC", ("i" if m.group(2) == "\\i" else m.group(2)) + acc[m.group(1)]), s)
    s = re.sub(r"\\c\s*\{?\s*([cC])\s*\}?", lambda m: unicodedata.normalize("NFC", m.group(1) + "\u0327"), s)
    return s.replace("\\ae", "æ").replace("\\oe", "œ").replace("\\ss", "ß")

def convert(src, uni=True):
    src = src.replace("\r", "")
    src = src.replace("\\%", "\x12").replace("\\$", DOLLAR)
    src = re.sub(r"%.*", "", src).replace("\x12", "%")
    def meta(name):
        m = re.search(r"\\%s\s*\{" % name, src)
        return grab(src, m.end() - 1)[0] if m else ""
    t_title, t_author = meta("title"), meta("author")
    french = bool(re.search(r"french|francais|français", src[:src.find("\\begin{document}") if "\\begin{document}" in src else 2000]))
    THM = THM_FR if french else THM_EN
    b = src.find("\\begin{document}")
    if b != -1:
        e = src.rfind("\\end{document}")
        src = src[b + 15:e if e != -1 else len(src)]
    # macros sans argument
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?\s*\{", src):
        d, _ = grab(src, m.end() - 1)
        src = src.replace("\\" + m.group(1) + " ", d + " ")
        src = re.sub(r"\\%s(?![A-Za-z])" % m.group(1), lambda _: d.replace("\\", "\\\\"), src)
    src = re.sub(r"\\(?:re)?newcommand.*?\n", "", src) if False else src
    # maths d'affichage
    envs = "equation|align|gather|multline|eqnarray|displaymath|flalign|math"
    src = re.sub(r"\\begin\{(%s)(\*?)\}(.*?)\\end\{\1\2\}" % envs, lambda m: display(m.group(3), uni), src, flags=re.S)
    src = re.sub(r"\$\$(.*?)\$\$", lambda m: display(m.group(1), uni), src, flags=re.S)
    src = re.sub(r"\\\[(.*?)\\\]", lambda m: display(m.group(1), uni), src, flags=re.S)
    src = re.sub(r"\$(.+?)\$", lambda m: m2t(m.group(1), uni), src, flags=re.S)
    src = re.sub(r"\\\((.*?)\\\)", lambda m: m2t(m.group(1), uni), src, flags=re.S)
    # espaces / paragraphes
    src = re.sub(r"[ \t]*\n[ \t]*\n[\s]*", H, src)
    src = src.replace("\n", " ")
    # titre
    src = re.sub(r"\\maketitle", H + "\x01" + t_title + H + (t_author.replace("\\and", ", ") + H if t_author else ""), src)
    # sections
    has_chap = "\\chapter" in src
    lvl = dict(chapter=0, section=1, subsection=2, subsubsection=3, paragraph=3)
    sty = dict(chapter=1, section=2 if has_chap else 1, subsection=3 if has_chap else 2, subsubsection=3, paragraph=3)
    cnt = [0, 0, 0, 0]
    rx = re.compile(r"\\(chapter|section|subsection|subsubsection|paragraph)(\*?)(?![A-Za-z])")
    pos = 0
    while True:
        m = rx.search(src, pos)
        if not m: break
        i = m.end()
        while i < len(src) and src[i] == " ": i += 1
        if src[i:i + 1] == "[":
            i = src.find("]", i) + 1
        ttl, i = grab_arg(src, i)
        name = m.group(1); label = ""
        if not m.group(2) and name != "paragraph":
            d = lvl[name]; cnt[d] += 1
            for k in range(d + 1, 4): cnt[k] = 0
            first = 0 if has_chap else 1
            label = ".".join(str(c) for c in cnt[first:d + 1]) + " "
        rep = H + chr(sty[name]) + label + ttl + H
        src = src[:m.start()] + rep + src[i:]
        pos = m.start() + len(rep)
    # tableaux
    def table(m):
        rows = [r for r in re.split(r"\\\\", m.group(3)) if r.strip()]
        out = []
        for r in rows:
            r = re.sub(r"\\(hline|cline\{[^}]*\}|toprule|midrule|bottomrule)", "", r)
            cells = [c.strip() for c in r.split("&")]
            if any(cells): out.append(" | ".join(cells))
        return H + M.join(out) + H
    src = re.sub(r"\\begin\{(tabular\*?|array)\}(\{[^{}]*\})?(.*?)\\end\{\1\}", table, src, flags=re.S)
    # listes et environnements
    stack = []
    rx = re.compile(r"\\(begin|end)\{(\w+)\*?\}(\[[^\]]*\])?|\\item(?![A-Za-z])\s*(\[[^\]]*\])?")
    out, pos = [], 0
    for m in rx.finditer(src):
        out.append(src[pos:m.start()]); pos = m.end()
        if m.group(0).startswith("\\item"):
            if not stack: out.append(M + "- "); continue
            kind, n = stack[-1]; ind = "  " * (len(stack) - 1)
            if kind == "enumerate":
                stack[-1][1] += 1; out.append(M + ind + "%d. " % stack[-1][1])
            elif kind == "description" and m.group(4): out.append(M + ind + m.group(4)[1:-1] + ": ")
            else: out.append(M + ind + "- ")
            continue
        be, env, opt = m.group(1), m.group(2), m.group(3)
        if env in ("itemize", "enumerate", "description"):
            if be == "begin": out.append(H if not stack else M); stack.append([env, 0])
            else:
                if stack: stack.pop()
                out.append(H if not stack else M)
        elif env in THM:
            if be == "begin":
                out.append(H + THM[env] + (" (" + opt[1:-1] + ")" if opt else "") + ". ")
            else:
                out.append(" []" + H if env == "proof" else H)
        elif env in ("verbatim", "lstlisting", "center", "figure", "table", "minipage", "flushleft", "flushright",
                     "quote", "quotation", "document", "frame"):
            out.append(H)
            if be == "begin" and env == "minipage":
                nxt = src[pos:]; 
                if nxt.startswith("{"): _, k = grab(nxt, 0); pos += k
        else:
            out.append(H)
    out.append(src[pos:]); src = "".join(out)
    # commandes de texte
    keep = ["textbf", "textit", "emph", "textsc", "texttt", "textrm", "textsf", "underline", "mbox", "text",
            "textnormal", "bfseries", "itshape", "textup", "uppercase", "lowercase", "mathrm"]
    src = apply_cmd(src, keep, lambda o, a: a)
    src = apply_cmd(src, ["footnote"], lambda o, a: " [note: " + a + "]")
    src = apply_cmd(src, ["cite", "citep", "citet"], lambda o, a: "[" + a + "]")
    src = apply_cmd(src, ["ref", "eqref", "autoref", "pageref", "cref"], lambda o, a: "(" + a + ")")
    src = apply_cmd(src, ["url"], lambda o, a: a)
    src = apply_cmd(src, ["caption"], lambda o, a: H + "[" + ("Figure" if True else "") + ": " + a + "]" + H)
    src = apply_cmd(src, ["includegraphics"], lambda o, a: H + "[image: " + a + "]" + H)
    src = apply_cmd(src, ["label", "vspace", "hspace", "usepackage", "documentclass", "bibliographystyle", "bibliography",
                          "setlength", "pagestyle", "thispagestyle", "input", "include", "newtheorem", "geometry",
                          "pagenumbering", "setcounter", "addtocounter", "index", "centering", "linewidth", "title",
                          "author", "date", "hypersetup", "graphicspath", "color", "textcolor", "color"], lambda o, a: "")
    src = re.sub(r"\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}", r"\1", src)
    src = fix_accents(src)
    for a, b in (("\\ldots", "..."), ("\\dots", "..."), ("\\og", '"'), ("\\fg", '"'), ("\\LaTeX", "LaTeX"), ("\\TeX", "TeX"), ("---", "-"),
                 ("--", "-"), ("``", '"'), ("''", '"'), ("~", " "), ("\\&", "&"), ("\\#", "#"), ("\\_", "_"),
                 ("\\{", "{"), ("\\}", "}"), ("\\ ", " "), ("\\,", " "), ("\\;", " "), ("\\!", ""), ("\\quad", " ")):
        src = src.replace(a, b)
    src = re.sub(r"\\(par|newpage|clearpage|pagebreak|tableofcontents|medskip|bigskip|smallskip)(?![A-Za-z])", H, src)
    src = re.sub(r"\\(\\|newline)(\[[^\]]*\])?", M, src)
    src = re.sub(r"\\(noindent|hline|small|large|Large|LARGE|huge|normalsize|footnotesize|tiny|today|indent|relax)(?![A-Za-z])", "", src)
    src = re.sub(r"\\[A-Za-z]+\*?", "", src).replace("\\", "")
    src = src.replace("{", "").replace("}", "").replace(DOLLAR, "$")
    # nettoyage final
    text = src.replace(H, "\n\n").replace(M, "\n")
    lines = []
    for ln in text.split("\n"):
        mk = ""
        if ln and ln[0] in "\x01\x02\x03\x04": mk, ln = ln[0], ln[1:]
        body = re.sub(r" +", " ", ln.strip())
        lead = len(ln) - len(ln.lstrip(" ")) if (not mk and re.match(r"(- |\d+\. )", body)) else 0
        if mk and not body: continue
        lines.append(mk + " " * lead + body)
    res = []
    for ln in lines:
        if ln == "" and (not res or res[-1] == ""): continue
        res.append(ln)
    while res and res[-1] == "": res.pop()
    out = "\n".join(res)
    # caractères
    o = []
    for ch in out:
        ch = TEXT_SUBST.get(ch, ch)
        for c in ch:
            if ord(c) < 128 or (uni and (c in KEEP_ACCENTS or c in "αβγδεζηθικλμνξπρστφχψωΓΔΘΛΞΠΣΦΨΩ≤≥≠≈≡∞→←⇒⇔↔↦±∓×·∈∉⊂⊆∪∩∅∀∃∇∂∫∬∮¬∧∨⊥∥∠°∘⌊⌋⌈⌉∝≪≫•⊕⊗√ħæß")):
                o.append(c)
            else:
                d = unicodedata.normalize("NFD", c)
                base = "".join(x for x in d if ord(x) < 128)
                o.append(base if base else "?")
    return "".join(o), (t_title or "")

def c_escape(s):
    return "".join(chr(b) if (32 <= b < 127 and chr(b) not in '"\\?') else "\\%03o" % b for b in s.encode("utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tex"); ap.add_argument("--ascii", action="store_true")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "doc.h"))
    ap.add_argument("--titre"); ap.add_argument("--txt")
    a = ap.parse_args()
    src = open(a.tex, encoding="utf-8", errors="replace").read()
    text, t = convert(src, not a.ascii)
    title = a.titre or re.sub(r"[\x01-\x06]", "", re.sub(r"\\[A-Za-z]+", "", t)).strip() or os.path.splitext(os.path.basename(a.tex))[0]
    if a.txt: open(a.txt, "w", encoding="utf-8").write(text.replace("\x01", "# ").replace("\x02", "## ").replace("\x03", "### ").replace("\x04", "    "))
    data = text.encode("utf-8")
    with open(a.out, "w") as f:
        f.write("/* genere par tex2h.py */\n#define DOC_LEN %d\n" % len(data))
        f.write('static const char doc_title[] = "%s";\n' % c_escape(title[:40]))
        f.write("static const unsigned char doc_text[] = {\n")
        for i in range(0, len(data), 24):
            f.write(",".join(str(b) for b in data[i:i + 24]) + ",\n")
        f.write("0};\n")
    print("%d octets de texte -> %s" % (len(data), a.out))

if __name__ == "__main__":
    main()
