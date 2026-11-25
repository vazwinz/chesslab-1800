# Revisão intensivão: a revisão de partidas que treina

*Design para aprovação do dono (2026-11-24). Escrito em português porque o leitor agora é ele; README e ROADMAP continuam em inglês.*

## Intenção

O dono quer a análise de partidas "melhor que a do chess.com", e o AURA é um intensivão: cada minuto tem que render aprendizado. O Game Review do chess.com é bom para **ver** uma partida: gráfico, treinador falando, momentos-chave, Retry e 10 etiquetas. Mas o erro some depois que você vê. O AURA ganha transformando a revisão em **treino com retorno**:

- você tenta antes de ver;
- recebe a resposta na hora;
- o que errou volta nos dias seguintes;
- cada dia termina com uma regra prática.

Contexto que pesa:
- Ele joga umas 10 rápidas por dia no chess.com, e o rating subiu de ~800 para ~1064 em 2,5 semanas de AURA.
- A rotina é cumprida pela metade.
- O passo "Partidas contra o AURA" quase não é usado.
- O treino de erros de partida já é a parte mais usada (179 de 393 exercícios).

## Metas

1. O modo **"Seus erros de partida"** (o nome fica, decisão do dono) passa a começar pela **sessão do dia**: os 5 momentos mais valiosos das partidas do dia, de partidas diferentes e misturados, em ~10 min.
2. Cada momento começa com **você tentando** achar o lance. Depois vem um toque de **"certeza ou chute?"** e a **resposta logo em seguida**, com a ideia encenada no tabuleiro.
3. O momento **volta em 1, 3, 7 e 21 dias**, até ficar firme.
4. O dia termina com **1 regra "se… então"** tirada do seu padrão de erro, mostrada de novo no dia seguinte.
5. Mostrar **onde você gastou pouco tempo num lance que decidiu a partida**.
6. Depois, na fase 3: "onde você acha que perdeu?" antes do motor, e uma revisão de partida com gráfico clicável, precisão por fase e "próximo momento".

## Não-metas

- Copiar as 10 etiquetas do chess.com, a "Game Rating" ou o treinador em voz. Pesam na cabeça e não ensinam; voz junto com texto atrapalha.
- Exigir IA. Tudo sai de regras e do Stockfish. A IA local (Ollama) pode reescrever textos depois, como camada opcional.
- Mudar o critério de julgamento da 0.5.2.

## Anti-metas (falhou mesmo funcionando, se…)

- a revisão do dia passar de ~12 min ou virar mais um passo arrastado na rotina;
- mostrar a resposta antes da tentativa, ou deixar pular a tentativa por padrão;
- a sessão do dia virar um **modo novo ao lado** de "Seus erros de partida" em vez de morar dentro dele (regra do dono: substituir, não empilhar);
- o app atrasar ou travar o botão Atualizar agora por causa da análise automática.

## Base científica (o porquê de cada peça)

| Peça | Princípio | Força |
|---|---|---|
| Tentar antes de ver | Efeito do pré-teste: a tentativa, mesmo errada, melhora o que se guarda da resposta (Richland, Kornell & Kao 2009; Kornell, Hays & Bjork 2009). A resposta tem que vir **logo depois**: com atraso o ganho some (Grimaldi & Karpicke 2012) | forte |
| Voltar em 1, 3, 7 e 21 dias | Testar e espaçar são as duas técnicas mais bem avaliadas (Dunlosky et al. 2013) | forte |
| "Certeza ou chute?" | Hipercorreção: erro cometido com certeza é corrigido com mais força (Butterfield & Metcalfe 2001) | forte |
| Encenar a ideia depois da tentativa | Exemplo resolvido depois de tentar (falha produtiva, Kapur); um motivo por vez pela carga de memória de trabalho (Sweller) | média a forte |
| Misturar momentos de partidas diferentes | Misturar tipos de problema treina escolher qual ideia serve (Rohrer & Taylor 2007) | média |
| Tempo × peso do lance | Pensar mais melhora o lance em todos os níveis (Moxley et al. 2012; alcance limitado segundo o estudo de 2023) | média |
| Regra "se… então" | Planos de implementação mudam comportamento (Gollwitzer & Sheeran 2006). No xadrez é inferência | forte em geral |
| "Onde você acha que perdeu?" | Conselho de treinador (Dvoretsky, Heisman) e calibração metacognitiva; sem estudo de xadrez | fraca, por isso fica leve e na fase 3 |

