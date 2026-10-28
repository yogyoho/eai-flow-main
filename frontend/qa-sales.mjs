import { chromium } from '@playwright/test'
import fs from 'node:fs'

const token = process.env.SALES_QA_TOKEN
if (!token) throw new Error('SALES_QA_TOKEN is required')
const outDir = process.env.SALES_QA_OUT || 'C:/Users/admin/AppData/Local/Temp/opencode/sales-qa'
fs.mkdirSync(outDir, { recursive: true })

const base = 'http://localhost:2026/sales'
const pages = [
  ['workbench', '/'],
  ['opportunities', '/opportunities'],
  ['todos', '/todos'],
  ['approvals', '/approvals'],
  ['master-data', '/master-data'],
]
const sizes = [
  [1440, 1100],
  [1024, 900],
  [390, 844],
]

const browser = await chromium.launch()
for (const [width, height] of sizes) {
  const context = await browser.newContext({ viewport: { width, height } })
  await context.addInitScript((value) => {
    window.localStorage.setItem('sales_token', value)
  }, token)
  const page = await context.newPage()
  const messages = []
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') messages.push(`${msg.type()}: ${msg.text()}`)
  })
  page.on('pageerror', (err) => messages.push(`pageerror: ${err.message}`))
  for (const [name, path] of pages) {
    await page.goto(base + path, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2200)
    const body = await page.locator('body').innerText()
    const overflow = await page.evaluate(() => ({
      doc: document.documentElement.scrollWidth,
      view: window.innerWidth,
    }))
    await page.screenshot({ path: `${outDir}/${name}-${width}.png`, fullPage: true })
    console.log(JSON.stringify({ page: name, width, title: await page.title(), chars: body.length, overflow, authGate: body.includes('需要 EAI') || body.includes('登录') && body.length < 800 }))
  }
  console.log(JSON.stringify({ width, messages }))
  await context.close()
}
await browser.close()
