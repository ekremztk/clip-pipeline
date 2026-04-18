import puppeteer from 'puppeteer';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const cards = [
  'card-channel-dna',
  'card-content-finder',
  'card-ai-director',
  'card-editor',
  'card-analytics',
  'card-calendar',
];

async function main() {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1200, height: 800, deviceScaleFactor: 3 });

  const htmlPath = path.join(__dirname, 'card-export.html');
  await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle0' });

  const outputDir = path.join(__dirname, 'public', 'card-exports');
  await page.evaluate(() => {
    // ensure output dir message
  });

  // Create output dir
  const fs = await import('fs');
  fs.mkdirSync(outputDir, { recursive: true });

  for (const id of cards) {
    const el = await page.$(`#${id}`);
    if (!el) {
      console.log(`  [SKIP] #${id} not found`);
      continue;
    }
    const outPath = path.join(outputDir, `${id}.png`);
    await el.screenshot({ path: outPath, omitBackground: true });
    console.log(`  [OK] ${outPath}`);
  }

  await browser.close();
  console.log(`\nDone! ${cards.length} cards exported to ${outputDir}`);
}

main().catch(console.error);
