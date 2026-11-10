# Recon map: SlowRead: Book Tracker & TBR (iOS)

Escopo: a estante visual (livros em pé e deitados, capas e lombadas, decoração, temas), adicionar livros (busca, código de barras, foto da lombada), onboarding e paywall. Fora: comunidade, Apple Watch, bloqueio de apps.
Para: um produto próprio para vender, com nome, arte e textos novos (proposta: Android + iOS, em português, que o original não cobre bem).
Data: 2026-11-10

## Fontes

| # | fonte | URL | notas |
| --- | --- | --- | --- |
| 1 | 17 capturas de um vídeo do Instagram (análise de um criador) | enviadas pelo usuário, não versionadas | widget, estante, scanner, editor, paywall, 6 telas de onboarding, 2 TikToks do app |
| 2 | Listagem espelhada da App Store | https://mwm.ai/apps/slowread-book-tracker-tbr/6763293288 | lida só pelo resumo da busca; o host está bloqueado nesta sessão |
| 3 | Página de suporte do desenvolvedor | https://sites.google.com/view/sup-slowread | idem: só o resumo da busca |
| 4 | App Store | https://apps.apple.com/app/id6763293288 | não aberta; ID tirado da fonte 2 |

O que as fontes 2 e 3 dizem (pelo resumo da busca, conferir na loja): desenvolvedor individual (Adrian Martinez Moreno), lançado em 4 jul 2026, estante descrita como "2.5D", busca em várias bases de livros, código de barras ou foto da lombada, temas Cottagecore e Dark Academia, dados guardados no aparelho, sessão de foco com bloqueio de apps no plano Pro.

Não vistos: central de ajuda completa, changelog, o app rodando. Tudo abaixo marcado "palpite" vem só das capturas.

## Core loop

Adicionar um livro e vê-lo aparecer numa estante bonita que é sua, que você decora e mostra (widget na tela inicial, vídeo no TikTok).

## Telas

| ID | tela | como chegar | propósito | componentes | estados vistos |
| --- | --- | --- | --- | --- | --- |
| S01 | Onboarding: nome | abrir o app pela 1ª vez (passo 4) | "What's your name? It goes on your shelf" | campo de texto, botão primário, barra de progresso em 3 trechos, voltar | vazio; com o pedido de rastreamento (ATT) por cima |
| S02 | Onboarding: livros por ano | passo 6 | medir o hábito | número grande, slider 1 a 52+, mini prateleira que enche conforme o slider | 12 livros |
| S03 | Onboarding: projeção | passo 8 | "Erick, that's 450 books in ten years" | emoji, frase com nome, cartão com 2 números (horas/ano, minutos/dia), frase de transição | preenchido |
| S04 | Onboarding: estante exemplo | passo ~10 | "Want one like this?" | estante cheia de demonstração, botão "Build mine" | preenchido |
| S05 | Onboarding: escolher parede e prateleira | passo 11 | "Where should it live" | prévia da estante com silhuetas pontilhadas de livros, seletor de tema | vazio |
| S06 | Onboarding: decorar | passo ~14 | primeiro contato com decoração | prévia, bandeja de categorias (Nature, Light, Time), busca, "Not now" | vazio |
| S07 | Onboarding: nome da estante | passo 15 | "What do you call it?" | prévia com título ao vivo e "0 books", campo, continuar | padrão "My library" |
| S08 | Onboarding: lembrete de leitura | passo 25 | pedir notificação | prévia de tela de bloqueio com a notificação, horário com liga/desliga, "Add a reading time", "Allow notifications" | 19:30 todo dia |
| S09 | Paywall | fim do onboarding | vender o Pro | estante com a plaquinha do nome do usuário, lista de benefícios, 3 planos (anual USD 9 com teste de 3 dias, semanal USD 1,99, vitalício USD 35), "No payment now", botão "Try for Free", Restore, Redeem code, Terms, Privacy | anual selecionado |
| S10 | Estante (Library) | aba Library | a tela principal | fundo texturizado, prateleiras de madeira, livros de lombada, livros de capa, pilhas deitadas, decoração, cordão de luzes, barra de abas flutuante | cheia; vazia não vista |
| S11 | Estante em modo edição | segurar um livro ou botão de editar | arrumar e decorar | dica "Hold & drag to move · tap to style", "Done", ferramentas Move, Arrange, Decorate, Backdrop, Shelf | Move ativo |
| S12 | Folha do livro (estilo) | tocar num livro em edição | mudar como o livro aparece | título, seção "Appearance" (palpite: capa de frente, lombada, deitado, trocar foto) | parcial |
| S13 | Bandeja de decoração | Decorate | escolher enfeite | abas Recents, Photos, Favorites, Nature..., busca, grade de itens, "+ Photo" e molduras (Walnut, Oval, Hanging, Polaroid) | aba Photos |
| S14 | Scanner de lombada | adicionar livro > foto | fotografar a lombada | câmera, guia vertical pontilhada, "Point at a spine, or just tap to capture", botão de disparo, fechar | apontando |
| S15 | Seletor de estante | título no topo ("TBR 💕 ⌄") | trocar entre estantes | nome, contagem de livros, menu | fechado |
| S16 | Widget de tela inicial | iOS, adicionar widget | mostrar a estante fora do app | tamanho grande (2 prateleiras) e médio (1 prateleira) | preenchido |
| S17 | Animação "DNF" (abandonei) | marcar livro como abandonado | momento compartilhável | capa pega fogo, vira cinza e some em partículas; título e autor embaixo | 3 quadros vistos |
| S18 | Abas Home, Books, Stats, Profile | barra de abas | início, lista, estatísticas, perfil | só os rótulos foram vistos | não vistas (palpite) |

