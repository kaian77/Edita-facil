"""O "editor" de IA: o Claude lê a transcrição e devolve um plano de edição em JSON.

Por que isso gasta poucos tokens:
- O vídeo NUNCA é enviado para a IA. Só vai texto: a transcrição com tempos.
  Um vídeo de 1 minuto vira ~300 tokens.
- A IA devolve só decisões (quais trechos manter, zoom, textos). Legendas,
  cortes e renderização são feitos localmente pelo ffmpeg.
- A instrução fixa e a transcrição ficam em cache: pedidos seguidos no chat
  ("tira a parte do preço") reaproveitam o cache e custam ~10% do normal.
"""
import json

import anthropic

from . import brand as brandkit

MODELS = {
    # id: (nome, US$ por 1M tokens de entrada, US$ por 1M de saída)
    "claude-opus-5-5": ("Claude Opus 5.5 — melhor qualidade", 4.0, 20.0),
    "claude-sonnet-5-5": ("Claude Sonnet 5.5 — rápido e mais barato", 2.0, 10.0),
    "claude-haiku-5-5": ("Claude Haiku 5.5 — o mais econômico", 0.10, 0.50),
}
DEFAULT_MODEL = "claude-opus-5-5"

TEXT_STYLES = ["gancho", "titulo", "destaque", "rodape", "cta", "aviso", "pergunta", "isso_nisso", "produto", "rotina", "final"]
FORMATS = ["9:16", "16:9", "1:1", "4:5", "original"]

SYSTEM_PROMPT = """Você é um editor de vídeo profissional brasileiro, especialista em Reels, TikTok, Shorts e comerciais.

Você recebe a transcrição de um vídeo CRU, dividida em trechos numerados com tempos em segundos no formato:
#id [início-fim] texto falado
e devolve um PLANO DE EDIÇÃO. Você não vê as imagens: decida pelo que é falado e pelos tempos.

Como o plano funciona:
- clips: a lista ORDENADA de pedaços do vídeo original que vão para o vídeo final. Cada clip tem start/end em segundos do vídeo ORIGINAL. Normalmente cada clip é um trecho (#id) inteiro, mas você pode cortar só uma parte de um trecho (ex.: tirar uma palavra repetida no começo) ou juntar trechos vizinhos. Tudo que não estiver em clips é cortado. A ordem dos clips é a ordem do vídeo final (pode reordenar se o modelo pedir).
- zoom: 1.0 = normal. 1.05 a 1.25 = zoom de ênfase (corte seco, estilo Reels).
- label: nome curto da cena a que o clip pertence (ex.: "Gancho", "Problema", "CTA"). Clips seguidos com o mesmo label formam uma cena.
- texts: textos animados na tela. at_clip é o índice (começando em 0) do clip onde o texto aparece; offset é quantos segundos depois do começo daquele clip; duration é por quanto tempo fica. style: gancho (grande, topo), titulo (grande, centro), destaque (caixa colorida), rodape (faixa embaixo), cta (chamada final). Máximo 7 palavras por texto.
  Estilos especiais do formato "isso → nisso" (partes separadas por |):
  aviso ("Simulação com IA · não é consulta médica"; fica o vídeo todo, use quando houver antes/depois ou tema de saúde),
  pergunta ("Pergunta|Resposta", estilo caixinha de perguntas do Instagram, no começo),
  isso_nisso ("isso|nisso", dois quadros no topo para as imagens de antes e depois; dure de 5 a 9s),
  produto ("NOME DO PRODUTO OU AÇÃO|etiqueta1|etiqueta2|etiqueta3", o "use isso"; etiquetas curtas tipo manhã, noite, 2x ao dia),
  rotina ("Sua rotina|item1|item2|item3", checklist que vai sendo marcado; perto do fim),
  final ("@perfil|frase curta", tela final escurecida com o @; últimos 2–3s). As legendas do que é falado são geradas automaticamente: NÃO repita a fala inteira em texts.
- scenes: uma linha por cena para mostrar ao usuário o que você fez (title curto + desc de 1 frase explicando a decisão).
- summary: 1 ou 2 frases, em português, dizendo o que você fez. Fale com o usuário, sem jargão técnico.

Regras:
- Nunca invente falas: você só pode usar trechos que existem.
- Corte silêncios, "é...", "hã", gaguejadas, frases recomeçadas (fique com a melhor tentativa, normalmente a última) e repetições.
- Não deixe um clip com menos de 0.4s, e não corte no meio de uma palavra.
- Se o modelo tiver duração máxima, respeite.
- Se o usuário pedir uma alteração, parta do plano atual e mude só o que foi pedido."""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "format": {"type": "string", "enum": FORMATS},
        "captions": {"type": "boolean"},
        "music": {"type": "boolean"},
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "zoom": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["start", "end", "zoom", "label"],
                "additionalProperties": False,
            },
        },
        "texts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "at_clip": {"type": "integer"},
                    "offset": {"type": "number"},
                    "duration": {"type": "number"},
                    "style": {"type": "string", "enum": TEXT_STYLES},
                },
                "required": ["text", "at_clip", "offset", "duration", "style"],
                "additionalProperties": False,
            },
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "desc": {"type": "string"},
                },
                "required": ["title", "desc"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "format", "captions", "music", "clips", "texts", "scenes"],
    "additionalProperties": False,
}


class AIError(Exception):
    pass


