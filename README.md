# Edita Fácil 🎬

Editor de vídeo com IA (Claude) que roda no seu computador. Você manda o vídeo **cru**, escolhe um
modelo pronto e a IA corta pausas, monta as cenas, coloca legendas animadas, zoom, textos e música.
Depois é só pedir ajustes no chat: _"corta a parte que eu falo do preço"_.

## Como abrir (jeito fácil)

1. Baixe o projeto: no GitHub, botão verde **Code → Download ZIP**, e descompacte.
2. Dê **dois cliques** em:
   - Windows: `Iniciar-Windows.bat`
   - Mac: `Iniciar-Mac.command` (se o Mac bloquear: botão direito → Abrir)
   - Linux: `iniciar-linux.sh`

   Na primeira vez ele instala tudo sozinho (Python, ffmpeg e as bibliotecas). Pode levar alguns minutos.
   Se pedir, feche e abra de novo. Depois disso, abre direto.
3. O navegador abre o editor. Clique em ⚙ e cole sua chave da Anthropic (console.anthropic.com → API Keys).

## Usar no celular

**Em casa (mesmo Wi-Fi):** no PC, clique em **📱 Celular** no topo do editor e aponte a câmera do celular
para o QR code. Digite o PIN que aparece. Pronto: abre a versão simples para celular.
Dica: no celular, **Compartilhar → Adicionar à Tela de Início** e ele vira um app com ícone.

No celular é só: escolher o vídeo da galeria → escolher o estilo → **Editar sozinho**. O computador faz o
trabalho pesado; você pode fechar o app e voltar depois em **Meus vídeos**, e então **Compartilhar** direto
no Instagram/TikTok ou **Baixar**. O PC precisa estar ligado com o Edita Fácil aberto.

**Fora de casa (pela internet):** coloque o app num servidor na nuvem usando o `Dockerfile` que já vem pronto
(Render, Railway ou Fly.io aceitam). Configure:
- variável `APP_PASSWORD` = a senha que você vai digitar no celular (obrigatório, protege suas chaves);
- um disco persistente montado em `/storage` (onde ficam vídeos, marca e chaves).

Atenção: servidor na nuvem é pago (algo como US$ 7 a 25 por mês) e, nos planos baratos, a transcrição e a
exportação ficam mais lentas que no seu PC.

## Instalação manual (se preferir)

Python 3.10+ e ffmpeg instalados, depois: `pip install -r requirements.txt` e `python -m server`.

## Por que gasta pouco

- **O vídeo nunca vai para a IA.** A fala é transcrita no seu PC (faster-whisper, grátis) e só o texto vai pro Claude.
  1 minuto de vídeo ≈ 300 tokens.
- A IA devolve só as **decisões** (o que cortar, onde dar zoom, quais textos). Legendas, cortes e a exportação são
  feitos pelo ffmpeg no seu PC.
- A transcrição fica em **cache**: cada pedido no chat sobre o mesmo vídeo custa ~10% do primeiro.
- O gasto aparece no painel do Claude. Um Reels de 1 minuto custa em torno de **US$ 0,01 a 0,05** com o Opus 5.5;
  troque para Sonnet 5.5 ou Haiku 5.5 em ⚙ se quiser gastar ainda menos.

## As telas

- **Editor** — manda o vídeo cru, escolhe o modelo, a IA edita. Ajustes pelo chat ou na timeline.
  Painel **Fundo**: troca o fundo (desfoque, cor, imagem ou cores da marca) sem mexer no rosto nem na voz.
- **✦ Criar com IA** — sem gravar nada: escreva o tema e a IA faz roteiro, narração (com a sua voz clonada),
  animações com giro 3D, números, listas e a sua marca. Ou mande um vídeo que você gostou e a IA copia o
  **estilo** (estrutura, gancho, ritmo) para os seus temas.
- **Minha marca** — nome, @, nicho, tom, cores, logo, avatar e voz. Fica salvo e a IA usa sempre.

## Chaves (⚙ no editor)

- **Anthropic** (obrigatória): console.anthropic.com → API Keys.
- **ElevenLabs** (opcional, para narrar e clonar voz): elevenlabs.io → Developers → API Keys.
  Clone só a sua voz ou de quem autorizou.

## Modelos prontos

| Modelo | Para quê |
|---|---|
| 🔥 Reels Viral | Jump cuts, legenda com palavra destacada, zoom de ritmo, gancho |
| ◻️ Comercial estilo Apple | Minimalista, textos grandes, ritmo calmo |
| ✨ Profissional: Isso → Nisso | O formato viral: caixinha de pergunta, quadros isso → nisso com antes/depois, card "use isso" com o produto, checklist e tela final com @ |
| 🎙️ Corte de Podcast | Acha o melhor trecho de 30–60s |
| 🎓 Aula / Tutorial | Mantém tudo, só limpa erros e silêncios |
| 🧹 Só limpar | Remove silêncios e repetições, sem efeitos |

Para criar o seu, copie um arquivo de `server/presets/` e mude as instruções — ou use **Copiar um vídeo que gostei**.

No formato isso → nisso, as imagens de antes e depois você escolhe no painel **Ajustes** ao clicar no elemento na timeline.

## Atalhos no editor

`Espaço` play/pause · `S` dividir · `Delete` apagar · `Z` zoom no clip · `Ctrl+Z` desfazer · `←/→` quadro a quadro

## Estrutura

```
server/   backend (FastAPI): análise, transcrição, IA, renderização ffmpeg (fontes Inter em server/fonts)
web/      interface do editor (HTML/CSS/JS puro, sem build); celular.html = versão simples para celular
projects/ seus projetos (vídeos, timeline) — fica só no seu PC
data/     sua marca, estilos copiados e modelos baixados
music/    suas músicas de fundo
```