## Fluxos

```
F01 Primeiro uso até o paywall
    S01 -> S02 -> S03 -> S04 -> S05 -> S06 -> S07 -> ... -> S08 -> S09
    toques no caminho feliz: cerca de 27 passos (o contador das capturas chega a 27)
    bordas: recusa do rastreamento, recusa da notificação, "Not now" na decoração, fechar o paywall

F02 Adicionar um livro pela lombada
    S10 -> adicionar -> S14 -> (recorte e identificação) -> livro na S10
    toques: 3 a 4 (palpite)
    bordas: lombada ilegível, livro não achado na base, câmera negada, sem internet

F03 Adicionar por busca ou código de barras
    S10 -> adicionar -> busca/scanner -> escolher resultado -> S10
    bordas: várias edições do mesmo título, sem capa disponível

F04 Arrumar e decorar
    S10 -> S11 -> arrastar livro / S12 / S13 / Backdrop / Shelf -> Done
    bordas: prateleira cheia, enfeite por cima de livro, desfazer

F05 Terminar ou abandonar um livro
    S10 -> livro -> mudar estado -> S17 (se DNF) -> S10
    bordas: reverter o estado

F06 Assinar
    S09 -> escolher plano -> compra da loja -> app liberado
    bordas: compra cancelada, restaurar, código promocional
```

## Componentes

| componente | variantes | estados | usado em |
| --- | --- | --- | --- |
| Botão | primário cheio (pílula), secundário | padrão, pressionado, desativado | todas |
| Barra de progresso do onboarding | 3 trechos | parcial | S01 a S08 |
| Campo de texto | simples, centralizado | vazio, preenchido | S01, S07 |
| Slider com número | 1 a 52+ | arrastando | S02 |
| Cartão de estatística | 2 colunas + rodapé | preenchido | S03 |
| Livro na estante | lombada, capa de frente, deitado em pilha | parado, arrastando, selecionado | S04, S10, S11, S16 |
| Prateleira | madeira clara, madeira escura, entalhada | vazia (silhuetas), cheia | S05, S10 |
| Fundo (backdrop) | tricô, madeira, papel floral, veludo | n/a | S10, S11 |
| Enfeite | planta, vela, gato, folhas, candelabro, moldura com foto | parado, arrastando | S10, S13 |
| Cordão de luzes | por prateleira | ligado | S10 |
| Barra de ferramentas de edição | 5 ferramentas | ativa, inativa | S11 |
| Folha inferior | meia altura, alta | arrastável | S12, S13 |
| Barra de abas flutuante | 5 abas | ativa, inativa | S10, S18 |
| Cartão de plano | anual, semanal, vitalício | selecionado, selo de teste grátis | S09 |
| Lista de benefícios | ícone + título + subtítulo | n/a | S09 |
| Widget | médio, grande | preenchido | S16 |

