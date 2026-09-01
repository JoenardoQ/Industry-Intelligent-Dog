/* Optional DOM-only real-browser release smoke. Requires Playwright on NODE_PATH. */
const { chromium } = require(process.argv[7] || process.env.INTDOG_PLAYWRIGHT_MODULE || 'playwright')
const fs = require('node:fs')

async function main() {
  const base = process.argv[2] || 'http://127.0.0.1:8765'
  const token = process.argv[3] || ''
  const output = process.argv[4] || 'intdog-browser-smoke.json'
  const executablePath = process.argv[6] || process.env.INTDOG_CHROME || undefined
  const browser = await chromium.launch({ headless: true, executablePath })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    await page.goto(`${base}/#session=${encodeURIComponent(token)}`)
    await page.waitForLoadState('networkidle')
    const evidence = []
    const destinations = {
      overview: '人工智能', daily: '每日情报', knowledge: '知识结构', products: '研究产物', sources: '信息源',
      research: '研究助手与 Intelligence Lab', jobs: '任务中心', system: '系统状态',
    }
    for (const [name, expected] of Object.entries(destinations)) {
      await page.evaluate(value => { location.hash = `/${value}` }, name)
      await page.getByRole('heading', { name: expected, exact: true }).waitFor()
      evidence.push([name, expected])
    }
    await page.evaluate(() => { location.hash = '/daily' })
    await page.getByRole('tab', { name: 'Story' }).click()
    evidence.push(['story-tab', await page.getByRole('heading', { name: '事件与证据' }).isVisible()])
    await page.evaluate(() => { location.hash = '/research' })
    evidence.push(['coverage', await page.getByText('开放世界覆盖地图').isVisible()])
    await page.evaluate(() => { location.hash = '/system' })
    evidence.push(['automation', await page.getByText('自动化计划').isVisible()])
    await page.getByText('每日采集', { exact: true }).waitFor()
    evidence.push(['schedule-cards', await page.locator('.schedule-grid article').count()])
    await page.setViewportSize({ width: 720, height: 900 })
    await page.evaluate(() => { location.hash = '/research' })
    await page.waitForTimeout(250)
    evidence.push(['narrow-overflow', await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth)])
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.evaluate(() => { document.documentElement.style.zoom = '2'; location.hash = '/knowledge' })
    await page.getByRole('heading', { name: '知识结构', exact: true }).waitFor()
    evidence.push(['zoom-200-overflow', await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth)])
    await page.evaluate(() => { document.documentElement.style.zoom = '1'; location.hash = '/overview' })
    const dailyNav=page.getByRole('button',{name:/每日情报/})
    await dailyNav.focus();await page.keyboard.press('Enter')
    await page.getByRole('heading',{name:'每日情报',exact:true}).waitFor()
    evidence.push(['keyboard-navigation',true])
    fs.writeFileSync(output, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8')
    process.stdout.write(`${JSON.stringify(evidence)}\n`)
  } finally {
    await browser.close()
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