## Abordagens consideradas

- **A. Igualar o chess.com:** gráfico, momentos-chave, Retry, encenação, chance perdida, abertura, fases, tempo e Game Rating. É conhecido, mas termina empatado e não usa a vantagem do AURA, que é o treino com retorno.
- **B. Revisão que treina, em versão intensivão (escolhida pelo dono):** revisão do dia misturada, tentativa antes, retorno espaçado e regra do dia. Usa o que a ciência sustenta e cabe em 10 min.
- **C. Treinador por IA, com texto e voz:** no teste com o gemma3 a IA trocou o sentido de um lance, então não pode ser a base. Fica como camada opcional futura.

## Como funciona hoje (o que o design toca)

- **Erros de partida:** a análise (`games.analyze_game`) julga só os lances do dono, com `judgement.score_move` na profundidade 18. Guarda `GameMistake` (`fen_before`, melhor lance, `win_pct_loss`, `severity`, `think_s`, `clock_s`, `category` do Error DNA, `pv`) e `Game.metrics` (precisão, contagens, destaques, `phase_acpl`, mediana de tempo).
  - A curva de chance de vitória (`wins`) é calculada para a precisão, mas **não é guardada**.
  - O tempo de cada lance só fica guardado para os erros.
- **Treino de erros:** `trainer.own_mistake_pool` serve erros e capivaradas, os mais novos primeiro, pulando os servidos nos últimos 3 dias. Posições de partida ficam **fora** do agendador espaçado, que funciona por conceito (`retention`). Não existe retorno por posição.
- **Rotina:** o passo `own_mistakes` ("Seus erros de partida", 5 posições, ou 3 no dia leve) é contado por sessões de treino desse tipo.
- **Chess.com:** o import é manual (`game_jobs.enqueue_chesscom`). O usuário fica salvo em `prefs.chesscom_username`. A análise roda numa fila em segundo plano, e o **Atualizar agora recusa enquanto ela roda**.

## O design

### 1. Partidas do dia chegam sozinhas

- Ao abrir o app, e no máximo 1 vez por hora enquanto ele estiver aberto, baixar o mês atual de `chesscom_username` (se estiver preenchido), importar as partidas novas e pôr na fila de análise, as mais recentes primeiro. Sem usuário salvo, nada muda.
- **Depende do ponto 1** (análise em duas passadas): uma passada rápida (profundidade 12) deixa as partidas revisáveis em segundos; a passada profunda (18) refina depois, só nos lances que importam. Enquanto a profunda não chega, os momentos saem da rápida e são recalculados quando ela termina. Momento já respondido não muda.
- **Depende do ponto 2**: com análise automática, o Atualizar agora tem que **pausar a fila e atualizar** em vez de recusar. A fila continua sozinha depois, porque cada partida sabe o que falta.
- Um interruptor em Configurações ("Buscar minhas partidas do Chess.com ao abrir") vem ligado quando já existe usuário salvo. Nos 2 primeiros dias do mês, o mês anterior também é baixado.

**Análise em duas passadas (ponto 1), em detalhe.**
- **Passada rápida:** profundidade 12, como era antes da 0.5.2, em todos os lances do dono. Grava tudo (métricas, erros, `wins`, `think`) e marca `metrics["deep"] = "pending"`.
- **Passada profunda:** profundidade 18, só nos lances em que a rápida viu queda de 3 pontos de chance ou mais, nos candidatos a ! e !!, nos lances com captura ou xeque, e nos lances logo depois de um erro do adversário (para achar chance perdida). Atualiza esses lances, recalcula as métricas e marca `metrics["deep"] = "done"`.
- O critério de julgamento continua 2. O `CRITERIA` não muda e nenhuma partida fica marcada como "critério antigo" por causa disso.

