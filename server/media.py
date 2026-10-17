"""Análise local do vídeo com ffmpeg: metadados, miniaturas, forma de onda e silêncios.

Tudo aqui roda na sua máquina e não gasta nenhum token de IA.
"""
import array
import json
import re
import subprocess
from pathlib import Path


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(path: Path) -> dict:
    out = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe falhou: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if video is None:
        raise RuntimeError("O arquivo não tem trilha de vídeo.")
    width, height = int(video["width"]), int(video["height"])
    # Vídeos de celular costumam vir com rotação nos metadados.
    rotation = 0
    for sd in video.get("side_data_list", []):
        if "rotation" in sd:
            rotation = abs(int(sd["rotation"]))
    if "rotate" in video.get("tags", {}):
        rotation = abs(int(video["tags"]["rotate"]))
    if rotation in (90, 270):
        width, height = height, width
    num, den = (video.get("avg_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    return {
        "duration": float(data["format"]["duration"]),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "has_audio": audio is not None,
    }


def make_thumbnails(path: Path, out_dir: Path, every: float = 1.0) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-v", "error", "-y", "-i", str(path),
        "-vf", f"fps=1/{every},scale=-2:90", "-q:v", "6",
        str(out_dir / "t%05d.jpg"),
    ])
    return len(list(out_dir.glob("t*.jpg")))


def make_proxy(path: Path, out: Path) -> bool:
    """Cópia leve em H.264 para o preview tocar em qualquer navegador (inclusive vídeos HEVC de iPhone)."""
    res = run([
        "ffmpeg", "-v", "error", "-y", "-i", str(path),
        "-vf", "scale='if(gt(iw,ih),-2,min(540,iw))':'if(gt(iw,ih),min(540,ih),-2)',format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-g", "30",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out),
    ])
    return res.returncode == 0 and out.exists()


def waveform_peaks(path: Path, per_second: int = 20) -> list:
    """Picos de volume (0..1) para desenhar a forma de onda na timeline."""
    rate = 8000
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(rate),
         "-f", "s16le", "-"],
        capture_output=True,
    )
    samples = array.array("h", out.stdout[: len(out.stdout) // 2 * 2])
    step = rate // per_second
    peaks = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        peaks.append(max((abs(x) for x in chunk), default=0) / 32768)
    top = max(peaks, default=0) or 1
    return [round(p / top, 3) for p in peaks]


def detect_silences(path: Path, noise_db: int = -35, min_len: float = 0.35) -> list:
    out = run([
        "ffmpeg", "-hide_banner", "-i", str(path), "-vn",
        "-af", f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-",
    ])
    silences, start = [], None
    for line in out.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            silences.append([round(start, 3), round(float(m.group(1)), 3)])
            start = None
    return silences


def speech_ranges(duration: float, silences: list, min_len: float = 0.25) -> list:
    """O complemento dos silêncios: os trechos em que alguém está falando."""
    ranges, cursor = [], 0.0
    for s, e in silences:
        if s - cursor >= min_len:
            ranges.append([round(cursor, 3), round(s, 3)])
        cursor = e
    if duration - cursor >= min_len:
        ranges.append([round(cursor, 3), round(duration, 3)])
    return ranges
