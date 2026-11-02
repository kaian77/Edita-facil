"""Cidade Pro — gera um episódio a partir de um spec JSON.

uso: python3 episode.py spec.json saida.mp4 [--preview t1 t2 ...]

spec = {
  "episode": 2,
  "followers": 31,
  "named_before": ["Barbearia do Zé", ...],   # lojas com nome já construídas em episódios anteriores
  "new": ["Doce Mel Confeitaria", ...]         # lojas novas deste episódio (comentários)
}
Precisa do modelo Kokoro em ../kokoro (veja README).
"""
import json, os, sys, math, re, subprocess, random
import numpy as np, soundfile as sf
from num2words import num2words

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make as M

KOKORO = os.environ.get('KOKORO_DIR', os.path.join(HERE, '..', 'kokoro'))
VOICE, SPEED = 'pm_alex', 0.97
MAX_SHOW = 6

def num(n):
    return num2words(int(n), lang='pt_BR')

def clean_name(s, maxlen=22):
    s = re.sub(r'[^0-9A-Za-zÀ-ÿ&\'\-\. ]', '', s).strip()
    s = re.sub(r'\s+', ' ', s)
    return s[:maxlen].strip()

KIND_WORDS = [('barb', 'barber'), ('cabel', 'barber'), ('sal', 'barber'), ('pizz', 'pizza'), ('lanch', 'pizza'),
              ('burg', 'pizza'), ('padar', 'paes'), ('pão', 'paes'), ('pao', 'paes'), ('confeit', 'paes'), ('doce', 'paes'),
              ('bolo', 'paes'), ('café', 'cafe'), ('cafe', 'cafe'), ('pet', 'pet'), ('vet', 'pet'), ('farm', 'farm'),
              ('drog', 'farm'), ('clín', 'farm'), ('clin', 'farm'), ('odont', 'farm'), ('saúde', 'farm')]
def kind_for(name, j):
    n = name.lower()
    for w_, k in KIND_WORDS:
        if w_ in n:
            return k
    return ['cafe', 'pet', 'paes', 'farm', 'pizza', 'barber'][j % 6]

