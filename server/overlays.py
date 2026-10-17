"""Elementos do formato viral "isso → nisso → use isso".

Cada elemento é um texto da timeline com um estilo especial. Partes separadas por "|":
- aviso:      "Simulação com IA · não é consulta médica"
- pergunta:   "Qual é a sua profissão?|Sou dermato. Edição com IA funciona pra mim?"
- isso_nisso: "isso|nisso"  (+ imagens de antes/depois em img_a / img_b)
- produto:    "SABONETE FACIAL SUAVE|manhã|noite|sem esfregar"
- rotina:     "SUA ROTINA|Sabonete facial suave|Hidratante|Protetor solar"
- final:      "@seuperfil|me chama no direct"

Aqui ficam o desenho (legenda ASS com formas vetoriais) e as regiões de vidro fosco e de imagem,
que o render.py monta com o ffmpeg. O preview do navegador imita o mesmo layout em CSS.
"""
from pathlib import Path

from . import brand as brandkit

RICH_STYLES = ["aviso", "pergunta", "isso_nisso", "produto", "rotina", "final"]


def parts(text: str) -> list:
    return [p.strip() for p in (text or "").split("|")]


def _t(x: float) -> str:
    x = max(0.0, x)
    return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"


def _c(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def rrect(w: int, h: int, r: int) -> str:
    r = max(1, min(r, w // 2, h // 2))
    return (f"m {r} 0 l {w - r} 0 b {w} 0 {w} 0 {w} {r} l {w} {h - r} b {w} {h} {w} {h} {w - r} {h} "
            f"l {r} {h} b 0 {h} 0 {h} 0 {h - r} l 0 {r} b 0 0 0 0 {r} 0")


def circle(cx: int, cy: int, r: int) -> str:
    k = int(r * 0.552)
    return (f"m {cx} {cy - r} b {cx + k} {cy - r} {cx + r} {cy - k} {cx + r} {cy} "
            f"b {cx + r} {cy + k} {cx + k} {cy + r} {cx} {cy + r} b {cx - k} {cy + r} {cx - r} {cy + k} {cx - r} {cy} "
            f"b {cx - r} {cy - k} {cx - k} {cy - r} {cx} {cy - r}")


def layout(W: int, H: int) -> dict:
    """Caixas em pixels, proporcionais ao vídeo (referência 1080×1920)."""
    u = W / 1080
    v = H / 1920

    def box(x, y, w, h):
        return [int(x * u), int(y * v), int(w * u), int(h * v)]

    side = int(390 * u)
    return {
        "u": u,
        "aviso": box(270, 48, 540, 58),
        "pergunta_head": box(150, 170, 780, 92),
        "pergunta_body": box(150, 262, 780, 210),
        "frame_a": [int(48 * u), int(120 * v), side, side],
        "frame_b": [W - int(48 * u) - side, int(120 * v), side, side],
        "produto": box(140, 1240, 800, 150),
        "chips_y": int(1430 * v),
        "rotina": box(150, 1180, 780, 330),
        "handle_y": int(1880 * v),
    }


def phases(style: str, dur: float, n_parts: int) -> dict:
    """Quando cada pedaço do elemento aparece (segundos desde o início dele)."""
    if style == "isso_nisso":
        a = max(0.35, dur * 0.2)
        b = max(a + 0.5, dur * 0.45)
        return {"frames": 0.0, "a": a, "b": b, "arrow": b + 0.35}
    if style == "produto":
        card = min(0.8, dur * 0.3)
        return {"card": card, "chips": [card + 0.35 + 0.3 * i for i in range(max(0, n_parts - 1))]}
    if style == "rotina":
        n = max(1, n_parts - 1)
        return {"items": [0.15 + 0.2 * i for i in range(n)],
                "checks": [dur * 0.35 + (dur * 0.45) * i / max(1, n - 1 if n > 1 else 1) for i in range(n)]}
    return {}


def regions(elem: dict, W: int, H: int, project_dir: Path) -> tuple[list, list]:
    """(vidros, imagens) que o ffmpeg desenha por baixo da legenda ASS."""
    L = layout(W, H)
    a, b = elem["start"], elem["end"]
    style = elem["style"]
    glass, images = [], []
    r = int(28 * L["u"])
    if style == "isso_nisso":
        ph = phases(style, b - a, 0)
        for key, img_key, t_img in (("frame_a", "img_a", ph["a"]), ("frame_b", "img_b", ph["b"])):
            x, y, w, h = L[key]
            glass.append({"x": x, "y": y, "w": w, "h": h, "r": r, "a": a, "b": b})
            img = elem.get(img_key)
            if img and (project_dir / "assets" / img).exists():
                images.append({"path": project_dir / "assets" / img, "x": x, "y": y, "w": w, "h": h, "r": r,
                               "a": a + t_img, "b": b})
    elif style == "produto":
        x, y, w, h = L["produto"]
        ph = phases(style, b - a, len(parts(elem["text"])))
        glass.append({"x": x, "y": y, "w": w, "h": h, "r": r, "a": a, "b": a + ph["card"] + 0.05})
    elif style == "final":
        glass.append({"x": 0, "y": 0, "w": W, "h": H, "r": 0, "a": a, "b": b, "dim": True})
    return glass, images


def events(elem: dict, W: int, H: int, brand: dict | None = None) -> list:
    b_ = brand or brandkit.load()
    ACC = brandkit.ass_color(b_["colors"]["accent"])
    L = layout(W, H)
    u = L["u"]
    a, b = elem["start"], elem["end"]
    style = elem["style"]
    p = parts(elem["text"])
    out = []

    def ev(layer, t0, t1, tags, body):
        if t1 - t0 > 0.02:
            out.append(f"Dialogue: {layer},{_t(t0)},{_t(t1)},Rich,,0,0,0,,{{{tags}}}{body}")

    def shape(layer, t0, t1, x, y, tags, path):
        ev(layer, t0, t1, rf"\an7\pos({x},{y})\bord0\shad0{tags}\p1", path + r"{\p0}")

    def text(layer, t0, t1, x, y, size, color, tags, body, bold=1):
        ev(layer, t0, t1, rf"\an5\pos({x},{y})\fs{int(size)}\b{bold}\bord0\shad0\c{color}{tags}", _c(body))

    pop = r"\fscx80\fscy80\t(0,180,\fscx103\fscy103)\t(180,260,\fscx100\fscy100)\fad(120,160)"
    white, dark = "&H00FFFFFF", "&H00202020"

    if style == "aviso":
        x, y, w, h = L["aviso"]
        shape(1, a, b, x, y, r"\c&H101010&\1a&H60&\fad(200,200)", rrect(w, h, h // 2))
        text(2, a, b, x + w // 2, y + h // 2, 24 * u, white, r"\fad(200,200)", "ⓘ " + p[0])
    elif style == "pergunta":
        hx, hy, hw, hh = L["pergunta_head"]
        bx, by, bw, bh = L["pergunta_body"]
        r = int(26 * u)
        anim = r"\fad(150,200)\fscx90\fscy90\t(0,200,\fscx100\fscy100)"
        shape(1, a, b, hx, hy, rf"\c&H262626&{anim}", rrect(hw, hh + r, r))
        shape(1, a, b, bx, by, rf"\c&HFFFFFF&{anim}", rrect(bw, bh, r))
        text(2, a, b, hx + hw // 2, hy + hh // 2, 34 * u, white, r"\fad(150,200)", p[0] or "Pergunta")
        if len(p) > 1:
            ev(2, a, b, rf"\an5\pos({bx + bw // 2},{by + bh // 2})\fs{int(46 * u)}\b0\bord0\shad0\c{dark}\q0\fad(150,200)", _c(p[1]))
        _handle(out, a, b, bx + bw - int(10 * u), by + bh + int(50 * u), u, b_, white)
    elif style == "isso_nisso":
        ph = phases(style, b - a, 0)
        labels = [p[0] or "isso", p[1] if len(p) > 1 and p[1] else "nisso"]
        for k, key in enumerate(("frame_a", "frame_b")):
            x, y, w, h = L[key]
            r = int(28 * u)
            t_img = ph["a"] if k == 0 else ph["b"]
            shape(1, a, b, x, y, r"\c&HFFFFFF&\1a&HE6&\fad(200,200)", rrect(w, h, r))  # tinta do vidro
            # rótulo some quando a imagem entra
            text(3, a, a + t_img + (0.25 if elem.get("img_a" if k == 0 else "img_b") else 99), x + w // 2, y + h // 2,
                 40 * u, white, r"\fad(200,150)", labels[k], bold=0)
            # moldura branca: fina no vidro, grossa e brilhante quando a imagem aparece
            ev(4, a, b, rf"\an7\pos({x},{y})\c&HFFFFFF&\1a&HFF&\3c&HFFFFFF&\3a&H70&\bord{max(2, int(3 * u))}\shad0\fad(200,200)\p1",
               rrect(w, h, r) + r"{\p0}")
            ev(5, a + t_img, b, rf"\an7\pos({x},{y})\c&HFFFFFF&\1a&HFF&\3c&HFFFFFF&\bord{max(3, int(7 * u))}\shad0"
               rf"\blur{int(6 * u)}\t(0,500,\blur1)\fad(150,200)\p1", rrect(w, h, r) + r"{\p0}")
            if k == 1:
                # linha de varredura revelando o "depois"
                line_w = max(4, int(6 * u))
                ev(6, a + t_img, a + t_img + 0.55, rf"\an7\move({x},{y},{x + w - line_w},{y},0,550)\c&HFFFFFF&\bord0"
                   rf"\shad0\blur2\fad(0,120)\p1", f"m 0 0 l {line_w} 0 {line_w} {h} 0 {h}" + r"{\p0}")
        # seta entre os quadros
        ax0 = L["frame_a"][0] + L["frame_a"][2] + int(24 * u)
        ax1 = L["frame_b"][0] - int(24 * u)
        ay = L["frame_a"][1] + L["frame_a"][3] // 2
        lw = max(2, int(4 * u))
        length = ax1 - ax0
        head = int(22 * u)
        arrow = (f"m 0 {-lw // 2} l {length - head} {-lw // 2} {length - head} {-head // 2} {length} 0 "
                 f"{length - head} {head // 2} {length - head} {lw // 2} 0 {lw // 2}")
        ev(4, a + ph["arrow"], b, rf"\an7\pos({ax0},{ay})\c&HFFFFFF&\bord0\shad0\clip(0,0,{ax0},{H})"
           rf"\t(0,350,\clip(0,0,{ax1 + 2},{H}))\fad(0,200)\p1", arrow + r"{\p0}")
        ev(5, a + ph["arrow"], b, rf"\an7\pos({ax0},{ay})\c&HFFFFFF&\bord0\shad0\fad(100,200)\p1",
           circle(0, 0, max(4, int(8 * u))) + r"{\p0}")
    elif style == "produto":
        x, y, w, h = L["produto"]
        ph = phases(style, b - a, len(p))
        r = int(30 * u)
        t_card = a + ph["card"]
        # antes do nome: o vidro com "use isso"
        shape(1, a, t_card + 0.05, x, y, r"\c&HFFFFFF&\1a&HE0&\3c&HFFFFFF&\fad(200,100)", rrect(w, h, r))
        ev(2, a, t_card + 0.05, rf"\an7\pos({x},{y})\c&HFFFFFF&\1a&HFF&\3c&HFFFFFF&\3a&H70&\bord{max(2, int(3 * u))}\shad0\fad(200,100)\p1",
           rrect(w, h, r) + r"{\p0}")
        text(3, a, t_card, x + w // 2, y + h // 2, 34 * u, white, r"\alpha&H60&\fad(200,100)", "use isso", bold=0)
        # o card branco com o produto
        shape(1, t_card, b, x, y, rf"\c&HFFFFFF&\1a&H08&{pop}", rrect(w, h, r))
        name = (p[0] or "PRODUTO").upper()
        text(3, t_card, b, x + w // 2, y + h // 2 - int(6 * u), 50 * u, dark, pop, name)
        ul_w = int(min(w * 0.75, len(name) * 30 * u))
        ev(3, t_card + 0.25, b, rf"\an7\pos({x + (w - ul_w) // 2},{y + h - int(36 * u)})\c{ACC}\bord0\shad0"
           rf"\clip(0,0,{x + (w - ul_w) // 2},{H})\t(0,400,\clip(0,0,{x + w},{H}))\fad(0,160)\p1",
           f"m 0 0 l {ul_w} 0 {ul_w} {max(3, int(5 * u))} 0 {max(3, int(5 * u))}" + r"{\p0}")
        chips = [c for c in p[1:] if c][:4]
        if chips:
            cw = [int((len(c) * 17 + 70) * u) for c in chips]
            gap = int(18 * u)
            total = sum(cw) + gap * (len(cw) - 1)
            cx = (W - total) // 2
            ch = int(56 * u)
            for k, c in enumerate(chips):
                t0 = a + ph["chips"][k]
                shape(1, t0, b, cx, L["chips_y"], rf"\c&HFFFFFF&\1a&H10&{pop}", rrect(cw[k], ch, ch // 2))
                text(2, t0, b, cx + cw[k] // 2, L["chips_y"] + ch // 2, 25 * u, dark, pop, "• " + c, bold=0)
                cx += cw[k] + gap
    elif style == "rotina":
        x, y, w, h = L["rotina"]
        items = [i for i in p[1:] if i][:5] or ["Passo 1"]
        h = int((110 + 66 * len(items)) * u)
        ph = phases(style, b - a, len(items) + 1)
        shape(1, a, b, x, y, rf"\c&HFFFFFF&\1a&H0A&{pop}", rrect(w, h, int(28 * u)))
        ev(2, a, b, rf"\an4\pos({x + int(40 * u)},{y + int(52 * u)})\fs{int(26 * u)}\b1\bord0\shad0\c&H808080&\fad(120,160)",
           _c((p[0] or "SUA ROTINA").upper()))
        for k, item in enumerate(items):
            iy = y + int((112 + 66 * k) * u)
            t_item = a + ph["items"][k]
            t_check = a + ph["checks"][k]
            ccx = x + int(58 * u)
            rad = int(17 * u)
            ev(2, t_item, b, rf"\an7\pos(0,0)\c&HFFFFFF&\1a&HFF&\3c&HB0B0B0&\bord{max(2, int(3 * u))}\shad0\fad(150,160)\p1",
               circle(ccx, iy, rad) + r"{\p0}")
            ev(3, t_check, b, rf"\an7\pos(0,0)\c{ACC}\bord0\shad0\fscx40\fscy40\org({ccx},{iy})\t(0,200,\fscx100\fscy100)\fad(0,160)\p1",
               circle(ccx, iy, rad + 1) + r"{\p0}")
            ev(4, t_check + 0.08, b, rf"\an5\pos({ccx},{iy})\fs{int(24 * u)}\b1\bord0\shad0\c&HFFFFFF&\fad(80,160)", "✓")
            ev(2, t_item, b, rf"\an4\pos({x + int(96 * u)},{iy})\fs{int(32 * u)}\b0\bord0\shad0\c{dark}\fad(150,160)"
               rf"\t({int((t_check - t_item) * 1000)},{int((t_check - t_item) * 1000) + 200},\c&H909090&)", _c(item))
    elif style == "final":
        handle = p[0] or b_.get("handle") or ""
        sub = p[1] if len(p) > 1 else ""
        cx, cy = W // 2, int(H * 0.42)
        s = int(150 * u)
        ev(3, a + 0.2, b, rf"\an7\pos({cx - s // 2},{cy - s // 2})\c&HFFFFFF&\1a&HFF&\3c{ACC}\bord{max(4, int(10 * u))}\shad0{pop}\p1",
           rrect(s, s, int(s * 0.28)) + r"{\p0}")
        ev(3, a + 0.2, b, rf"\an7\pos(0,0)\c&HFFFFFF&\1a&HFF&\3c{ACC}\bord{max(4, int(9 * u))}\shad0\fad(120,160)\p1",
           circle(cx, cy, int(s * 0.22)) + r"{\p0}")
        ev(3, a + 0.2, b, rf"\an7\pos(0,0)\c{ACC}\bord0\shad0\fad(120,160)\p1",
           circle(cx + int(s * 0.27), cy - int(s * 0.27), max(3, int(s * 0.05))) + r"{\p0}")
        if handle:
            text(3, a + 0.4, b, cx, cy + int(150 * u), 48 * u, white, r"\fad(200,160)", handle.upper())
        if sub:
            text(3, a + 0.6, b, cx, cy + int(230 * u), 40 * u, white, r"\fad(200,160)\alpha&H30&", sub, bold=0)
    return out


def _handle(out, a, b, x, y, u, brand, color):
    h = brand.get("handle")
    if h:
        out.append(f"Dialogue: 2,{_t(a)},{_t(b)},Rich,,0,0,0,,{{\\an6\\pos({x},{y})\\fs{int(28 * u)}\\b1\\bord0"
                   f"\\shad1\\c{color}\\alpha&H20&\\fad(150,200)}}{_c(h.upper())}")


def ass_style(W: int) -> str:
    # margens laterais = largura dos cards: o texto quebra a linha dentro deles
    m = int(185 * W / 1080)
    return (f"Style: Rich,Inter,{int(40 * W / 1080)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
            f"0,0,0,0,100,100,0,0,1,0,0,5,{m},{m},0,1")


FONTS = Path(__file__).resolve().parent / "fonts"


def ass_filter(ass_name: str, workdir: Path) -> str:
    """Filtro de legenda usando a fonte Inter que vem com o app (o vídeo sai igual em qualquer PC)."""
    import os

    try:
        rel = os.path.relpath(FONTS.resolve(), workdir.resolve()).replace("\\", "/")
    except ValueError:  # outro disco no Windows
        return f"ass={ass_name}"
    return f"ass={ass_name}:fontsdir={rel}" if ":" not in rel else f"ass={ass_name}"


def mask_png(project_dir: Path, w: int, h: int, r: int) -> Path:
    """Máscara de canto arredondado para o vidro e as imagens."""
    from PIL import Image, ImageDraw

    d = project_dir / "masks"
    d.mkdir(exist_ok=True)
    f = d / f"m_{w}x{h}_{r}.png"
    if not f.exists():
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
        img.save(f)
    return f
