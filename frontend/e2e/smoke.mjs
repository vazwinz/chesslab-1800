// End-to-end smoke test (Playwright) for the 0.4.0 UI.
// Requires the backend running on BASE with the puzzles imported (the test fixture is enough).
//   node e2e/smoke.mjs [http://127.0.0.1:8000] [outDir]
import { Chess } from "chess.js";
import { chromium, devices } from "playwright";

const BASE = process.argv[2] ?? "http://127.0.0.1:8000";
const OUT = process.argv[3] ?? ".";
const log = (...a) => console.log("[e2e]", ...a);
const failures = [];
const check = (ok, what) => {
  log(ok ? "ok  " : "FAIL", what);
  if (!ok) failures.push(what);
};
const shot = (page, name, full = false) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: full });

async function clickMove(page, uci) {
  await page.locator(`[data-square="${uci.slice(0, 2)}"]`).first().click();
  await page.locator(`[data-square="${uci.slice(2, 4)}"]`).first().click();
}

/** Starts the next exercise with `trigger`, then plays it right or wrong through the board. */
async function playOne(page, trigger, correct) {
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/next") && r.request().method() === "POST"),
    trigger(),
  ]);
  const ex = await resp.json();
  await page.waitForTimeout(900); // the opponent's first move is animated
  // the harness (not the app) looks the solution up to drive the board
  const sol = await (await page.request.get(`${BASE}/api/puzzles/${ex.puzzle_id}`)).json();
  const g = new Chess(sol.fen);
  if (!correct) {
    const right = new Chess(sol.fen).move(sol.solution_san[0]);
    const wrong = g.moves({ verbose: true }).find((m) => m.from + m.to !== right.from + right.to && !m.promotion);
    await clickMove(page, wrong.from + wrong.to);
  } else {
    for (let i = 0; i < sol.solution_san.length; i += 2) {
      const m = g.move(sol.solution_san[i]);
      await clickMove(page, m.from + m.to);
      if (m.promotion) await page.locator(`[data-piece="${g.turn() === "w" ? "b" : "w"}Q"]`).first().click().catch(() => {});
      await page.waitForTimeout(700);
      if (sol.solution_san[i + 1]) g.move(sol.solution_san[i + 1]);
    }
  }
  await page.getByRole("button", { name: /Próximo puzzle/ }).first().waitFor({ timeout: 20000 });
  return ex;
}

async function noOverflow(page, what) {
  const o = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check(!o, `sem rolagem horizontal: ${what}`);
}

