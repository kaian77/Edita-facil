"""Kit da marca: cores, logo, avatar, voz e jeito de falar. Fica salvo e é usado em tudo."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BRAND_DIR = DATA / "brand"
BRAND_FILE = DATA / "brand.json"
BRAND_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT = {
    "name": "",
    "handle": "",
    "niche": "",
    "audience": "",
    "tone": "próximo, direto e confiante",
    "cta": "",
    "colors": {"primary": "#ff6b3d", "secondary": "#6d5cf6", "accent": "#ffd700", "text": "#ffffff"},
    "logo": None,
    "avatar": None,
    "avatar_desc": "",
    "voice_id": "",
    "voice_name": "",
    "watermark": True,
}

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def load() -> dict:
    data = json.loads(json.dumps(DEFAULT))
    if BRAND_FILE.exists():
        saved = json.loads(BRAND_FILE.read_text(encoding="utf-8"))
        colors = {**data["colors"], **saved.get("colors", {})}
        data.update(saved)
        data["colors"] = colors
    return data


def save(changes: dict) -> dict:
    data = load()
    for key, value in changes.items():
        if key == "colors":
            for name, color in (value or {}).items():
                if name in data["colors"] and HEX.match(color or ""):
                    data["colors"][name] = color.lower()
        elif key in DEFAULT and key not in ("logo", "avatar"):
            data[key] = value.strip()[:300] if isinstance(value, str) else value
    BRAND_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def save_image(kind: str, raw: bytes) -> dict:
    """Guarda logo/avatar como PNG. O avatar ganha também uma versão redonda."""
    from io import BytesIO

    from PIL import Image, ImageDraw, ImageOps

    img = ImageOps.exif_transpose(Image.open(BytesIO(raw))).convert("RGBA")
    img.thumbnail((1200, 1200))
    img.save(BRAND_DIR / f"{kind}.png")
    if kind == "avatar":
        side = min(img.size)
        sq = ImageOps.fit(img, (side, side))
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, side - 1, side - 1), fill=255)
        sq.putalpha(mask)
        sq.save(BRAND_DIR / "avatar_round.png")
    data = load()
    data[kind] = f"{kind}.png"
    BRAND_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def path(kind: str) -> Path | None:
    f = BRAND_DIR / f"{kind}.png"
    return f if f.exists() else None


def ass_color(hex_color: str, alpha: str = "00") -> str:
    """#RRGGBB -> &HAABBGGRR (formato das legendas ASS)."""
    h = hex_color.lstrip("#")
    return f"&H{alpha}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def prompt_block(data: dict | None = None) -> str:
    """Resumo da marca para a IA usar como referência."""
    b = data or load()
    parts = []
    if b["name"]:
        parts.append(f"Marca/nome: {b['name']}" + (f" ({b['handle']})" if b["handle"] else ""))
    if b["niche"]:
        parts.append(f"Nicho: {b['niche']}")
    if b["audience"]:
        parts.append(f"Público: {b['audience']}")
    if b["tone"]:
        parts.append(f"Tom de voz: {b['tone']}")
    if b["cta"]:
        parts.append(f"Chamada final preferida: {b['cta']}")
    if b["avatar_desc"]:
        parts.append(f"Quem aparece/fala: {b['avatar_desc']}")
    return ("MARCA DO USUÁRIO (use sempre como referência):\n" + "\n".join(parts)) if parts else ""
