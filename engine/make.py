import numpy as np, math, random, subprocess, sys, os, wave
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, 'press-start-2p.woff')
OW, OH, FPS = 1080, 1920, 30
W, H = 180, 500
ROWS = [130, 220, 310, 400]           # bottom y of each shop row
SLOTS = [4, 33, 62, 91, 120, 149]
SW, SH = 26, 26
LIME = (198, 241, 53)
CREAM = (247, 232, 180)
INK = (22, 18, 14)

# ---------------------------------------------------------------- world art
def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)

KINDS = ['cafe', 'farm', 'paes', 'barber', 'pet', 'cafe', 'pet', 'barber', 'farm', 'pizza', 'cafe', 'paes']
ROOFS = [(150, 62, 52), (70, 92, 130), (126, 82, 58), (88, 112, 70), (164, 122, 60), (112, 72, 112)]
WALLS = [(214, 196, 160), (196, 176, 146), (206, 190, 156)]

class World:
    def __init__(self, seed=3):
        self.img = Image.new('RGB', (W, H))
        self.d = ImageDraw.Draw(self.img)
        self.lights = []      # (x, y, r, intensity, color)
        self.emit = []        # (x0,y0,x1,y1,color) drawn after lighting
        self.rng = random.Random(seed)

    def ground(self):
        px = self.img.load()
        shades = [(44, 82, 46), (50, 90, 50), (40, 74, 42), (56, 98, 54)]
        r = random.Random(11)
        for y in range(H):
            for x in range(W):
                px[x, y] = shades[r.randrange(4) if r.random() < 0.35 else 1]
        for _ in range(140):
            x, y = r.randrange(W), r.randrange(H)
            px[x, y] = r.choice([(190, 170, 90), (200, 120, 120), (150, 180, 220)])

    def street(self, y0):
        r = random.Random(y0)
        px = self.img.load()
        for y in range(y0, y0 + 16):
            for x in range(W):
                c = r.choice([(120, 88, 58), (112, 82, 54), (128, 96, 62), (120, 88, 58)])
                if y in (y0, y0 + 15):
                    c = (92, 68, 46)
                px[x, y] = c
        for _ in range(40):
            px[r.randrange(W), r.randrange(y0 + 2, y0 + 14)] = (98, 74, 50)

    def tree(self, x, y, kind):
        d = self.d
        if kind == 0:
            d.rectangle([x, y + 3, x + 1, y + 6], fill=(78, 54, 36))
            d.ellipse([x - 4, y - 5, x + 5, y + 4], fill=(30, 72, 40))
            d.ellipse([x - 4, y - 6, x + 3, y + 1], fill=(44, 96, 50))
            d.point([(x - 2, y - 4), (x - 1, y - 4), (x - 2, y - 3)], fill=(76, 132, 64))
        else:
            d.rectangle([x, y + 4, x + 1, y + 6], fill=(70, 48, 32))
            for i, w in enumerate([1, 2, 3, 4]):
                d.rectangle([x - w + 1, y - 6 + i * 2, x + w, y - 5 + i * 2 + 1], fill=(28, 64, 44) if i % 2 else (36, 80, 52))
        d.rectangle([x - 2, y + 7, x + 3, y + 7], fill=(30, 52, 32))

    def forest(self, zones_block):
        r = random.Random(5)
        pts = []
        for _ in range(900):
            x, y = r.randrange(-3, W + 3), r.randrange(-3, H + 3)
            if any(a <= y <= b for a, b in zones_block):
                continue
            if any(abs(x - px) < 6 and abs(y - py) < 6 for px, py in pts):
                continue
            pts.append((x, y))
        for x, y in sorted(pts, key=lambda p: p[1]):
            self.tree(x, y, r.randrange(2))

    def lot(self, x, yb, col=(120, 90, 60)):
        d = self.d
        y0 = yb - SH + 6
        for (a, b) in [(x, y0), (x + SW - 1, y0), (x, yb), (x + SW - 1, yb)]:
            d.rectangle([a, b - 2, a, b], fill=col)
        for xx in range(x + 1, x + SW - 1, 2):
            d.point([(xx, y0 - 1), (xx, yb - 1)], fill=shade(col, 1.25))

    def shop(self, x, yb, i, lit=False, kind=None, glow=1.0):
        d = self.d
        roof = ROOFS[i % 6]
        wall = WALLS[i % 3]
        y0 = yb - SH
        d.rectangle([x, yb + 1, x + SW, yb + 1], fill=(30, 46, 30))
        d.rectangle([x - 1, y0, x + SW, y0 + 11], fill=roof)
        d.rectangle([x - 1, y0, x + SW, y0], fill=shade(roof, 1.25))
        for yy in range(y0 + 3, y0 + 11, 3):
            d.line([x - 1, yy, x + SW, yy], fill=shade(roof, 0.8))
        d.rectangle([x - 1, y0 + 11, x + SW, y0 + 11], fill=shade(roof, 0.6))
        d.rectangle([x, y0 + 12, x + SW - 1, yb], fill=wall)
        d.rectangle([x, y0 + 12, x + SW - 1, y0 + 12], fill=shade(wall, 0.7))
        cx = x + SW // 2
        # door
        door = (255, 200, 110) if lit else (70, 46, 32)
        d.rectangle([cx - 3, yb - 7, cx + 2, yb], fill=(56, 38, 26))
        d.rectangle([cx - 2, yb - 6, cx + 1, yb], fill=door if not lit else (96, 64, 40))
        # windows
        for wx in (x + 3, x + SW - 9):
            d.rectangle([wx - 1, y0 + 16, wx + 6, y0 + 21], fill=(80, 58, 40))
            col = (255, 214, 120) if lit else (38, 50, 68)
            d.rectangle([wx, y0 + 17, wx + 5, y0 + 20], fill=col)
            d.line([wx + 2, y0 + 17, wx + 2, y0 + 20], fill=(80, 58, 40))
            if lit:
                self.emit.append((wx, y0 + 17, wx + 1, y0 + 20, (255, 228, 150)))
                self.emit.append((wx + 3, y0 + 17, wx + 5, y0 + 20, (255, 214, 120)))
                self.lights.append((wx + 3, y0 + 22, 14, 0.55 * glow, (255, 170, 70)))
            else:
                d.point([(wx, y0 + 17)], fill=(70, 90, 110))
        # sign plank
        kind = kind or KINDS[i % 12]
        sc = {'paes': (196, 140, 76), 'barber': (60, 80, 140), 'pizza': (176, 52, 40),
              'cafe': (96, 64, 44), 'farm': (40, 120, 80), 'pet': (150, 90, 150), 'novo': LIME}[kind]
        if lit and kind != 'novo':
            sc = shade(sc, 1.35)
        d.rectangle([cx - 6, y0 + 13, cx + 5, y0 + 15], fill=sc)
        d.rectangle([cx - 6, y0 + 15, cx + 5, y0 + 15], fill=shade(sc, 0.7))
        if kind == 'paes':
            d.rectangle([cx - 2, y0 + 13, cx + 1, y0 + 14], fill=(244, 206, 140))
            d.point([(cx - 1, y0 + 13), (cx + 1, y0 + 13)], fill=(170, 110, 60))
        elif kind == 'barber':
            for yy in range(y0 + 13, yb):
                d.rectangle([x + SW - 2, yy, x + SW - 1, yy], fill=[(220, 50, 50), (240, 240, 240), (60, 90, 200)][(yy) % 3])
            d.rectangle([cx - 3, y0 + 14, cx + 2, y0 + 14], fill=(240, 240, 240))
        elif kind == 'pizza':
            d.polygon([(cx - 3, y0 + 13), (cx + 2, y0 + 13), (cx, y0 + 15)], fill=(240, 170, 60))
            d.point([(cx - 1, y0 + 13), (cx + 1, y0 + 14)], fill=(190, 40, 30))
        elif kind == 'cafe':
            d.rectangle([cx - 2, y0 + 13, cx, y0 + 14], fill=(240, 236, 220))
            d.point([(cx + 1, y0 + 13)], fill=(240, 236, 220))
        elif kind == 'farm':
            d.rectangle([cx - 1, y0 + 13, cx, y0 + 15], fill=(240, 240, 240))
            d.rectangle([cx - 2, y0 + 14, cx + 1, y0 + 14], fill=(240, 240, 240))
        elif kind == 'novo':
            d.rectangle([cx - 1, y0 + 13, cx, y0 + 15], fill=(30, 36, 20))
            d.rectangle([cx - 3, y0 + 14, cx + 2, y0 + 14], fill=(30, 36, 20))
            self.emit.append((cx - 6, y0 + 13, cx + 5, y0 + 15, None))
            self.lights.append((cx, y0 + 16, 24, 0.7, (170, 255, 60)))
        else:
            d.point([(cx - 2, y0 + 14), (cx, y0 + 13), (cx + 2, y0 + 14), (cx, y0 + 14)], fill=(250, 230, 240))
        if lit:
            self.lights.append((cx, y0 + 14, 9, 0.35 * glow, (255, 200, 120)))

    def lamp(self, x, y):
        d = self.d
        d.rectangle([x, y - 6, x, y], fill=(40, 36, 34))
        d.rectangle([x - 1, y - 8, x + 1, y - 7], fill=(255, 236, 170))
        self.emit.append((x - 1, y - 8, x + 1, y - 7, (255, 240, 190)))
        self.lights.append((x, y - 4, 20, 0.6, (255, 190, 90)))

    def plaza(self, x0, x1, yb):
        d = self.d
        y0 = yb - SH + 2
        d.rectangle([x0, y0, x1, yb], fill=(132, 128, 120))
        for yy in range(y0, yb + 1, 4):
            d.line([x0, yy, x1, yy], fill=(116, 112, 106))
        for xx in range(x0, x1, 6):
            for yy in range(y0, yb, 8):
                d.line([xx + (4 if (yy // 4) % 2 else 0), yy, xx + (4 if (yy // 4) % 2 else 0), yy + 3], fill=(116, 112, 106))
        cx, cy = (x0 + x1) // 2, (y0 + yb) // 2
        d.ellipse([cx - 9, cy - 7, cx + 9, cy + 7], fill=(150, 146, 138))
        d.ellipse([cx - 7, cy - 5, cx + 7, cy + 5], fill=(60, 120, 170))
        d.ellipse([cx - 4, cy - 3, cx + 4, cy + 3], fill=(90, 160, 210))
        d.rectangle([cx - 1, cy - 4, cx + 1, cy + 1], fill=(180, 176, 168))
        d.point([(cx, cy - 6), (cx - 1, cy - 5), (cx + 1, cy - 5)], fill=(200, 230, 250))
        for bx in (x0 + 4, x1 - 10):
            d.rectangle([bx, yb - 4, bx + 6, yb - 3], fill=(110, 76, 50))
        for fx in (x0 + 3, x1 - 3):
            self.tree(fx, y0 + 4, 0)
        self.lamp(x0 + 14, yb - 2)
        self.lamp(x1 - 14, yb - 2)

    def bubble(self, cx, yb):
        d = self.d
        y0 = yb - SH - 14
        d.rectangle([cx - 5, y0, cx + 5, y0 + 9], fill=(244, 240, 228))
        d.rectangle([cx - 5, y0, cx + 5, y0], fill=(255, 255, 255))
        d.polygon([(cx - 1, y0 + 10), (cx + 2, y0 + 10), (cx - 1, y0 + 12)], fill=(244, 240, 228))
        q = ["0110", "1001", "0010", "0100", "0000", "0100"]
        for j, row in enumerate(q):
            for k, ch in enumerate(row):
                if ch == '1':
                    d.point((cx - 2 + k, y0 + 2 + j), fill=(30, 30, 40))
        self.emit.append((cx - 5, y0, cx + 5, y0 + 9, None))

    def signboard(self, cx, yb):
        d = self.d
        y0 = yb - 20
        d.rectangle([cx - 1, y0 + 6, cx, yb - 2], fill=(70, 50, 34))
        d.rectangle([cx - 7, y0, cx + 6, y0 + 7], fill=(40, 44, 30))
        d.rectangle([cx - 6, y0 + 1, cx + 5, y0 + 6], fill=LIME)
        d.rectangle([cx - 1, y0 + 2, cx, y0 + 5], fill=(30, 36, 20))
        d.rectangle([cx - 3, y0 + 3, cx + 2, y0 + 4], fill=(30, 36, 20))
        self.emit.append((cx - 6, y0 + 1, cx + 5, y0 + 6, None))
        self.lights.append((cx, y0 + 4, 22, 0.75, (170, 255, 60)))

    def finish(self, ambient, tint):
        a = np.asarray(self.img).astype(np.float32)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        L = np.zeros((H, W), np.float32)
        add = np.zeros((H, W, 3), np.float32)
        for (x, y, r, i, col) in self.lights:
            f = np.clip(1 - np.hypot(xx - x, (yy - y) * 1.15) / r, 0, 1) ** 1.6 * i
            L += f
            add += f[..., None] * np.array(col, np.float32)[None, None] / 255 * 60
        L = np.floor(np.minimum(L, 1.1) * 8) / 8           # banded, pixel-art light
        add = np.floor(add / 8) * 8
        out = a * (ambient * np.array(tint, np.float32))[None, None] * 1.0
        out = out + a * L[..., None] * 0.85 + add
        out = np.clip(out, 0, 255)
        src = np.asarray(self.img)
        for (x0, y0, x1, y1, col) in self.emit:
            if col is None:
                out[y0:y1 + 1, x0:x1 + 1] = src[y0:y1 + 1, x0:x1 + 1]
            else:
                out[y0:y1 + 1, x0:x1 + 1] = col
        return out.astype(np.uint8)


def build(state):
    w = World()
    w.ground()
    blocks = [(r - SH - 6, r + 18) for r in ROWS]
    w.forest(blocks)
    for r in ROWS:
        w.street(r + 2)
    lit_B = {1, 3, 6, 9}
    i = 0
    for ri, r in enumerate(ROWS):
        for si, x in enumerate(SLOTS):
            occupied_B = ri in (1, 2)
            if state in ('B', 'Bq', 'D', 'E'):
                if occupied_B:
                    w.shop(x, r, i, lit=(i in lit_B))
                    i += 1
                else:
                    w.lot(x, r)
            else:  # C: everything built
                if ri == 3 and si in (2, 3):
                    continue
                w.shop(x, r, ri * 6 + si, lit=True, glow=1.0)
        if state == 'C':
            for lx in range(16, W, 44):
                w.lamp(lx, r + 3)
    if state == 'C':
        w.plaza(SLOTS[2] - 1, SLOTS[3] + SW, ROWS[3])
    if state == 'Bq':
        w.bubble(SLOTS[4] + SW // 2, ROWS[2])
    if state == 'E':
        w.shop(SLOTS[2], ROWS[0], 2, lit=True, kind='novo')
    if state == 'D':
        w.signboard(SLOTS[2] + SW // 2, ROWS[0])
        w.lot(SLOTS[2], ROWS[0], col=(150, 200, 60))
    if state == 'C':
        return w.finish(0.78, (0.92, 0.94, 1.0))
    return w.finish(0.62, (0.80, 0.86, 1.05))

# ---------------------------------------------------------------- text
font_cache = {}
def F(sz):
    if sz not in font_cache:
        font_cache[sz] = ImageFont.truetype(FONT, sz)
    return font_cache[sz]

TS = 5   # text pixel scale

# the font's accented capitals are malformed: draw the base letter plus our own accent pixels
ACUTE = [(3, 2), (4, 2), (4, 3), (5, 3)]
CIRC = [(1, 2), (2, 3), (3, 3), (4, 2)]
TILDE = [(1, 2), (2, 3), (3, 2), (4, 3), (5, 2)]
GRAVE = [(2, 3), (3, 3), (3, 2), (4, 2)]
ACC = {'Á': ('A', ACUTE), 'É': ('E', ACUTE), 'Í': ('I', ACUTE), 'Ó': ('O', ACUTE), 'Ú': ('U', ACUTE),
       'Â': ('A', CIRC), 'Ê': ('E', CIRC), 'Ô': ('O', CIRC), 'Ã': ('A', TILDE), 'Õ': ('O', TILDE), 'À': ('A', GRAVE)}

def draw_text(d, x, y, text, f, fill, sz):
    plain = ''.join(ACC[ch][0] if ch in ACC else ch for ch in text)
    d.text((x, y), plain, font=f, fill=fill)
    u = max(1, sz // 8)
    for i, ch in enumerate(text):
        if ch in ACC:
            px = int(x + d.textlength(plain[:i], font=f))
            top = d.textbbox((px, y), 'O', font=f)[1]
            for (ax, ay) in ACC[ch][1]:
                d.rectangle([px + ax * u, top - ay * u, px + ax * u + u - 1, top - ay * u + u - 1], fill=fill)
def text_img(items):
    """items: list of (text, size, color, y_center). returns RGBA at output size"""
    im = Image.new('RGBA', (OW // TS, OH // TS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    for text, sz, col, yc in items:
        f = F(sz)
        bb = d.textbbox((0, 0), text, font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        x = (im.width - tw) // 2 - bb[0]
        y = int(yc - th / 2) - bb[1]
        o = max(1, sz // 8)
        layers = [(INK, [(dx, dy) for dx in range(-o, o + 1) for dy in range(-o, o + 2) if dx or dy]), (col, [(0, 0)])]
        for c, offs in layers:
            for dx, dy in offs:
                draw_text(d, x + dx, y + dy, text, f, c + (255,), sz)
    return im.resize((OW, OH), Image.NEAREST)

_tc = {}
def text_cached(key, items):
    if key not in _tc:
        _tc[key] = np.asarray(text_img(items)).astype(np.float32)
    return _tc[key]

# ---------------------------------------------------------------- 3D scene
def boxes3d():
    B = []
    def box(x0, x1, y0, y1, z0, z1, c):
        B.append(((x0, x1), (y0, y1), (z0, z1), c))
    box(-1.6, 1.6, 0, 2.2, -1.2, 1.2, (214, 196, 160))
    box(-1.85, 1.85, 2.2, 2.55, -1.45, 1.45, (150, 62, 52))
    box(-1.4, 1.4, 2.55, 2.85, -1.0, 1.0, (130, 54, 46))
    box(-0.38, 0.38, 0, 1.15, 1.2, 1.26, (70, 46, 32))
    box(-1.35, -0.65, 0.85, 1.5, 1.2, 1.25, (255, 214, 120))
    box(0.65, 1.35, 0.85, 1.5, 1.2, 1.25, (255, 214, 120))
    box(-1.75, 1.75, 1.62, 1.78, 1.2, 1.7, LIME)
    box(-1.0, 1.0, 2.85, 3.45, 0.85, 0.97, (24, 28, 20))
    box(-0.9, 0.9, 2.93, 3.37, 0.97, 1.0, LIME)
    box(2.35, 2.55, 0, 0.9, 0.3, 0.5, (90, 62, 40))
    box(1.95, 2.95, 0.9, 1.9, -0.1, 0.9, (52, 110, 58))
    box(-2.6, -2.5, 0, 2.0, 1.4, 1.5, (40, 40, 40))
    box(-2.75, -2.35, 2.0, 2.2, 1.25, 1.65, (255, 236, 170))
    return B

BOXES = boxes3d()
LDIR = np.array([-0.45, 0.8, 0.55]); LDIR /= np.linalg.norm(LDIR)

def render3d(t, dur):
    im = Image.new('RGB', (OW, OH))
    g = np.linspace(0, 1, OH)[:, None]
    bg = (np.array([8, 10, 7]) * (1 - g) + np.array([20, 26, 12]) * g)
    arr = np.repeat(bg[:, None, :], OW, axis=1).reshape(OH, OW, 3)
    im = Image.fromarray(arr.astype(np.uint8))
    d = ImageDraw.Draw(im)
    a = -0.9 + 1.5 * (t / dur)
    p = 0.52
    pop = min(1, t / 0.35)
    s = 175 * (0.82 + 0.18 * (1 - (1 - pop) ** 3))
    cx, cy = OW / 2, OH * 0.47
    ca, sa, cp, sp = math.cos(a), math.sin(a), math.cos(p), math.sin(p)
    def proj(x, y, z):
        xr = x * ca + z * sa
        zr = -x * sa + z * ca
        yc = y * cp - zr * sp
        zc = y * sp + zr * cp
        return (cx + s * xr, cy - s * yc, zc)
    # ground plate + grid
    G = 3.2
    pts = [proj(*q)[:2] for q in [(-G, 0, -G), (G, 0, -G), (G, 0, G), (-G, 0, G)]]
    d.polygon(pts, fill=(18, 24, 14))
    n = 8
    for k in range(n + 1):
        v = -G + 2 * G * k / n
        d.line([proj(v, 0, -G)[:2], proj(v, 0, G)[:2]], fill=(70, 96, 24), width=2)
        d.line([proj(-G, 0, v)[:2], proj(G, 0, v)[:2]], fill=(70, 96, 24), width=2)
    d.polygon(pts, outline=LIME, width=4)
    order = []
    for (xs, ys, zs, c) in BOXES:
        ctr = proj(sum(xs) / 2, sum(ys) / 2, sum(zs) / 2)[2]
        order.append((ctr, xs, ys, zs, c))
    order.sort(key=lambda o: o[0])
    faces_def = [((1, 0, 0), 'x', 1), ((-1, 0, 0), 'x', 0), ((0, 1, 0), 'y', 1),
                 ((0, -1, 0), 'y', 0), ((0, 0, 1), 'z', 1), ((0, 0, -1), 'z', 0)]
    for _, xs, ys, zs, c in order:
        fl = []
        for nrm, ax, side in faces_def:
            nx, ny, nz = nrm
            nzc = ny * sp + (-nx * sa + nz * ca) * cp
            if nzc <= 0.001:
                continue
            if ax == 'x':
                X = xs[side]; q = [(X, ys[0], zs[0]), (X, ys[1], zs[0]), (X, ys[1], zs[1]), (X, ys[0], zs[1])]
            elif ax == 'y':
                Y = ys[side]; q = [(xs[0], Y, zs[0]), (xs[1], Y, zs[0]), (xs[1], Y, zs[1]), (xs[0], Y, zs[1])]
            else:
                Z = zs[side]; q = [(xs[0], ys[0], Z), (xs[1], ys[0], Z), (xs[1], ys[1], Z), (xs[0], ys[1], Z)]
            lam = 0.42 + 0.58 * max(0, float(np.dot(nrm, LDIR)))
            if c in [(255, 214, 120), (255, 236, 170), LIME]:
                lam = max(lam, 0.9)
            pts = [proj(*v)[:2] for v in q]
            d.polygon(pts, fill=shade(c, lam), outline=(10, 12, 8), width=3)
    out = np.asarray(im).astype(np.float32)
    # lime ground glow
    yy, xx = np.ogrid[0:OH, 0:OW]
    glow = np.clip(1 - np.hypot((xx - cx) / 700, (yy - cy - 120) / 380), 0, 1) ** 2
    out += glow[..., None] * np.array([40, 60, 8])
    # glitch-in for first frames
    if t < 0.2:
        rr = random.Random(int(t * 1000))
        for _ in range(14):
            y0 = rr.randrange(0, OH - 60); h = rr.randrange(10, 60); sh = rr.randrange(-80, 80)
            out[y0:y0 + h] = np.roll(out[y0:y0 + h], sh, axis=1)
    return np.clip(out, 0, 255)

# ---------------------------------------------------------------- camera views
WORLDS = {}
VIEWINFO = [0, 0, 6]
def world(state):
    if state not in WORLDS:
        WORLDS[state] = build(state)
    return WORLDS[state]

def view(state, cx, cy, k):
    wd = world(state)
    vw, vh = OW / k, OH / k
    x0 = min(max(cx - vw / 2, 0), W - vw)
    y0 = min(max(cy - vh / 2, 0), H - vh)
    ix, iy = int(math.floor(x0)), int(math.floor(y0))
    nw, nh = int(math.ceil(vw)) + 2, int(math.ceil(vh)) + 2
    reg = wd[iy:iy + nh, ix:ix + nw]
    if reg.shape[0] < nh or reg.shape[1] < nw:
        reg = np.pad(reg, ((0, nh - reg.shape[0]), (0, nw - reg.shape[1]), (0, 0)), mode='edge')
    up = np.repeat(np.repeat(reg, k, axis=0), k, axis=1)
    ox, oy = int(round((x0 - ix) * k)), int(round((y0 - iy) * k))
    VIEWINFO[:] = [x0, y0, k]
    return up[oy:oy + OH, ox:ox + OW].astype(np.float32)

def shop_center(row, slot):
    return SLOTS[slot] + SW / 2, ROWS[row] - SH / 2 + 2

# ---------------------------------------------------------------- timeline
def ease(u):
    return u * u * (3 - 2 * u)

R2, R3 = 1, 2
S = []   # (t0, t1, kind, args)
def cam(t0, t1, state, c0, c1, k):
    S.append((t0, t1, 'cam', (state, c0, c1, k)))

LX, LY = SLOTS[2] + SW / 2, ROWS[0] - 12
cam(0.0, 1.4, 'D', (LX, LY + 4), (LX, LY + 1), 12)
cam(1.4, 3.2, 'E', (LX, LY + 1), (LX, LY - 3), 12)
cam(3.2, 6.6, 'B', (90, 205), (90, 232), 6)
bx, by = shop_center(R2, 2); cam(6.6, 7.8, 'B', (bx + 4, by), (bx, by + 2), 15)
bx, by = shop_center(R2, 3); cam(7.8, 9.0, 'B', (bx - 3, by + 2), (bx + 1, by), 15)
bx, by = shop_center(R3, 3); cam(9.0, 10.2, 'B', (bx, by + 3), (bx, by - 1), 15)
bx, by = shop_center(R3, 4); cam(10.2, 12.6, 'Bq', (bx, by - 2), (bx, by - 7), 14)
cam(12.6, 14.0, 'C', (90, 250), (90, 236), 6)
cam(14.0, 15.0, 'C', (70, ROWS[0] - 10), (100, ROWS[0] - 8), 9)
cam(15.0, 16.2, 'C', (90, ROWS[3] - 4), (90, ROWS[3] - 10), 12)
bx, by = shop_center(0, 4); cam(16.2, 17.6, 'C', (bx - 3, by), (bx + 3, by), 15)
cam(17.6, 20.0, 'C', (90, 240), (90, 220), 6)
S.append((20.0, 22.2, '3d', None))
cam(22.2, 24.6, 'D', (LX, LY + 6), (LX, LY + 1), 12)
cam(24.6, 27.2, 'E', (LX, LY + 1), (LX, LY - 4), 12)
cam(27.2, 31.6, 'D', (90, 190), (90, 160), 6)
TOTAL = 31.6
JINGLE_T = 20.0
FLASH = [1.4, 24.6]
PLATES = [(1.55, 3.2, 'SUA LOJA'), (24.75, 27.2, 'SEU NEGÓCIO')]
PLATE_ANCHOR = (SLOTS[2] + SW / 2, ROWS[0] - SH - 1)

CAP = [  # (t0, t1, text, color)
    (0.0, 1.4, 'SE VOCÊ ME SEGUIR AGORA', CREAM), (1.4, 2.3, 'EU CONSTRUO', CREAM), (2.3, 3.2, 'SUA LOJA AQUI', LIME),
    (4.4, 5.5, 'E CADA UM DELES', CREAM), (5.5, 6.6, 'VIROU UMA LOJA', LIME),
    (6.6, 7.8, 'PADARIA', CREAM), (7.8, 9.0, 'BARBEARIA', CREAM), (9.0, 10.2, 'PIZZARIA', CREAM),
    (10.2, 11.4, 'MAS NENHUMA', CREAM), (11.4, 12.6, 'TEM SITE AINDA', CREAM),
    (12.6, 14.0, 'A CADA NOVO SEGUIDOR', CREAM), (14.0, 15.0, 'MAIS LOJAS', CREAM), (15.0, 16.2, 'UMA PRAÇA', CREAM),
    (16.2, 17.6, 'LETREIROS ACESOS', CREAM),
    (17.6, 18.8, 'COM 100 SEGUIDORES', CREAM), (18.8, 20.0, 'A CIDADE INTEIRA', CREAM), (20.0, 22.2, 'VIRA 3D', LIME),
    (22.2, 23.4, 'COMENTA O NOME', CREAM), (23.4, 24.6, 'DO SEU NEGÓCIO', LIME), (24.6, 25.9, 'ELE VIRA UMA LOJA', CREAM),
    (25.9, 27.2, 'COM O NOME NA FACHADA', LIME),
    (27.2, 28.6, 'SEGUE A PÁGINAS PRO', CREAM), (28.6, 29.8, 'A PRÓXIMA LOJA', CREAM), (29.8, TOTAL, 'PODE SER A SUA', LIME),
]
CAP_Y = int(OH / TS * 0.72)

def overlays(t):
    items = []
    key = []
    if 3.2 <= t < 6.6:
        items += [('ESSA PÁGINA TEM SÓ', 8, CREAM, 34), ('12', 32, LIME, 62), ('SEGUIDORES', 8, CREAM, 92)]
        key.append('title')
    if t >= 27.2:
        items += [('@paginasproo', 8, LIME, 40)]
        key.append('end')
    pop = False
    for (a, b, txt, col) in CAP:
        if a <= t < b:
            dy = -2 if t - a < 0.07 else 0
            items.append((txt, 8, col, CAP_Y + dy))
            key.append(txt + str(dy))
    return ('|'.join(key), items)

_pc = {}
def plate_img(name):
    if name in _pc:
        return _pc[name]
    sc = 4
    f = F(8)
    tmp = ImageDraw.Draw(Image.new('RGBA', (10, 10)))
    tw = int(tmp.textlength(''.join(ACC[c][0] if c in ACC else c for c in name), font=f))
    w, h = tw + 10, 8 + 12
    im = Image.new('RGBA', (w, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im); d.fontmode = '1'
    d.rectangle([0, 0, w - 1, h - 1], fill=INK + (255,))
    d.rectangle([1, 1, w - 2, h - 2], fill=LIME + (255,))
    d.rectangle([2, 2, w - 3, h - 3], fill=(18, 22, 12, 255))
    d.polygon([(w // 2 - 3, h - 1), (w // 2 + 3, h - 1), (w // 2, h + 3)], fill=LIME + (255,))
    draw_text(d, 5, 7, name, f, LIME + (255,), 8)
    _pc[name] = np.asarray(im.resize((im.width * sc, im.height * sc), Image.NEAREST)).astype(np.float32)
    return _pc[name]

yy, xx = np.ogrid[0:OH, 0:OW]
VIG = np.clip(1.0 - 0.75 * (((xx - OW / 2) / (OW * 0.62)) ** 2 + ((yy - OH / 2) / (OH * 0.62)) ** 2), 0.25, 1)[..., None].astype(np.float32)

FLIES = [(random.Random(i).random(), random.Random(i + 99).random(), random.Random(i + 7).random()) for i in range(18)]

def frame(t):
    for (t0, t1, kind, args) in S:
        if t0 <= t < t1 or (t >= t1 and t1 == TOTAL):
            break
    u = ease(min(1, (t - t0) / (t1 - t0)))
    if kind == 'cam':
        state, c0, c1, k = args
        img = view(state, c0[0] + (c1[0] - c0[0]) * u, c0[1] + (c1[1] - c0[1]) * u, k)
        # fireflies
        for i, (fx, fy, ph) in enumerate(FLIES):
            px = int((fx * OW + 40 * math.sin(t * 0.7 + ph * 9)) % OW)
            py = int((fy * OH - t * 18 * (0.5 + ph)) % OH)
            al = max(0, math.sin(t * 2.2 + ph * 20)) * 0.8
            sz = 6
            img[py:py + sz, px:px + sz] = img[py:py + sz, px:px + sz] * (1 - al) + np.array([220, 245, 150]) * al
        img = img * VIG
        for (p0, p1, name) in PLATES:
            if p0 <= t < p1:
                x0, y0, k = VIEWINFO
                sx = (PLATE_ANCHOR[0] - x0) * k
                sy = (PLATE_ANCHOR[1] - y0) * k - (12 if t - p0 < 0.08 else 0)
                pl = plate_img(name)
                ph, pw = pl.shape[:2]
                X, Y = int(sx - pw / 2), int(sy - ph)
                a = pl[..., 3:4] / 255
                img[Y:Y + ph, X:X + pw] = img[Y:Y + ph, X:X + pw] * (1 - a) + pl[..., :3] * a
        for fl in FLASH:
            if fl <= t < fl + 0.2:
                f = 1 - (t - fl) / 0.2
                img = img * (1 - 0.85 * f) + 255 * 0.85 * f
    else:
        img = render3d(t - t0, t1 - t0) * (0.5 + 0.5 * VIG)
    key, items = overlays(t)
    if items:
        ti = text_cached(key, items)
        a = ti[..., 3:4] / 255
        img = img * (1 - a) + ti[..., :3] * a
    if t > TOTAL - 0.7:
        img = img * max(0, (TOTAL - t) / 0.7)
    return np.clip(img, 0, 255).astype(np.uint8)

# ---------------------------------------------------------------- audio
def synth(path):
    sr = 44100
    n = int(TOTAL * sr)
    out = np.zeros(n, np.float32)
    bpm = 96
    beat = 60 / bpm
    def note(f):
        return 440 * 2 ** ((f - 69) / 12)
    def sq(freq, dur, vol, duty=0.5, decay=6.0):
        m = int(dur * sr)
        tt = np.arange(m) / sr
        w = ((tt * freq) % 1 < duty).astype(np.float32) * 2 - 1
        return w * vol * np.exp(-tt * decay)
    def tri(freq, dur, vol):
        m = int(dur * sr)
        tt = np.arange(m) / sr
        w = 2 * np.abs(2 * ((tt * freq) % 1) - 1) - 1
        env = np.minimum(1, tt / 0.01) * np.exp(-tt * 1.5)
        return w * vol * env
    def put(sig, t0):
        i = int(t0 * sr)
        if i >= n:
            return
        sig = sig[:n - i]
        out[i:i + len(sig)] += sig
    chords = [(57, [69, 72, 76]), (53, [65, 69, 72]), (48, [64, 67, 72]), (55, [67, 71, 74])]  # Am F C G
    t = 0.0
    bar = 0
    while t < TOTAL:
        root, tones = chords[bar % 4]
        put(tri(note(root - 12), beat * 4, 0.22), t)
        put(tri(note(root - 12), beat * 2, 0.12), t + beat * 2)
        arp = tones + [tones[1] + 12, tones[2], tones[1], tones[0] + 12, tones[2]]
        for j in range(8):
            v = 0.05 if bar < 2 else 0.065
            put(sq(note(arp[j]), beat * 0.5, v, 0.25, 7), t + j * beat * 0.5)
        if bar >= 2:
            for j in range(8):
                m = int(0.03 * sr)
                hat = np.random.RandomState(j).uniform(-1, 1, m) * np.exp(-np.arange(m) / sr * 120) * 0.025
                put(hat.astype(np.float32), t + j * beat * 0.5)
        t += beat * 4
        bar += 1
    for (a, b, txt, col) in CAP:
        put(sq(1568 if col == LIME else 1175, 0.06, 0.05, 0.5, 40), a)
    for fl in FLASH:
        for j, f in enumerate([60, 67, 72, 79]):
            put(sq(note(f), 0.1, 0.07, 0.5, 8), fl + j * 0.05)
    for j, f in enumerate([72, 76, 79, 84, 88]):   # level-up jingle at 3D reveal
        put(sq(note(f), 0.12, 0.08, 0.5, 6), JINGLE_T + j * 0.07)
    fade = np.ones(n, np.float32)
    fl = int(1.5 * sr)
    fade[-fl:] = np.linspace(1, 0, fl)
    out *= fade
    out = np.tanh(out * 1.6) * 0.8
    pcm = (out * 32767).astype(np.int16)
    st = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(st.tobytes())

if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'preview':
        for ts in sys.argv[2:]:
            Image.fromarray(frame(float(ts))).save(os.path.join(HERE, f'pv_{ts}.jpg'), quality=88)
    else:
        synth(os.path.join(HERE, 'music.wav'))
        tmp = os.path.join(HERE, 'video_tmp.mp4')
        p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{OW}x{OH}',
                              '-r', str(FPS), '-i', '-', '-i', os.path.join(HERE, 'music.wav'),
                              '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                              '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', tmp], stdin=subprocess.PIPE)
        nf = int(TOTAL * FPS)
        for i in range(nf):
            p.stdin.write(frame(i / FPS).tobytes())
        p.stdin.close()
        if p.wait() == 0:
            os.replace(tmp, os.path.join(HERE, 'cidade-pro-ep1-v2.mp4'))
            print('ok')
