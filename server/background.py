"""Troca de fundo: separa a pessoa do fundo quadro a quadro (MediaPipe, no seu PC).

A pessoa NÃO é alterada: os pixels do rosto e do corpo são copiados do vídeo original,
e a voz é o áudio original. Só o que é fundo é trocado (desfoque, cor, imagem ou a marca).
"""
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "data" / "models" / "selfie_segmenter.tflite"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/image_segmenter/"
             "selfie_segmenter/float16/latest/selfie_segmenter.tflite")
MODES = ["desfoque", "cor", "imagem", "marca"]


def available() -> bool:
    try:
        import cv2  # noqa: F401
        import mediapipe  # noqa: F401
        return True
    except ImportError:
        return False


def _ensure_model():
    if not MODEL.exists():
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, MODEL)


def _hex_bgr(h: str):
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def _background(mode, w, h, color, image_path, brand_colors):
    import cv2
    import numpy as np

    if mode == "cor":
        return np.full((h, w, 3), _hex_bgr(color or "#111111"), np.uint8)
    if mode == "imagem" and image_path and Path(image_path).exists():
        img = cv2.imread(str(image_path))
        ih, iw = img.shape[:2]
        s = max(w / iw, h / ih)
        img = cv2.resize(img, (int(iw * s) + 1, int(ih * s) + 1), interpolation=cv2.INTER_AREA)
        y0, x0 = (img.shape[0] - h) // 2, (img.shape[1] - w) // 2
        return img[y0:y0 + h, x0:x0 + w].copy()
    if mode == "marca":
        a = np.array(_hex_bgr(brand_colors["primary"]), np.float32) * 0.6
        b = np.array(_hex_bgr(brand_colors["secondary"]), np.float32) * 0.5
        t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        grad = (a * (1 - t) + b * t).repeat(w, axis=1)
        return grad.astype(np.uint8)
    return None  # desfoque: calculado por quadro


def replace(source: Path, out: Path, info: dict, mode: str = "desfoque", color: str = "#111111",
            image_path: Path | None = None, brand_colors: dict | None = None, on_progress=None) -> Path:
    import cv2
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    _ensure_model()
    w, h = info["width"], info["height"]
    fps = info["fps"] if 10 < info["fps"] < 61 else 30
    total_frames = max(1, int(info["duration"] * fps))
    bg_static = _background(mode, w, h, color, image_path, brand_colors or {})

    options = vision.ImageSegmenterOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        output_confidence_masks=True,
        output_category_mask=False,
    )
    decoder = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(source), "-f", "rawvideo", "-pix_fmt", "bgr24", "-r", str(fps), "-"],
        stdout=subprocess.PIPE,
    )
    encoder = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps),
         "-i", "-", "-i", str(source), "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-shortest", str(out)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    frame_bytes = w * h * 3
    prev = None
    n = 0
    try:
        with vision.ImageSegmenter.create_from_options(options) as segmenter:
            while True:
                raw = decoder.stdout.read(frame_bytes)
                if len(raw) < frame_bytes:
                    break
                frame = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = segmenter.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(n * 1000 / fps))
                mask = res.confidence_masks[0].numpy_view().astype(np.float32)
                if mask.shape[:2] != (h, w):
                    mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
                # suaviza no tempo (menos tremido) e nas bordas (recorte natural)
                prev = mask if prev is None else prev * 0.35 + mask * 0.65
                m = cv2.GaussianBlur(prev, (0, 0), max(1.0, w / 500))
                m = np.clip((m - 0.25) / 0.5, 0, 1)[:, :, None]
                bg = bg_static if bg_static is not None else cv2.GaussianBlur(frame, (0, 0), max(8, w / 45))
                outf = frame * m + bg * (1 - m)
                encoder.stdin.write(outf.astype(np.uint8).tobytes())
                n += 1
                if on_progress and n % 10 == 0:
                    on_progress(min(0.99, n / total_frames))
    finally:
        decoder.stdout.close()
        decoder.wait()
        encoder.stdin.close()
        err = encoder.stderr.read().decode("utf-8", "replace")
        code = encoder.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg falhou: {err[-500:]}")
    return out
