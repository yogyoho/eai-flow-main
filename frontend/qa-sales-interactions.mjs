import { chromium } from '@playwright/test'
import fs from 'node:fs'

const token = process.env.SALES_QA_TOKEN
if (!token) throw new Error('SALES_QA_TOKEN is required')
const outDir = process.env.SALES_QA_OUT || 'C:/Users/admin/AppData/Local/Temp/opencode/sales-qa'
fs.mkdirSync(outDir, { recursive: true })
const base = 'http://localhost:2026/sales'

const browser = await chromium.launch()

async function makePage(width, height) {
  const context = await browser.newContext({ viewport: { width, height } })
  await context.addInitScript((value) => window.localStorage.setItem('sales_token', value), token)
  const page = await context.newPage()
  const messages = []
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') messages.push(`${msg.type()}: ${msg.text()}`)
  })
  page.on('pageerror', (err) => messages.push(`pageerror: ${err.message}`))
  return { context, page, messages }
}

{
  const { context, page, messages } = await makePage(1440, 1100)
  await page.goto(base + '/opportunities', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr')
  await page.waitForTimeout(800)
  await page.locator('table tbody tr').nth(2).click()
  await page.waitForTimeout(900)
  const drawerText = await page.locator('.drawer').innerText().catch(() => 'NO DRAWER')
  await page.screenshot({ path: `${outDir}/opportunity-drawer-1440.png`, fullPage: true })
  console.log(JSON.stringify({ view: 'opportunity-drawer-1440', drawer: drawerText.slice(0, 220), messages }))
  await context.close()
}

{
  const { context, page, messages } = await makePage(390, 844)
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.menu-button')
  await page.waitForTimeout(800)
  await page.locator('.menu-button').click()
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${outDir}/mobile-nav-390.png`, fullPage: false })
  const navOpen = await page.locator('.sidebar.open').count()
  console.log(JSON.stringify({ view: 'mobile-nav-390', navOpen, messages }))
  await page.goto(base + '/opportunities', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('table tbody tr')
  await page.waitForTimeout(700)
  await page.locator('table tbody tr').nth(2).click()
  await page.waitForTimeout(900)
  await page.screenshot({ path: `${outDir}/opportunity-drawer-390.png`, fullPage: false })
  const overflow = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, view: innerWidth }))
  console.log(JSON.stringify({ view: 'opportunity-drawer-390', overflow, messages }))
  await context.close()
}

await browser.close()