**Pausar em vez de recusar (ponto 2), em detalhe.**
- O Atualizar agora cancela a fila (`game_jobs.cancel`, que já existe) e segue.
- Na abertura seguinte, a fila se refaz sozinha com:
  - as partidas não analisadas;
  - as com `deep = "pending"`;
  - as de critério antigo, só se o dono já tinha mandado reanalisar.
- A importação de puzzles continua bloqueando o botão, porque é outro mecanismo.

### 2. A análise guarda um pouco mais

Em `Game.metrics`, guardar:
- `wins`: a chance de vitória do ponto de vista do dono, por meio-lance, nos lances que a análise avaliou;
- `think`: os segundos gastos em cada lance do dono, quando o PGN tem relógio.

Em cada `GameMistake.detail`, guardar a **linha que pune** o seu lance: a `pv` da busca do seu lance, que é o seu lance, a melhor resposta do adversário e o que vem depois. Hoje só a linha do melhor lance fica guardada, e a encenação precisa da outra.

Sem coluna nova (metrics e detail já são JSON). Partidas antigas sem esses campos usam só os `GameMistake` (veja Seleção), e a encenação delas mostra só o melhor lance.

### 3. Seleção dos momentos do dia

Candidatos: lances do dono nas partidas das últimas 24 h que ainda não foram revisadas. O dia não precisa de partida nova; ver "Sem partidas hoje" abaixo. Os tipos de momento:

- **Erro decisivo:** erro ou capivarada depois do qual a partida não voltou mais. Exemplo de critério: a chance passa de ≥ 50% para < 25% e não volta acima de 40%.
- **Chance perdida:** na sua vez, a chance era ≥ 70% e tinha subido ≥ 20 pontos desde a sua vez anterior (o adversário errou), e o seu lance tirou ≥ 10 pontos.
- **Erro comum:** erro ou capivarada, sem os critérios acima.
- **Padrão do dia:** um bônus quando a mesma categoria do Error DNA aparece em 2 ou mais partidas do dia.
- **Lance bom:** um ! ou !!, no máximo 1 por dia. Serve de recompensa e de exemplo, e vale como pergunta igual às outras.

Pontuação: `perda de chance × peso do tipo`. Pesos de partida: decisivo 2,0, chance perdida 1,8, comum 1,0; padrão do dia ×1,3. Os números finos ficam com quem constrói (veja "Deixado pra quem constrói").

Regras de montagem:
- **5 momentos** (3 no dia leve);
- no máximo **2 da mesma partida**;
- ordem **misturada**, sem duas seguidas da mesma partida nem da mesma categoria, quando der;
- os **retornos que vencem no dia** (seção 5) entram intercalados, até 5. Sessão típica: 5 novos + até 5 retornos, ~10 min.

Sem partidas hoje: a sessão usa os retornos que vencem e os momentos não revisados dos últimos 3 dias. Se não houver nada, a rotina dá o passo como cumprido e avisa que não há partidas novas.

Detalhes:
- **Dia** é o dia local, como na rotina.
- A sessão do dia é **montada uma vez**, na primeira abertura, e fica guardada (KV), para não mudar no meio. Partidas que chegam depois entram numa segunda rodada opcional ("Chegaram 3 partidas novas: revisar?").
- Uma partida conta como revisada quando os momentos dela foram respondidos, ou quando ela foi considerada e não rendeu nenhum momento. Fica gravado em `metrics["reviewed_on"]`.

### 4. Um momento, passo a passo

