// Capture marketing screenshots of the running demo.
// Override the target with DEMO_BASE, e.g. DEMO_BASE=http://localhost:8095
const puppeteer = require('puppeteer');

const BASE = process.env.DEMO_BASE || 'http://localhost:8090';
const OUT = '/out';
const HIDE_BANNER = `.tsp-demobar{display:none!important}`;

const shots = [
  // Public frontend (logged out)
  { url: '/demo',            file: 'fe-home.png',      login: false },
  { url: '/meetings',        file: 'fe-meetings.png',  login: false },
  { url: '/library',         file: 'fe-library.png',   login: false },
  { url: '/events',          file: 'fe-events.png',    login: false },
  // Backend (logged in)
  { url: '/tspro',           file: 'be-dashboard.png', login: true },
  { url: '/tspro/meetings',  file: 'be-meetings.png',  login: true },
  { url: '/tspro/frontend',  file: 'be-frontend.png',  login: true },
  { url: '/tspro/watchtower',file: 'be-watchtower.png',login: true },
];

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });

  // Log in once (GET endpoint sets the session + lands on /tspro).
  let loggedIn = false;
  async function ensureLogin() {
    if (loggedIn) return;
    await page.goto(BASE + '/demo/login-admin', { waitUntil: 'networkidle2', timeout: 60000 });
    loggedIn = true;
  }

  for (const s of shots) {
    if (s.login) await ensureLogin();
    await page.goto(BASE + s.url, { waitUntil: 'networkidle2', timeout: 60000 });
    await page.addStyleTag({ content: HIDE_BANNER });
    await new Promise(r => setTimeout(r, 1000)); // let async widgets settle
    await page.screenshot({ path: `${OUT}/${s.file}`, type: 'png' });
    console.log('captured', s.file);
  }

  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
