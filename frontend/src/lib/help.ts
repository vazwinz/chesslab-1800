/** Plain-language explanations behind every "?" in the app (also listed in the Guide). */
export const HELP: Record<string, { title: string; text: string }> = {
  puzzle_rating: {
    title: "Rating de puzzle",
    text: "Mede o seu acerto em puzzles, comparado com a dificuldade de cada puzzle (rating do Lichess). Sobe quando você acerta puzzles difíceis e desce quando erra fáceis. Não é o seu rating do Chess.com: são escalas diferentes. Use para ver se o treino está evoluindo.",
  },
  real_rating: {
    title: "Rating real (Chess.com)",
    text: "É o rating que aparece no cabeçalho das partidas que você importou (o Chess.com escreve o rating de cada jogador no PGN). É o número que importa para a meta dos 1800. Ele só muda quando você importa partidas novas. O AURA separa por ritmo (rápidas, blitz, bullet), porque cada um tem o seu rating.",
  },
  puzzle_vs_real: {
    title: "Rating de puzzle × rating real",
    text: "O rating de puzzle mostra o quanto você enxerga táticas com tempo e sem pressão. O real mostra o resultado nas partidas, onde também contam relógio, abertura, final e nervosismo. É normal o de puzzle ficar bem acima. Se ele sobe e o real não, o gargalo está fora das táticas: veja o Diagnóstico.",
  },
  rd: {
    title: "Margem do rating (RD)",
    text: "Quanto o AURA ainda pode estar errado sobre o seu rating de puzzle. Começa grande (350) e diminui conforme você resolve puzzles. Um '?' depois do número quer dizer que o rating ainda é provisório.",
  },
  ci: {
    title: "Intervalo de confiança (IC 95%)",
    text: "Com poucos exercícios, uma porcentagem engana. O intervalo mostra a faixa onde o seu acerto verdadeiro provavelmente está. Exemplo: 70% com IC 55–82% quer dizer 'algo entre 55% e 82%'. Quanto mais exercícios, mais estreito ele fica.",
  },
  accuracy: {
    title: "Acerto",
    text: "Porcentagem de puzzles resolvidos sem errar nenhum lance. Puzzles de pressão não mudam o seu rating, mas entram aqui.",
  },
  streak: {
    title: "Sequência",
    text: "Quantos puzzles seguidos você acertou até agora. Zera no primeiro erro.",
  },
  error_dna: {
    title: "Error DNA",
    text: "Toda vez que você erra, o AURA classifica o tipo de erro com regras fixas a partir do Stockfish, do tabuleiro e do seu tempo: tática não vista, erro de cálculo, ameaça ignorada, decisão impulsiva, problema de relógio, técnica de final, candidatos ruins ou erro posicional. Um padrão é 'recorrente' quando aparece 3 vezes ou mais em pelo menos 2 partidas ou sessões. São pistas de treino, não um diagnóstico da sua cabeça.",
  },
  retention: {
    title: "Retenção",
    text: "Mostra se você continua acertando um tema depois de um tempo sem vê-lo. O que conta é acertar puzzles NOVOS do tema dias depois (lembrar de uma posição repetida não vale). Cada tema volta para revisão em intervalos cada vez maiores: 1 dia, 3 dias, depois mais.",
  },
  fatigue: {
    title: "Fadiga",
    text: "Durante a sessão, o AURA compara o seu acerto (ajustado pela dificuldade) e o seu tempo no começo e no fim. Se os dois pioram de forma consistente, ele sugere uma pausa. É um sinal do desempenho, não um diagnóstico médico.",
  },
  pressure: {
    title: "Pressão",
    text: "Puzzles com relógio que vai encurtando (de 60 s até 12 s por puzzle) e posições mais complexas. A qualidade das decisões é medida separada da velocidade: estourar o tempo não conta como lance errado, conta como problema de relógio.",
  },
  loop: {
    title: "Treino em ciclo",
    text: "O modo principal. Medir: 20 puzzles variados (ou 3 partidas analisadas). Diagnosticar: acha o seu erro recorrente mais forte. Intervir e praticar: 30 exercícios feitos para esse erro. Reavaliar: 20 puzzles variados de novo. Adaptar: compara antes e depois (usa as suas partidas quando houver dados suficientes) e aprende qual intervenção funciona para você.",
  },
  prediction: {
    title: "Previsão",
    text: "Uma reta ajustada aos seus próprios dados, com uma faixa (intervalo de previsão de 95%) onde o próximo valor provavelmente cai. Aprender não é uma reta, então leia como 'para onde a tendência atual aponta'. Só aparece com dados suficientes.",
  },
  acpl: {
    title: "ACPL",
    text: "Perda média em centipeões por lance (100 centipeões = 1 peão), segundo o Stockfish. Quanto menor, mais precisos foram os seus lances.",
  },
  game_accuracy: {
    title: "Precisão da partida",
    text: "Nota de 0 a 100 calculada a partir de quanto cada lance seu diminuiu a chance de vitória (modelo do Lichess). Não é a mesma conta do Chess.com, então os números podem ser um pouco diferentes.",
  },
  severity: {
    title: "Imprecisão, erro e capivarada",
    text: "Classificação de cada lance pela queda na chance de vitória segundo o Stockfish: imprecisão (10 pontos ou mais), erro (20 ou mais) e capivarada (30 ou mais).",
  },
  bands: {
    title: "Faixas de dificuldade",
    text: "O AURA escolhe puzzles perto do seu rating, dentro de uma faixa. Ele sobe de faixa quando você acerta 80% ou mais em pelo menos 10 puzzles da faixa, e desce com 45% ou menos em 8. Se o seu rating de puzzle já está firme (margem de 110 ou menos) e bem fora da faixa, ele vai direto para a faixa do seu rating. Nunca muda por causa de um puzzle só.",
  },
  daily_minutes: {
    title: "Minutos por dia",
    text: "Soma do tempo medido resolvendo exercícios em cada dia (no fuso do seu computador). O tempo parado entre um puzzle e outro não entra.",
  },
  engine_eval: {
    title: "Avaliação do Stockfish",
    text: "Positivo é melhor para as Brancas, negativo para as Pretas, em peões (+1.00 ≈ um peão a mais). '#3' quer dizer mate em 3 para as Brancas, '#-3' mate em 3 para as Pretas. A profundidade diz quantos lances à frente o Stockfish olhou.",
  },
  coach_source: {
    title: "De onde vem a explicação",
    text: "Regras: o AURA monta o texto a partir do Stockfish e de fatos do tabuleiro (capturas, xeques, garfos, cravadas...). IA: uma IA reescreve o texto a partir desses mesmos fatos. O AURA confere a resposta da IA e descarta se ela inventar lance, número ou disser que outro lance é o melhor.",
  },
  candidates: {
    title: "Lances candidatos",
    text: "Antes de jogar, escreva até 3 lances que você considera. A nota é 1 se a solução estiver na lista, 0,5 se algum dos 3 melhores do Stockfish estiver, e 0 se não.",
  },
  blind: {
    title: "Cálculo às cegas",
    text: "Escreva a linha inteira (só os seus lances) antes de mexer qualquer peça. As respostas do adversário são automáticas. Treina segurar a variante na cabeça.",
  },
};