1. **Posição** (`fen_before`, orientada para o seu lado). Junto vem uma linha com a partida, o número do lance e o seu relógio, sem dizer o tipo do momento: dizer seria dica. Pedido: "Ache o melhor lance."
2. **Você joga** no tabuleiro. Não tem voltar nem dica.
3. **Certeza ou chute?** Dois botões grandes, um toque, antes de qualquer resposta. Teclas 1 e 2.
4. **Resposta na hora**, sem tela intermediária:
   - **Acertou:** "Isso!" e o melhor lance com a ideia em 2 a 3 meios-lances (a `pv`).
   - **Errou:**
     - primeiro a **encenação** do problema do seu lance: o tabuleiro joga o seu lance e a resposta que pune (a linha guardada em `detail`), com seta, e uma frase curta do motivo. As fontes:
       - peça sem defesa: `judgement.see`;
       - mate: a linha termina em mate;
       - ameaça ignorada e os outros: categoria do Error DNA;
       - garfo e cravada: detectores **novos e pequenos**, com python-chess (uma peça atacando 2 alvos valiosos depois da resposta; `board.is_pinned`). Na fase 1, sem detector, a frase fica genérica ("depois de X, ele ganha material").
     - depois o melhor lance com a ideia dele;
     - errou **com certeza**: a resposta ganha destaque ("Você tinha certeza: olhe de novo") e o momento volta amanhã de qualquer jeito.
   - **Tempo × peso:** se o momento era decisivo ou chance perdida e você pensou menos de 5 s (ou menos de metade da sua mediana), aparece a linha "Você pensou 3 s no lance que decidiu a partida."
5. **Próximo** (tecla Enter). O tipo do momento ("chance perdida", "erro decisivo") só aparece aqui, depois da resposta.

Registro: um `Attempt` de `exercise_kind="game_position"` com `mode="daily_review"`. O "certeza ou chute" vai num campo JSON que já existe (`hesitation["confidence"]`), sem migração.

### 5. Retorno espaçado por posição, sem tabela nova

O próximo vencimento de cada `GameMistake` sai do histórico de `Attempt` dele, numa escada:

- acertou → próximo degrau (+1, +3, +7, +21 dias);
- errou → volta amanhã e cai um degrau;
- 3 acertos seguidos no degrau de 21 dias → **dominado**, sai da fila.

O cálculo é uma função pura sobre os `Attempt` (`game_mistake_id`, `correct`, `finished_at`, confiança), fácil de testar. Se ficar lento com muitas tentativas, um índice ou cache é decisão de quem constrói.

### 6. Regra do dia ("se… então")

No fim da sessão, a categoria do Error DNA mais frequente entre os momentos que você errou hoje vira uma regra pronta, que você aceita, edita ou pula. Modelos por categoria (texto final é de quem constrói):

| Categoria | Regra |
|---|---|
| Cegueira tática | Se tem captura ou xeque na posição, eu olho todos antes de decidir. |
| Erro de cálculo | Se a minha linha tem troca, eu conto até o fim quem fica com o quê. |
| Ameaça ignorada | Se ele acabou de mexer, eu pergunto o que esse lance ameaça. |
| Decisão impulsiva | Se a posição está tensa, eu espero 10 segundos antes de jogar. |
| Candidatos ruins | Se não é lance forçado, eu acho 3 candidatos antes de escolher. |
| Erro posicional | Se não tem tática, eu melhoro a minha pior peça. |
| Problema de relógio | Se passei da metade do tempo na abertura, eu jogo os lances simples rápido. |
| Técnica de final | Se é final, eu ativo o rei antes de tudo. |

A regra aceita aparece no Início no dia seguinte e na tela de começar partida do Jogar. O AURA conta se essa categoria diminui nas partidas seguintes e mostra isso ("Ameaça ignorada: 4 → 1 nos últimos 7 dias").

### 7. Rotina e Treinar: substitui, não empilha

- **Rotina:** o passo continua **"Seus erros de partida"**, com o mesmo nome e a mesma chave (`own_mistakes`). Assim os dias já planejados e o reconhecimento por título (`routine._is_step`) não mudam. A meta passa a ser a sessão do dia completa (5 momentos e os retornos do dia, ou 3 no dia leve), em vez de 5 posições soltas. Os testes da rotina mudam junto.
  - A contagem vira: respostas de `mode="daily_review"` no dia, contra o tamanho da sessão montada (seção 3).
