# Cidade Pro — série do @paginasproo

Cada seguidor vira uma loja numa cidade em pixel art. Quem comenta o nome do negócio
ganha uma loja com o nome na fachada no episódio seguinte. Narração: Kokoro (gratuita, voz `pm_alex`).

## Arquivos
- `engine/make.py` — arte da cidade, textos, cena 3D, música (biblioteca)
- `engine/episode.py` — gera um episódio a partir de um spec JSON
- `state.json` — episódios publicados, lojas com nome, comentários já usados
- `episodios/epNN.mp4` — vídeos prontos (o Social Studio importa pelo link raw do GitHub)

## Gerar um episódio
```bash
pip install --break-system-packages kokoro-onnx soundfile num2words pillow numpy
mkdir -p kokoro && cd kokoro
curl -sSLO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -sSLO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
cd ..
python3 engine/episode.py spec.json episodios/ep02.mp4            # vídeo final
python3 engine/episode.py spec.json /tmp/x.mp4 --preview 1 5 9     # quadros soltos para conferir
```
spec: `{"episode": 2, "followers": 19, "named_before": ["..."], "new": ["Barbearia do Zé"]}`

Link público do vídeo: `https://raw.githubusercontent.com/kaian77/edita-facil/cidade-pro/episodios/ep02.mp4`