## Modelo de dados inferido

```
Book        id, title, author, isbn, cover_image, spine_image, spine_color,
            pages, status (tbr | reading | read | dnf), rating, added_at, finished_at
            evidência: S10, S12, S14, S17, fonte 3 (quero ler / lendo / lido)
            confiança: alta nos campos básicos, palpite em rating e pages

Shelf       id, name, backdrop_id, shelf_style_id, theme_id, position
            evidência: S07, S15 ("TBR 💕"), S11 (Backdrop, Shelf)
            confiança: alta

Placement   id, shelf_id, book_id, row, order, display (spine | cover | stacked)
            evidência: S10 mostra o mesmo acervo com capas, lombadas e pilhas; S11 "Hold & drag"
            confiança: média (pode ser posição livre x,y em vez de ordem)

Decoration  id, shelf_id, asset_id, row, x, scale, photo (para molduras)
            evidência: S13
            confiança: média

Asset       id, kind (decoration | backdrop | shelf), category, name, premium
            evidência: S13 categorias, S09 "Every theme and decoration unlocked"
            confiança: alta

Profile     name, books_per_year, minutes_per_day, reminder_times[]
            evidência: S01, S02, S03, S08
            confiança: alta

Entitlement plan (yearly | weekly | lifetime), trial_ends_at, active
            evidência: S09
            confiança: alta

ReadingSession  book_id, started_at, minutes, pages
            evidência: aba Stats, "Stats & Wrap Ups" no paywall
            confiança: palpite
```

Relações: Profile 1-n Shelf, Shelf 1-n Placement, Book 1-n Placement, Shelf 1-n Decoration, Asset 1-n Decoration, Book 1-n ReadingSession.

Armazenamento: local no aparelho (fonte 3). Conta e servidor só entram com a parte de comunidade.

## Como o "3D" é feito (inferência das capturas)

Não é um motor 3D. A própria listagem chama de "2.5D": imagens planas empilhadas em camadas.

- Lombada: uma imagem retangular estreita (foto recortada do scanner, ou gerada a partir da capa: cor dominante + título em pé).
- Capa de frente: a capa plana, com uma faixa fina de lombada ao lado e sombra, o que dá a sensação de volume.
- Altura e largura variam por livro (largura proporcional ao número de páginas é o palpite).
- Prateleira, fundo e enfeites são PNGs com transparência; a sombra projetada faz o resto.
- A animação de fogo do DNF é um efeito de partículas/shader sobre a capa.

## Matriz de recursos

Ver `features.csv`. Must: 14, should: 11, could: 6, skip: 5.

## Fora de escopo (não dá ou não se deve copiar)

- O nome SlowRead, o ícone, os textos e as frases do onboarding e do paywall.
- A arte deles: fundos, prateleiras, enfeites, molduras. Precisa de arte nova (ilustrador, banco com licença comercial ou geração própria).
- As capturas de tela e os vídeos de divulgação.
- Capas de livro: são das editoras. O caminho normal é buscá-las por API pública (Open Library, Google Books) e deixar o usuário fotografar as suas; não empacotar capas no app.
- A audiência do TikTok e a comunidade de leitores deles.
- Apple Watch e bloqueio de apps: fora da primeira versão por custo, não por impedimento.

## Tamanho

Telas 18, fluxos 6, entidades 8.
Partes difíceis: (1) o desenho da estante com arrastar e soltar suave entre prateleiras; (2) lombada a partir de foto: recortar, endireitar e identificar o livro; (3) o volume de arte original (temas, enfeites) que é o que vende o app; (4) widget nativo de tela inicial; (5) assinatura pelas lojas.
Tamanho: M para a fatia central (estante + adicionar + temas + paywall), L com widget, estatísticas e comunidade.