- **Treinar:** o modo "Seus erros de partida" passa a começar pela sessão do dia. Quando ela acaba, continua com os retornos e com erros antigos nunca revisados, os mais novos primeiro (a lógica de `own_mistake_pool`), para quem quiser mais. Nada de dois modos parecidos lado a lado.
- **Onde mora a tela:** dentro do Treinar, reaproveitando o tabuleiro e o fluxo de posição de partida que já existem. O endereço (`/treinar?modo=...`) é decisão de quem constrói.

### 8. Fase 3: antes do motor, e a revisão de uma partida

- **"Onde você acha que perdeu?"** Nas partidas perdidas do dia, antes dos momentos daquela partida, a lista de lances aparece sem as marcas do motor, e você toca no lance onde acha que perdeu (ou pula). Depois o AURA mostra o erro decisivo de verdade e guarda a calibração ("você acertou onde perdeu em 4 de 10 partidas").
- **Tela de uma partida** (Partidas → Revisar):
  - **gráfico de chance de vitória** clicável, usando `wins`;
  - **precisão por fase** a partir dos dados de fase que já existem;
  - **"Próximo momento"**, que pula entre os momentos-chave;
  - tempo por lance sobreposto ao gráfico, usando `think`.
  As imprecisões ficam recolhidas na lista de erros (ponto 4 da conversa anterior).

## Entrega em fases

1. **Núcleo:**
   - análise rápida e depois profunda (ponto 1);
   - o botão de atualizar pausando a análise (ponto 2);
   - import diário do chess.com;
   - `wins` e `think` nas métricas;
   - seleção dos momentos;
   - fluxo de um momento (tentar, certeza, resposta na hora com o melhor lance);
   - retorno espaçado;
   - troca do passo da rotina e do modo do Treinar.
2. **Ensino:** encenação do motivo, tempo × peso, regra do dia e a contagem da categoria nas partidas seguintes.
3. **Partida:** "onde você acha que perdeu?", gráfico clicável, precisão por fase, próximo momento, imprecisões recolhidas.

Cada fase pode virar versão sozinha (0.6.0, 0.6.1…).

## Como saber se funciona

- **Retenção:** acerto nos retornos de 3 e 7 dias. Esperado: subir com as semanas.
- **Transferência:** erros por 100 lances da categoria da regra, nas partidas das 2 semanas seguintes, contra as 2 anteriores. Só critério 2, para não misturar réguas.
- **Custo e adesão:** tempo médio da sessão ≤ 12 min, e em quantos dias da semana a revisão foi feita.
- Tudo isso na tela de Diagnóstico, como números do próprio dono. Nenhuma promessa de rating.

## Restrições

- Tudo local, a interface em português do Brasil, a mesma pilha (FastAPI, React, Stockfish).
- Nada de voltar lance nem dica dentro do momento.
- Banco: sem migração na fase 1 (só campos JSON). Se alguma fase precisar, alembic com o backup automático que já existe.
- Testes para a seleção, a escada de retorno, a regra do dia e a troca do passo da rotina; o resto como o projeto já testa.
- O CI precisa rodar os testes que usam o Stockfish (ponto 5); senão a seleção, que depende de análise real, não é testada em lugar nenhum.

## Fora deste design (decidir à parte)

- O passo "Partidas contra o AURA" da rotina só conta partidas jogadas no AURA, e o dono joga no chess.com. Se ele deve contar as partidas importadas do dia é decisão do dono, separada desta.
- O "tim" na abertura (ponto 3) e o branch sobrando (ponto 5) não dependem deste design. O CI com Stockfish (ponto 5) entra como restrição acima.

## Deixado pra quem constrói

- os números finos da seleção (limites de chance, pesos, "menos de metade da mediana");
- o texto final das frases e das regras;
- o layout da tela (segue o tabuleiro e os componentes do Treinar);
- como guardar a calibração da fase 3 (KV ou JSON);
- a sobreposição do tempo no gráfico.
