import { chromium } from '@playwright/test'
import fs from 'node:fs'

const token = process.env.SALES_QA_TOKEN
const outDir = 'C:/Users/admin/AppData/Local/Temp/opencode/sales-qa'
fs.mkdirSync(outDir, { recursive: true })
const base = 'http://localhost:2026/sales'
const browser = await chromium.launch()

async function run(width, height, prefix) {
  const context = await browser.newContext({ viewport: { width, height } })
  await context.addInitScript((value) => window.localStorage.setItem('sales_token', value), token)
  const page = await context.newPage()
  const messages = []
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') messages.push(`${msg.type()}: ${msg.text()}`)
  })
  page.on('pageerror', (err) => messages.push(`pageerror: ${err.message}`))
  await page.goto(base + '/approvals', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr')
  await page.waitForTimeout(700)
  await page.screenshot({ path: `${outDir}/${prefix}-list.png`, fullPage: true })
  await page.locator('table tbody tr').first().click()
  await page.waitForTimeout(800)
  const text = await page.locator('.drawer').innerText().catch(() => 'NO DRAWER')
  await page.screenshot({ path: `${outDir}/${prefix}-drawer.png`, fullPage: width > 500 })
  console.log(JSON.stringify({ prefix, text: text.slice(0, 400), messages }))
  await context.close()
}

await run(1440, 1100, 'approval-1440')
await run(390, 844, 'approval-390')
await browser.close()
