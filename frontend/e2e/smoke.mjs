// End-to-end smoke test (Playwright). Requires the backend running on BASE with puzzles imported.
//   node e2e/smoke.mjs [http://127.0.0.1:8000] [outDir]
import { chromium, devices } from "playwright";

const BASE = process.argv[2] ?? "http://127.0.0.1:8000";
const OUT = process.argv[3] ?? ".";
const log = (...a) => console.log("[e2e]", ...a);

async function clickMove(page, uci) {
  await page.locator(`[data-square="${uci.slice(0, 2)}"]`).click();
  await page.locator(`[data-square="${uci.slice(2, 4)}"]`).click();
}

async function solveOne(page, trigger, correct) {
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/next") && r.request().method() === "POST"),
    trigger(),
  ]);
  const ex = await resp.json();
  await page.waitForTimeout(900); // opponent move animation
  // the test harness (not the app) looks up the solution to drive the UI
  const solution = await (await page.request.get(`${BASE}/api/puzzles/${ex.puzzle_id}`)).json();
  if (!correct) {
    const legal = await (await page.request.post(`${BASE}/api/board/legal`, { data: { fen: ex.fen } })).json();
    const { Chess } = await import("chess.js");
    const right = new Chess(solution.fen).move(solution.solution_san[0]);
    await clickMove(page, legal.moves.find((m) => m.slice(0, 4) !== right.from + right.to));
  } else {
    // replay the solution: our moves are at even indexes of the solution line
    const { Chess } = await import("chess.js");
    const g = new Chess(solution.fen);
    for (let i = 0; i < solution.solution_san.length; i += 2) {
      const m = g.move(solution.solution_san[i]);
      await clickMove(page, m.from + m.to);
      await page.waitForTimeout(700);
      if (solution.solution_san[i + 1]) g.move(solution.solution_san[i + 1]);
    }
  }
  await page.getByText(/Next exercise/).waitFor({ timeout: 15000 });
}

const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${BASE}/`);
  await page.getByText("Stockfish", { exact: false }).first().waitFor();
  await page.screenshot({ path: `${OUT}/dashboard-empty.png` });
  await page.goto(`${BASE}/train`);
  await solveOne(page, () => page.getByRole("button", { name: "Start" }).nth(1).click(), true); // Mixed tactics
  const okText = await page.locator("text=Correct").first().isVisible();
  log("correct solve shows feedback:", okText);
  await page.screenshot({ path: `${OUT}/train-correct.png` });
  await solveOne(page, () => page.getByText(/Next exercise/).click(), false);
  const dna = await page.locator("text=Error DNA").first().isVisible();
  log("wrong move shows Error DNA:", dna);
  await page.screenshot({ path: `${OUT}/train-wrong.png` });
  await page.goto(`${BASE}/`);
  await page.getByText("Solved").waitFor();
  const solved = await page.locator(".card", { hasText: "Solved" }).first().innerText();
  log("dashboard solved card:", solved.replace(/\n/g, " | "));
  await page.screenshot({ path: `${OUT}/dashboard.png`, fullPage: true });
  await page.goto(`${BASE}/cognitive`);
  await page.getByText("Completed cycles").waitFor();
  for (const t of ["Profile", "Error DNA", "Science"]) {
    await page.getByRole("button", { name: t, exact: true }).click();
    await page.waitForTimeout(400);
  }
  await page.screenshot({ path: `${OUT}/cognitive-science.png`, fullPage: true });
  await page.goto(`${BASE}/analysis`);
  await clickMove(page, "e2e4");
  await page.getByRole("button", { name: "Stockfish" }).click();
  await page.locator("text=depth").first().waitFor({ timeout: 20000 });
  await page.screenshot({ path: `${OUT}/analysis.png` });
  // mobile
  const m = await browser.newContext({ ...devices["iPhone 13"] });
  const mp = await m.newPage();
  mp.on("pageerror", (e) => errors.push(String(e)));
  await mp.goto(`${BASE}/train`);
  await mp.getByRole("button", { name: "Start" }).nth(1).click();
  await mp.waitForTimeout(1500);
  const boardBox = await mp.locator('[data-square="e4"]').boundingBox();
  const overflow = await mp.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  log("mobile square size:", boardBox && Math.round(boardBox.width), "horizontal overflow:", overflow);
  await mp.screenshot({ path: `${OUT}/mobile-train.png` });
  log("page errors:", errors.length ? errors : "none");
  if (!okText || !dna || overflow || errors.length) process.exitCode = 1;
} finally {
  await browser.close();
}