def transcript_block(transcript: dict, info: dict) -> str:
    lines = [
        f"VÍDEO: {info['duration']:.1f}s, {info['width']}x{info['height']}",
        "TRANSCRIÇÃO:" if transcript["source"] == "whisper"
        else "TRECHOS COM FALA (sem transcrição disponível, só os tempos):",
    ]
    for seg in transcript["segments"]:
        text = seg["text"] or "(fala)"
        lines.append(f"#{seg['id']} [{seg['start']:.2f}-{seg['end']:.2f}] {text}")
    return "\n".join(lines)


def preset_block(preset: dict) -> str:
    limit = (f"Duração máxima do vídeo final: {preset['max_seconds']}s."
             if preset.get("max_seconds") else "Sem limite de duração.")
    return (
        f"MODELO DE EDIÇÃO: {preset['name']}\n{preset['instructions']}\n{limit}\n"
        f"Formato sugerido: {preset['format']}. "
        f"Legendas: {'sim' if preset['captions']['enabled'] else 'não'}. "
        f"Música de fundo: {'sim' if preset.get('music_volume') else 'não'}."
    )


def compact_plan(timeline: dict) -> str:
    """O plano atual em JSON enxuto, para pedidos de alteração no chat."""
    clips = timeline["clips"]
    starts = {c["id"]: i for i, c in enumerate(clips)}
    plan = {
        "format": timeline["format"],
        "captions": timeline["captions"]["enabled"],
        "music": timeline["music"]["enabled"],
        "clips": [
            {"start": c["src_in"], "end": c["src_out"], "zoom": c["zoom"], "label": c["label"]}
            for c in clips
        ],
        "texts": [
            {"text": t["text"], "at_clip": starts.get(t.get("clip_id"), 0),
             "offset": round(t.get("offset", 0), 2), "duration": round(t["end"] - t["start"], 2),
             "style": t["style"]}
            for t in timeline["texts"]
        ],
    }
    return json.dumps(plan, ensure_ascii=False, separators=(",", ":"))


def request_plan(config: dict, transcript: dict, info: dict, preset: dict,
                 user_request: str = "", current_timeline: dict | None = None) -> tuple[dict, dict]:
    tail = [preset_block(preset)]
    if brand_text := brandkit.prompt_block():
        tail.append(brand_text)
    if current_timeline is not None:
        tail.append("PLANO ATUAL:\n" + compact_plan(current_timeline))
    tail.append("PEDIDO DO USUÁRIO: " + (user_request.strip() or "Edite o vídeo seguindo o modelo."))

    content = [
        # Bloco estável primeiro e marcado para cache: os próximos pedidos do chat
        # sobre o mesmo vídeo pagam só ~10% por ele.
        {"type": "text", "text": transcript_block(transcript, info),
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "\n\n".join(tail)},
    ]
    return call_json(config, SYSTEM_PROMPT, content, PLAN_SCHEMA)


def call_json(config: dict, system: str, content: list, schema: dict) -> tuple[dict, dict]:
    """Uma chamada ao Claude que devolve JSON validado pelo schema + o relatório de gasto."""
    api_key = config.get("api_key")
    if not api_key:
        raise AIError("Coloque sua chave da API da Anthropic em ⚙️ Configurações.")
    model = config.get("model") or DEFAULT_MODEL
    if model not in MODELS:
        model = DEFAULT_MODEL
    params = dict(
        model=model,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": content}],
        thinking={"type": "adaptive"},
        output_config={
            "effort": config.get("effort") or "medium",
            "format": {"type": "json_schema", "schema": schema},
        },
    )
    if model != "claude-haiku-5-5":
        # Se o modelo recusar por engano, a API tenta outro modelo automaticamente.
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"

    client = anthropic.Anthropic(api_key=api_key)
    try:
        if "betas" in params:
            response = client.beta.messages.create(**params)
        else:
            response = client.messages.create(**params)
    except anthropic.AuthenticationError:
        raise AIError("Chave da API inválida. Confira em ⚙️ Configurações.")
    except anthropic.PermissionDeniedError:
        raise AIError("Sua chave não tem permissão para esse modelo.")
    except anthropic.RateLimitError:
        raise AIError("Limite de uso da API atingido. Espere um pouco e tente de novo.")
    except anthropic.BadRequestError as exc:
        raise AIError(f"A API recusou o pedido: {exc.message}")
    except anthropic.APIStatusError as exc:
        raise AIError(f"Erro na API ({exc.status_code}). Tente de novo em instantes.")
    except anthropic.APIConnectionError:
        raise AIError("Sem conexão com a API. Verifique sua internet.")

    if response.stop_reason == "refusal":
        raise AIError("A IA recusou esse pedido. Tente reformular.")
    if response.stop_reason == "max_tokens":
        raise AIError("A resposta da IA ficou grande demais. Tente um pedido mais simples.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise AIError("A IA respondeu num formato inesperado. Tente de novo.")
    return data, usage_report(response.model or model, response.usage)


def usage_report(model: str, usage) -> dict:
    _name, price_in, price_out = MODELS.get(model, MODELS[DEFAULT_MODEL])
    fresh = usage.input_tokens or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    out = usage.output_tokens or 0
    cost = (fresh * price_in + cache_write * price_in * 1.25
            + cache_read * price_in * 0.1 + out * price_out) / 1_000_000
    return {
        "model": model,
        "input_tokens": fresh + cache_write + cache_read,
        "cached_tokens": cache_read,
        "output_tokens": out,
        "cost_usd": round(cost, 5),
    }