# ------------------------------------------------------------------ city layout
EXTRA_ROW_START = 490
def named_slot(j):
    """posição (x, row_bottom) da j-ésima loja com nome"""
    order_rows = [M.ROWS[0], M.ROWS[3]]
    if j < 12:
        return M.SLOTS[j % 6], order_rows[j // 6]
    r = (j - 12) // 6
    return M.SLOTS[(j - 12) % 6], EXTRA_ROW_START + r * 90

def setup_world_size(total_named):
    rows = list(M.ROWS)
    j = max(total_named + 1, 12)
    if j > 12:
        n_extra = (j - 12 + 5) // 6
        rows += [EXTRA_ROW_START + r * 90 for r in range(n_extra)]
    M.H = max(500, rows[-1] + 100)
    return rows

def build_state(rows, named, sign_at=None, demo_at=None):
    w = M.World()
    w.ground()
    w.forest([(r - M.SH - 6, r + 18) for r in rows])
    for r in rows:
        w.street(r + 2)
        for lx in range(16, M.W, 44):
            w.lamp(lx, r + 3)
    lit_B = {1, 3, 6, 9}
    i = 0
    for ri in (1, 2):
        for x in M.SLOTS:
            w.shop(x, M.ROWS[ri], i, lit=(i in lit_B))
            i += 1
    used = set()
    for j, name in enumerate(named):
        x, yb = named_slot(j)
        w.shop(x, yb, j + 2, lit=True, kind=kind_for(name, j))
        used.add((x, yb))
    for r in rows:
        if r in (M.ROWS[1], M.ROWS[2]):
            continue
        for x in M.SLOTS:
            if (x, r) not in used and (sign_at is None or (x, r) != named_slot(sign_at)) and \
               (demo_at is None or (x, r) != named_slot(demo_at)):
                w.lot(x, r)
    if sign_at is not None:
        x, yb = named_slot(sign_at)
        w.signboard(x + M.SW // 2, yb)
        w.lot(x, yb, col=(150, 200, 60))
    if demo_at is not None:
        x, yb = named_slot(demo_at)
        w.shop(x, yb, 2, lit=True, kind='novo')
    return w.finish(0.66, (0.84, 0.88, 1.04))

def slot_center(j):
    x, yb = named_slot(j)
    return x + M.SW / 2, yb - 12

def plate_anchor(j):
    x, yb = named_slot(j)
    return x + M.SW / 2, yb - M.SH - 1

# ------------------------------------------------------------------ script
def script(spec):
    F = int(spec['followers'])
    before = [clean_name(n) for n in spec.get('named_before', [])]
    new = [clean_name(n) for n in spec.get('new', []) if clean_name(n)]
    k = len(new)
    nb = len(before)
    total_named = nb + k
    segs = []   # dict(say, show, color, shot, extras)
    first = nb
    if k:
        segs.append(dict(say=f"Essa semana, {num(k) if k > 1 else 'uma'} {'lojas novas chegaram' if k > 1 else 'loja nova chegou'} na cidade.",
                         show=f"{k} {'LOJAS NOVAS' if k > 1 else 'LOJA NOVA'} NA CIDADE", color='lime',
                         shot=('cam2', 'pre', 'post', slot_center(first), 12), flash=0.55, plate=(first, new[0], 0.6)))
    else:
        segs.append(dict(say="Essa semana ninguém comentou... e esse terreno continua vazio.",
                         show="NINGUÉM COMENTOU... O TERRENO CONTINUA VAZIO", color='cream',
                         shot=('cam', 'post_sign', slot_center(first), 12)))
    segs.append(dict(say=f"A página agora tem {num(F)} seguidores.", show="", color='cream',
                     shot=('wide', 'post'), title=F))
    for i, name in enumerate(new[:MAX_SHOW]):
        if i == 0 and k:
            say = f"Chegou {name}!"
        else:
            say = f"{'E chegou' if i == min(k, MAX_SHOW) - 1 and i else 'Chegou'} {name}!"
        segs.append(dict(say=say, show=name.upper(), color='lime',
                         shot=('cam', 'post', slot_center(nb + i), 15), plate=(nb + i, name, 0.0), minlen=1.7))
    if k > MAX_SHOW:
        segs.append(dict(say=f"E mais {num(k - MAX_SHOW)} lojas!", show=f"+{k - MAX_SHOW} LOJAS", color='lime',
                         shot=('wide', 'post')))
    total = 12 + total_named
    segs.append(dict(say=f"A cidade já tem {num(total)} lojas.", show=f"A CIDADE JÁ TEM {total} LOJAS", color='cream',
                     shot=('wide', 'post')))
    if F < 100:
        falta = 100 - F
        segs.append(dict(say=f"{'Falta' if falta == 1 else 'Faltam'} {num(falta)} {'seguidor' if falta == 1 else 'seguidores'} pra cidade inteira",
                         show=f"FALTAM {falta} PRA CIDADE INTEIRA", color='cream', shot=('wide', 'post')))
    else:
        segs.append(dict(say="A gente chegou a cem seguidores... e a cidade inteira", show="CHEGAMOS A 100! A CIDADE",
                         color='cream', shot=('wide', 'post')))
    segs.append(dict(say="virar três dê!", show="VIRAR 3D", color='lime', shot=('3d',), minlen=2.2, jingle=True))
    nxt = total_named
    segs.append(dict(say="Comenta o nome do seu negócio,", show="COMENTA O NOME DO SEU NEGÓCIO", color='cream',
                     shot=('cam', 'post_sign', slot_center(nxt), 12), short=True))
    segs.append(dict(say="que ele vira uma loja aqui, com o nome na fachada.", show="ELE VIRA LOJA COM O NOME NA FACHADA",
                     color='lime', shot=('cam', 'demo', slot_center(nxt), 12), flash=0.0, plate=(nxt, 'SEU NEGÓCIO', 0.1)))
    segs.append(dict(say="Segue a Páginas Pró. A próxima loja pode ser a sua.", show="SEGUE A PÁGINAS PRO|A PRÓXIMA LOJA PODE SER A SUA",
                     color='cream', shot=('wide', 'post_sign'), handle=True, tail=1.3))
    return segs, before, new, total_named

# ------------------------------------------------------------------ voice
def tts(segs, workdir):
    from kokoro_onnx import Kokoro
    k = Kokoro(os.path.join(KOKORO, 'kokoro-v1.0.onnx'), os.path.join(KOKORO, 'voices-v1.0.bin'))
    for i, s in enumerate(segs):
        a, sr = k.create(s['say'], voice=VOICE, speed=SPEED, lang='pt-br')
        a = np.asarray(a, np.float32)
        nz = np.where(np.abs(a) > 0.01)[0]
        a = a[max(0, nz[0] - 200): nz[-1] + 1200]
        p = os.path.join(workdir, f'seg{i:02d}.wav')
        sf.write(p, a, sr)
        s['wav'] = p
        s['dur'] = len(a) / sr
    return sr

def chunk_caption(text, maxc=20):
    parts = []
    for block in text.split('|'):
        words, cur = block.split(), ''
        for w_ in words:
            if cur and len(cur) + 1 + len(w_) > maxc:
                parts.append(cur); cur = w_
            else:
                cur = (cur + ' ' + w_).strip()
        if cur:
            parts.append(cur)
    return parts

def lay_out(segs):
    t = 0.0
    caps = []
    for s in segs:
        L = s['dur'] + (0.25 if s.get('short') else 0.45)
        L = max(L, s.get('minlen', 0)) + s.get('tail', 0)
        s['t0'], s['t1'] = t, t + L
        if s['show']:
            parts = chunk_caption(s['show'])
            span0, span1 = t + 0.1, t + 0.1 + max(s['dur'], 0.8)
            tot = sum(len(p) for p in parts)
            c = span0
            for j, p in enumerate(parts):
                d = (span1 - span0) * len(p) / tot
                end = c + d if j < len(parts) - 1 else s['t1']
                caps.append((c, end, p, M.LIME if s['color'] == 'lime' else M.CREAM))
                c += d
        t += L
    return t, caps

# ------------------------------------------------------------------ render
def main():
    spec = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    workdir = os.path.dirname(os.path.abspath(out))
    segs, before, new, total_named = script(spec)
    rows = setup_world_size(total_named + 1)
    S = {
        'pre': build_state(rows, before, sign_at=len(before)),
        'post': build_state(rows, before + new),
        'post_sign': build_state(rows, before + new, sign_at=total_named),
        'demo': build_state(rows, before + new, demo_at=total_named),
    }
    M.WORLDS.clear(); M.WORLDS.update(S)
    sr = tts(segs, workdir)
    TOT, caps = lay_out(segs)
    F = int(spec['followers'])
    world_h = M.H

    def cam_at(s, u):
        sh = s['shot']
        if sh[0] in ('cam', 'cam2'):
            c = sh[-2]; k = sh[-1]
            return c[0], c[1] + 3 - 6 * u, k
        if 'title' in s:
            return 90, 165 + 18 * u, 6
        cy0 = 205; cy1 = min(world_h - 170, 250)
        return 90, cy0 + (cy1 - cy0) * u, 6

    def frame(t):
        s = next((x for x in segs if x['t0'] <= t < x['t1']), segs[-1])
        u = M.ease(min(1, (t - s['t0']) / (s['t1'] - s['t0'])))
        sh = s['shot']
        if sh[0] == '3d':
            img = M.render3d(t - s['t0'], s['t1'] - s['t0']) * (0.5 + 0.5 * M.VIG)
        else:
            if sh[0] == 'cam2':
                state = sh[1] if (t - s['t0']) < s.get('flash', 0) else sh[2]
            else:
                state = sh[1]
            cx, cy, k = cam_at(s, u)
            img = M.view(state, cx, cy, k)
            for (fx, fy, ph) in M.FLIES:
                px = int((fx * M.OW + 40 * math.sin(t * 0.7 + ph * 9)) % M.OW)
                py = int((fy * M.OH - t * 18 * (0.5 + ph)) % M.OH)
                al = max(0, math.sin(t * 2.2 + ph * 20)) * 0.8
                img[py:py + 6, px:px + 6] = img[py:py + 6, px:px + 6] * (1 - al) + np.array([220, 245, 150]) * al
            img = img * M.VIG
            if 'plate' in s:
                j, name, delay = s['plate']
                pt = t - s['t0'] - max(delay, s.get('flash', 0) + 0.05 if 'flash' in s else delay)
                if pt >= 0:
                    x0, y0, kk = M.VIEWINFO
                    ax, ay = plate_anchor(j)
                    pl = M.plate_img(name.upper())
                    ph_, pw = pl.shape[:2]
                    X = int((ax - x0) * kk - pw / 2); Y = int((ay - y0) * kk - ph_ - (12 if pt < 0.08 else 0))
                    X = max(8, min(M.OW - pw - 8, X))
                    if 0 <= Y < M.OH - ph_:
                        a = pl[..., 3:4] / 255
                        img[Y:Y + ph_, X:X + pw] = img[Y:Y + ph_, X:X + pw] * (1 - a) + pl[..., :3] * a
            if 'flash' in s:
                fl = s['t0'] + s['flash']
                if fl <= t < fl + 0.2:
                    f = 1 - (t - fl) / 0.2
                    img = img * (1 - 0.85 * f) + 255 * 0.85 * f
        items, key = [], []
        if 'title' in s:
            items += [('ESSA PÁGINA TEM', 8, M.CREAM, 34), (str(s['title']), 32, M.LIME, 62), ('SEGUIDORES', 8, M.CREAM, 92)]
            key.append(f"title{s['title']}")
        if s.get('handle'):
            items += [('@paginasproo', 8, M.LIME, 40)]; key.append('handle')
        for (a, b, txt, col) in caps:
            if a <= t < b:
                dy = -2 if t - a < 0.07 else 0
                items.append((txt, 8, col, M.CAP_Y + dy)); key.append(txt + str(dy))
        if items:
            ti = M.text_cached('|'.join(key), items)
            al = ti[..., 3:4] / 255
            img = img * (1 - al) + ti[..., :3] * al
        if t > TOT - 0.7:
            img = img * max(0, (TOT - t) / 0.7)
        return np.clip(img, 0, 255).astype(np.uint8)

    if '--preview' in sys.argv:
        from PIL import Image
        for ts in sys.argv[sys.argv.index('--preview') + 1:]:
            Image.fromarray(frame(float(ts))).save(os.path.join(workdir, f'prev_{ts}.jpg'), quality=85)
        print(json.dumps([(round(s['t0'], 2), s['say']) for s in segs], ensure_ascii=False, indent=0))
        return

    # audio
    M.TOTAL = TOT
    M.CAP = caps
    M.FLASH = [s['t0'] + s['flash'] for s in segs if 'flash' in s]
    M.JINGLE_T = next(s['t0'] for s in segs if s.get('jingle'))
    mpath = os.path.join(workdir, 'music.wav')
    M.synth(mpath)
    mus, msr = sf.read(mpath, dtype='float32')
    voice = np.zeros(len(mus), np.float32)
    for s in segs:
        a, vsr = sf.read(s['wav'], dtype='float32')
        if vsr != msr:
            a = np.interp(np.arange(int(len(a) * msr / vsr)) * vsr / msr, np.arange(len(a)), a).astype(np.float32)
        st = int((s['t0'] + 0.1) * msr)
        a = a[:max(0, len(voice) - st)]
        voice[st:st + len(a)] += a
    env = np.convolve(np.abs(voice), np.ones(int(0.25 * msr)) / (0.25 * msr), mode='same')
    duck = 1 - 0.6 * np.clip(env / (env.max() * 0.25 + 1e-9), 0, 1)
    voice = voice / (np.abs(voice).max() + 1e-6) * 0.92
    mix = np.tanh((mus * duck[:, None] * 0.7 + voice[:, None]) * 1.1) * 0.95
    apath = os.path.join(workdir, 'mix.wav')
    sf.write(apath, mix, msr)

    tmp = out + '.tmp.mp4'
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{M.OW}x{M.OH}',
                          '-r', str(M.FPS), '-i', '-', '-i', apath, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                          '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', tmp],
                         stdin=subprocess.PIPE)
    for i in range(int(TOT * M.FPS)):
        p.stdin.write(frame(i / M.FPS).tobytes())
    p.stdin.close()
    if p.wait() == 0:
        os.replace(tmp, out)
        print('ok', round(TOT, 2), out)
    else:
        sys.exit('ffmpeg falhou')

if __name__ == '__main__':
    main()
