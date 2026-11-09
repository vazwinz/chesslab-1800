// First run on an empty database: the welcome tour and the empty states. Screenshots only.
//   node e2e/first_run.mjs [http://127.0.0.1:8000] [outDir]
import { chromium, devices } from "playwright";

const BASE = process.argv[2] ?? "http://127.0.0.1:8000";
const OUT = process.argv[3] ?? ".";
const browser = await chromium.launch();
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${BASE}/`);
  await page.getByRole("dialog").first().waitFor();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/tour-1.png` });
  for (let i = 2; i <= 4; i++) {
    const next = page.getByRole("button", { name: /Próximo|Continuar|Avançar/ }).first();
    if (!(await next.count())) break;
    await next.click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/tour-${i}.png` });
  }
  await page.keyboard.press("Escape");
  await page.goto(`${BASE}/`);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${OUT}/vazio-inicio.png`, fullPage: true });
  for (const [p, n] of [["/treinar", "treinar"], ["/partidas", "partidas"], ["/diagnostico?aba=erros", "diagnostico"]]) {
    await page.goto(`${BASE}${p}`);
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${OUT}/vazio-${n}.png`, fullPage: true });
  }
  const m = await browser.newPage({ ...devices["iPhone 13"] });
  await m.request.put(`${BASE}/api/prefs`, { data: { tour_done: false } });
  await m.goto(`${BASE}/`);
  await m.getByRole("dialog").first().waitFor();
  await m.waitForTimeout(400);
  await m.screenshot({ path: `${OUT}/tour-celular.png` });
} finally {
  await browser.close();
}
console.log("page errors:", errors.length ? errors : "none");
if (errors.length) process.exitCode = 1;
