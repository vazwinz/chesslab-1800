import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui";
import { HELP } from "../lib/help";
import { SESSION_KINDS, TRAIN_MODES } from "../lib/meta";
import { usePrefs } from "../lib/prefs";

const SECTIONS = [
  ["metodo", "O método"],
  ["comeco", "Na primeira semana"],
  ["dia", "Um dia de treino"],
  ["partidas", "Depois de cada partida"],
  ["jogar", "Jogar contra o computador"],
  ["modos", "Os modos de treino"],
  ["explicar", "O botão Explicar"],
  ["atalhos", "Atalhos de teclado"],
  ["numeros", "O que cada número quer dizer"],
  ["dados", "Seus dados"],
] as const;

export default function Guide() {
  const { set } = usePrefs();
  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_14rem] lg:gap-12">
      <article className="min-w-0 max-w-prose">
        <PageHeader title="Como treinar com o AURA"
          purpose="O método em poucas linhas, o que fazer em cada dia e o que significa cada número do app. Volte aqui sempre que um número parecer estranho." />

        <Part id="metodo" title="O método">
          <p>Até 1800, o que mais decide partida costuma ser tática: uma peça que fica pendurada, um garfo ou um mate que passou despercebido. Por isso o AURA começa pelos seus erros de verdade, e não por teoria.</p>
          <p>O treino principal é o <b>ciclo</b>, que se repete:</p>
          <ol className="list-decimal space-y-1 pl-5">
            <li><b>Medir</b> com 20 puzzles variados (ou 3 partidas analisadas).</li>
            <li><b>Diagnosticar</b>: achar o tipo de erro que mais se repete.</li>
            <li><b>Intervir</b>: escolher um treino feito para esse erro.</li>
            <li><b>Praticar</b> 30 exercícios desse treino.</li>
            <li><b>Reavaliar</b> com 20 puzzles variados.</li>
            <li><b>Adaptar</b>: comparar antes e depois e lembrar o que funcionou com você.</li>
          </ol>
          <p>Quando você tem partidas analisadas suficientes, a comparação de antes e depois usa as partidas, que é onde o rating de verdade se decide.</p>
        </Part>

        <Part id="comeco" title="Na primeira semana">
          <ol className="list-decimal space-y-2 pl-5">
            <li><Link className="link" to="/configuracoes">Baixe os puzzles do Lichess</Link>. Uma vez só: uns 300 MB e cerca de 15 minutos de importação.</li>
            <li><Link className="link" to="/partidas">Importe as suas partidas</Link> do Chess.com pelo seu usuário. A análise com o Stockfish roda em segundo plano, então dá para treinar enquanto isso.</li>
            <li><Link className="link" to="/treinar?modo=loop">Comece o ciclo</Link>. Os 20 primeiros puzzles são a medição: jogue no seu ritmo normal, sem pressa e sem chutar.</li>
            <li>Nos dias seguintes, continue o ciclo e siga o <Link className="link" to="/plano">plano do dia</Link>. Depois de uns dias, abra o <Link className="link" to="/diagnostico">Diagnóstico</Link>.</li>
          </ol>
        </Part>

        <Part id="dia" title="Um dia de treino">
          <p>O <Link className="link" to="/plano">plano do dia</Link> divide o treino em blocos. Cada bloco tem um lugar no app:</p>
          <dl className="space-y-2">
            <Def term="Padrões táticos">Treinar, no ciclo ou em puzzles mistos.</Def>
            <Def term="Cálculo profundo">Treinar, no cálculo às cegas: a linha inteira na cabeça antes de mexer.</Def>
            <Def term="Finais">A tela Finais (teoria contra o Stockfish) e os puzzles de final.</Def>
            <Def term="Preparação de aberturas">A tela Aberturas: treine as linhas do seu repertório de memória.</Def>
            <Def term="Partidas sérias">No Chess.com, com tempo para pensar em cada lance.</Def>
            <Def term="Análise dos erros">Partidas: revise os erros da última partida com o botão Explicar.</Def>
          </dl>
          <p>Os minutos de cada bloco são ajustáveis. Quando o app perceber quedas de desempenho repetidas, ele sugere um dia leve: menos tempo, mesmo foco.</p>
        </Part>

        <Part id="partidas" title="Depois de cada partida">
          <ol className="list-decimal space-y-1 pl-5">
            <li>Importe a partida em <Link className="link" to="/partidas">Partidas</Link> (pelo usuário do Chess.com ou colando o PGN).</li>
            <li>Espere a análise e abra a partida. Os seus erros aparecem marcados na lista de lances.</li>
            <li>Em cada erro, tente achar o lance melhor antes de olhar. Depois use <b>Explicar</b> para entender a ideia.</li>
            <li>Os erros viram exercícios no modo <b>{SESSION_KINDS.own_mistakes}</b>, para você revê-los dias depois.</li>
          </ol>
        </Part>

        <Part id="jogar" title="Jogar contra o computador">
          <p>Em <Link className="link" to="/jogar">Jogar</Link> você enfrenta o computador num nível que acompanha você: ganhou, o próximo sobe; perdeu, desce. Jogue depois do treino, para levar para a partida o que acabou de praticar.</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Cada lance seu é conferido na hora. Um erro ou uma capivarada acende o <b>vermelhão</b>, que só avisa: a partida segue, não dá para voltar o lance e o lance certo só aparece no fim. Depois de uma capivarada o computador joga o lance que pune, em qualquer nível.</li>
            <li>Comece do início, de uma abertura, do seu repertório, de um final, da posição antes de um erro seu ou de um FEN. Na revisão de partidas e na Análise, <b>Jogar daqui</b> começa uma partida da posição na tela.</li>
            <li>Só contam para o nível as partidas sem dica que começam do início, de uma abertura ou do repertório. As outras são treino.</li>
            <li>Toda partida vai para Partidas e é analisada: os erros entram no Error DNA e no ciclo como os das partidas importadas.</li>
          </ul>
          <p>Os níveis são aproximados: é o computador jogando pior de propósito, não o rating de um site.</p>
        </Part>

        <Part id="modos" title="Os modos de treino">
          <dl className="space-y-3">
            <Def term={SESSION_KINDS.loop}>O modo principal. Se não souber o que treinar, é este.</Def>
            {TRAIN_MODES.map((m) => <Def key={m.kind} term={SESSION_KINDS[m.kind]}>{m.when}</Def>)}
          </dl>
        </Part>

        <Part id="explicar" title="O botão Explicar">
          <p>Depois de cada puzzle e em cada erro das suas partidas, <b>Explicar</b> mostra a ideia do lance certo, a ameaça, o tema tático, por que o seu lance foi pior e a linha principal comentada lance a lance.</p>
          <p>Por padrão a explicação é montada por <b>regras</b>, a partir do Stockfish e de fatos do tabuleiro. Funciona sem internet e sem IA.</p>
          <p>Em <Link className="link" to="/configuracoes">Configurações</Link> você pode ligar uma <b>IA opcional</b> para reescrever o texto: o Ollama, que roda grátis no seu computador, ou uma chave de API sua. A IA recebe só os fatos do Stockfish. O AURA confere a resposta e volta para as regras se ela citar um lance que não está nos fatos, trouxer um número de avaliação ou chamar de melhor um lance que o Stockfish não confirmou. Cada explicação diz de onde veio.</p>
          <p>A chave fica só neste computador, criptografada pelo Windows para o seu usuário. Sem IA, tudo continua funcionando.</p>
        </Part>

        <Part id="atalhos" title="Atalhos de teclado">
          <h3>Treinar, depois de terminar um puzzle</h3>
          <dl className="space-y-1">
            <Keys keys={["Enter", "Espaço"]}>próximo puzzle</Keys>
            <Keys keys={["E"]}>explicar</Keys>
            <Keys keys={["A"]}>abrir a análise da posição</Keys>
            <Keys keys={["←", "→"]}>ver a solução lance a lance</Keys>
            <Keys keys={["Esc"]}>voltar da análise para o puzzle</Keys>
          </dl>
          <h3 className="pt-2">Análise e revisão de partidas</h3>
          <dl className="space-y-1">
            <Keys keys={["←", "→"]}>lance anterior e próximo</Keys>
            <Keys keys={["Home", "End"]}>início e fim</Keys>
            <Keys keys={["F"]}>virar o tabuleiro</Keys>
          </dl>
        </Part>

        <Part id="numeros" title="O que cada número quer dizer">
          <p className="text-muted">É o mesmo texto do “?” ao lado de cada número no app.</p>
          <dl className="space-y-4">
            {Object.entries(HELP).map(([k, h]) => (
              <div key={k}>
                <dt className="font-bold">{h.title}</dt>
                <dd className="text-muted">{h.text}</dd>
              </div>
            ))}
          </dl>
        </Part>

        <Part id="dados" title="Seus dados">
          <p>Tudo fica neste computador: exercícios, partidas, análises e configurações. A pasta aparece em Configurações, em Sobre. Antes de cada atualização que mexe no banco, o AURA salva uma cópia de segurança.</p>
          <p>O AURA só usa a internet para baixar os puzzles, importar partidas do Chess.com, ver se há versão nova (dá para desligar) e falar com a IA, se você configurar uma IA online.</p>
          <p>Os puzzles são do banco público do Lichess (domínio público, CC0). As análises são do Stockfish, um programa livre (GPLv3).</p>
          <button className="btn mt-2" onClick={() => set({ tour_done: false })}>Ver o tour de boas-vindas de novo</button>
        </Part>
      </article>

      <nav className="hidden lg:block" aria-label="Nesta página">
        <div className="sticky top-8 space-y-1 border-l border-rule pl-4 text-sm">
          {SECTIONS.map(([id, t]) => <a key={id} href={`#${id}`} className="block py-0.5 text-muted hover:text-ink">{t}</a>)}
        </div>
      </nav>
    </div>
  );
}

function Part({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 space-y-3 border-t border-rule py-8 first-of-type:border-t-0">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Def({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="font-bold">{term}</dt>
      <dd className="text-muted">{children}</dd>
    </div>
  );
}

function Keys({ keys, children }: { keys: string[]; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <dt className="flex gap-1">{keys.map((k) => <kbd key={k} className="kbd">{k}</kbd>)}</dt>
      <dd className="text-muted">{children}</dd>
    </div>
  );
}