const browser = await chromium.launch();
const errors = [];
try {
  for (const theme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: theme });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => errors.push(`${theme}: ${e}`));
    page.on("console", (m) => m.type() === "error" && errors.push(`${theme} console: ${m.text()}`));
    await page.request.put(`${BASE}/api/prefs`, { data: { theme: "system", tour_done: true } });

    await page.goto(`${BASE}/`);
    await page.getByRole("heading", { name: /Meta:/ }).waitFor();
    check(await page.getByText("Stockfish").first().isVisible(), `${theme}: status do Stockfish na barra lateral`);
    await shot(page, `${theme}-inicio`, true);

    await page.goto(`${BASE}/treinar`);
    await page.getByRole("heading", { name: "Treinar" }).waitFor();
    const startMixed = () => page.locator("li", { hasText: "Puzzles mistos" }).getByRole("button", { name: "Começar" }).click();
    await playOne(page, startMixed, true);
    check(await page.getByText("Correto", { exact: true }).isVisible(), `${theme}: acerto mostra "Correto"`);
    await shot(page, `${theme}-treinar-certo`);
    await page.getByRole("button", { name: /^Explicar/ }).click();
    await page.getByText(/Explicação por regras|^IA: /).first().waitFor({ timeout: 60000 });
    await page.waitForTimeout(500);
    await shot(page, `${theme}-treinar-explicar`, true);

    await playOne(page, () => page.getByRole("button", { name: /Próximo puzzle/ }).first().click(), false);
    check(await page.getByText("Não foi o melhor lance").isVisible(), `${theme}: erro mostra o aviso`);
    check(await page.getByText(/^Error DNA:/).first().isVisible(), `${theme}: erro mostra o Error DNA`);
    await shot(page, `${theme}-treinar-erro`);

    // analysing the position and coming back keeps the session (the grind is not lost)
    const ribbonBefore = await page.locator("[aria-label^='Resultados da sessão']").getAttribute("aria-label");
    await page.keyboard.press("a");
    await page.getByRole("button", { name: "Voltar ao puzzle" }).waitFor();
    await page.waitForTimeout(2500);
    await shot(page, `${theme}-treinar-analise`);
    await page.getByRole("button", { name: "Voltar ao puzzle" }).click();
    check(await page.getByText("Não foi o melhor lance").isVisible(), `${theme}: voltar da análise mantém o puzzle`);
    await page.goto(`${BASE}/diagnostico`);
    await page.goto(`${BASE}/treinar`);
    const ribbonAfter = await page.locator("[aria-label^='Resultados da sessão']").getAttribute("aria-label");
    check(ribbonBefore === ribbonAfter, `${theme}: sair e voltar para Treinar mantém a sessão (${ribbonAfter})`);

    await page.goto(`${BASE}/partidas`);
    await page.locator("h1").filter({ hasText: /^Partidas/ }).waitFor();
    await shot(page, `${theme}-partidas`, true);
    const firstGame = page.getByRole("button", { name: "Revisar" }).first();
    if (await firstGame.count()) {
      await firstGame.click();
      await page.waitForTimeout(2500);
      await shot(page, `${theme}-partida-revisao`, true);
    } else check(false, `${theme}: lista de partidas tem link para a revisão`);

    await page.goto(`${BASE}/diagnostico`);
    for (const [tab, label] of [["ciclo", "Ciclo"], ["erros", "Error DNA"], ["retencao", "Retenção"], ["fadiga", "Fadiga"],
      ["pressao", "Pressão"], ["perfil", "Perfil"], ["previsao", "Previsão"], ["intervencoes", "O que funciona"], ["ciencia", "Ciência"]]) {
      await page.getByRole("tab", { name: label, exact: true }).click();
      await page.waitForTimeout(600);
      check(!(await page.getByRole("alert").count()), `${theme}: Diagnóstico › ${label} sem erro`);
      if (theme === "light" || ["fadiga", "erros"].includes(tab)) await shot(page, `${theme}-diagnostico-${tab}`, true);
    }
    for (const [path, name] of [["/plano", "plano"], ["/aberturas", "aberturas"], ["/finais", "finais"], ["/guia", "guia"], ["/configuracoes", "configuracoes"]]) {
      await page.goto(`${BASE}${path}`);
      await page.waitForTimeout(700);
      check(!(await page.getByRole("alert").count()), `${theme}: ${path} sem erro`);
      await shot(page, `${theme}-${name}`, true);
    }
    // "?" opens the explanation
    await page.goto(`${BASE}/`);
    await page.getByRole("button", { name: /O que é: Rating de puzzle$/ }).first().click();
    check(await page.getByRole("dialog").first().isVisible(), `${theme}: o "?" abre a explicação`);

    await page.goto(`${BASE}/analise`);
    await clickMove(page, "e2e4");
    await page.locator("p", { hasText: /, profundidade \d+/ }).first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(1500);
    await shot(page, `${theme}-analise`);
    await ctx.close();
  }

  // mobile
  const m = await browser.newContext({ ...devices["iPhone 13"] });
  const mp = await m.newPage();
  mp.on("pageerror", (e) => errors.push(`mobile: ${e}`));
  for (const path of ["/", "/treinar", "/partidas", "/diagnostico?aba=erros", "/guia", "/configuracoes"]) {
    await mp.goto(`${BASE}${path}`);
    await mp.waitForTimeout(900);
    await noOverflow(mp, path);
  }
  await mp.goto(`${BASE}/treinar`);
  await mp.locator("li", { hasText: "Puzzles mistos" }).getByRole("button", { name: "Começar" }).click();
  await mp.locator('[data-square="e4"]').first().waitFor();
  await mp.waitForTimeout(1200);
  await noOverflow(mp, "/treinar com o tabuleiro");
  await shot(mp, "mobile-treinar");
  const sq = await mp.locator('[data-square="e4"]').first().boundingBox();
  log("mobile square size:", sq && Math.round(sq.width));
  check(!!sq && sq.width >= 38, "celular: casas do tabuleiro com 38 px ou mais");
  await mp.goto(`${BASE}/`);
  await shot(mp, "mobile-inicio", true);
  await m.close();
} finally {
  await browser.close();
}
log("page errors:", errors.length ? errors : "none");
if (errors.length) failures.push("erros na página");
if (failures.length) {
  log("FAILED:", failures);
  process.exitCode = 1;
}
