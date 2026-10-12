import assert from 'node:assert/strict'
import { mkdir, readFile } from 'node:fs/promises'
import path from 'node:path'

import { chromium } from 'playwright-core'

const appUrl = process.env.APP_URL ?? 'http://127.0.0.1:5173'
const browserName = process.env.BROWSER_NAME ?? 'chrome'
assert.ok(
  ['chrome', 'edge'].includes(browserName),
  'BROWSER_NAME must be chrome or edge',
)
const browserPath =
  process.env.BROWSER_PATH ??
  (browserName === 'edge'
    ? process.env.EDGE_PATH ??
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
    : process.env.CHROME_PATH ??
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
const fixture = path.resolve('../data/fixtures/two-speaker-zh.wav')
const screenshotDirectory = path.resolve('../data/test_results')
const runId = Date.now().toString(36)
const tenantSlug = `browser-smoke-${runId}`
const email = `${tenantSlug}@example.com`
const userPassword = 'browser-test-2026'
const adminUsername = process.env.PLATFORM_ADMIN_USERNAME ?? ''
const adminPassword = process.env.PLATFORM_ADMIN_PASSWORD ?? ''
assert.ok(
  adminUsername && adminPassword,
  'PLATFORM_ADMIN_USERNAME and PLATFORM_ADMIN_PASSWORD are required for browser provisioning',
)
const envText = await readFile(path.resolve('../.env'), 'utf8')
const envEntries = new Map(envText.split(/\r?\n/).flatMap((line) => {
  const trimmed = line.trim()
  if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) return []
  const separator = trimmed.indexOf('=')
  const key = trimmed.slice(0, separator).trim().replace(/^export\s+/, '')
  let value = trimmed.slice(separator + 1).trim()
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1)
  return [[key, value]]
}))
const deepSeekKey = envEntries.get('DEEPSEEK_API_KEY') ?? envEntries.get('deepseek_api') ?? ''
assert.ok(deepSeekKey, 'DeepSeek API key is required for browser smoke')

await mkdir(screenshotDirectory, { recursive: true })

const browser = await chromium.launch({ executablePath: browserPath, headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
const pageErrors = []
let chunkUploads = 0
let taskPolls = 0
let jobCreates = 0
let verifiedDuplicateChunkUploads = 0
let verifiedDuplicateJobCreates = 0
let expireSummaryOnce = true
let summaryAttempts = 0

await page.route('**/api/v1/workspace/summary', async (route) => {
  summaryAttempts += 1
  if (expireSummaryOnce) {
    expireSummaryOnce = false
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Invalid or expired access token' }),
    })
    return
  }
  await route.continue()
})

page.on('pageerror', (error) => pageErrors.push(error.message))
page.on('request', (request) => {
  const requestUrl = request.url()
  if (request.method() === 'PUT' && /\/uploads\/files\/[^/]+\/chunks\//.test(requestUrl)) {
    chunkUploads += 1
  }
  if (request.method() === 'GET' && /\/api\/v1\/jobs(?:\?|$)/.test(requestUrl)) {
    taskPolls += 1
  }
  if (request.method() === 'POST' && /\/api\/v1\/jobs(?:\?|$)/.test(requestUrl)) {
    jobCreates += 1
  }
})

try {
  const adminLogin = await fetch(`${appUrl}/api/v1/admin/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: adminUsername, password: adminPassword }),
  })
  assert.equal(adminLogin.status, 200, 'platform administrator login failed')
  const adminAuth = await adminLogin.json()
  assert.equal(
    adminAuth.password_change_required,
    false,
    'platform administrator must complete the initial password change first',
  )
  const provisioned = await fetch(`${appUrl}/api/v1/admin/tenants`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${adminAuth.access_token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      tenant_name: 'Browser Smoke Tenant',
      tenant_slug: tenantSlug,
      owner_display_name: 'Browser Tester',
      owner_email: email,
    }),
  })
  assert.equal(provisioned.status, 201, 'browser tenant provisioning failed')
  const provisionedAccount = await provisioned.json()

  await page.goto(`${appUrl}/login`)
  await page.getByLabel('租户标识').fill(tenantSlug)
  await page.getByLabel('电子邮箱').fill(email)
  await page.getByRole('button', { name: '下一步 →' }).click()
  await page.getByLabel('密码').fill(provisionedAccount.initial_password)
  await page.getByRole('button', { name: '进入工作台 →' }).click()
  await page.waitForURL('**/change-password')
  await page.getByLabel('新密码').fill(userPassword)
  await page.getByLabel('确认新密码').fill(userPassword)
  await page.getByRole('button', { name: '修改密码并退出' }).click()
  await page.waitForURL('**/login')
  await page.getByLabel('租户标识').fill(tenantSlug)
  await page.getByLabel('电子邮箱').fill(email)
  await page.getByRole('button', { name: '下一步 →' }).click()
  await page.getByLabel('密码').fill(userPassword)
  await page.getByRole('button', { name: '进入工作台 →' }).click()
  await page.waitForURL('**/workspace/overview')
  assert.equal(await page.title(), 'LC')
  assert.equal(await page.locator('link[rel="icon"]').getAttribute('href'), '/lc.svg')

  await page.getByText('工作空间', { exact: true }).waitFor()
  for (const metric of ['正在运行', '已经完成', '可用模型']) {
    await page.getByText(metric, { exact: true }).waitFor()
  }
  await page.getByText('0', { exact: true }).first().waitFor()
  assert.ok(summaryAttempts >= 2, 'expired dashboard token was not refreshed and retried')
  assert.equal(await page.getByText('统计加载失败', { exact: true }).count(), 0,
    'dashboard exposed a transient token error instead of recovering')
  const headingSize = Number.parseFloat(
    await page.getByRole('heading', { name: /你好，Browser Tester/ }).evaluate(
      (element) => getComputedStyle(element).fontSize,
    ),
  )
  assert.ok(headingSize >= 36, `overview heading is unexpectedly small: ${headingSize}px`)
  await page.screenshot({
    path: path.join(screenshotDirectory, 'workspace-overview.png'),
    fullPage: true,
  })

  await page.getByRole('button', { name: '查看已完成的转写任务' }).click()
  await page.waitForURL('**/workspace/tasks')
  await page.getByRole('heading', { name: '转写任务', exact: true }).waitFor()
  await page.getByRole('button', { name: '总览', exact: true }).click()
  await page.getByRole('button', { name: '查看可用模型' }).click()
  await page.waitForURL('**/workspace/models')
  await page.getByRole('heading', { name: '语音模型', exact: true }).waitFor()
  await page.getByRole('button', { name: '总览', exact: true }).click()
  await page.getByRole('button', { name: '查看历史文件' }).click()
  await page.waitForURL('**/workspace/history')
  await page.getByRole('heading', { name: '历史文件', exact: true }).waitFor()
  await page.getByRole('button', { name: '总览', exact: true }).click()

  await page.getByRole('button', { name: '提交转写', exact: true }).click()
  await page.getByText('尚未配置文本模型', { exact: true }).waitFor()
  await page.getByRole('button', { name: '模型', exact: true }).click()
  await page.getByRole('heading', { name: '语音模型', exact: true }).waitFor()
  await page.getByRole('heading', { name: '文本模型', exact: true }).waitFor()
  await page.getByRole('button', { name: '添加 API 模型', exact: true }).click()
  await page.getByLabel('模型分类').click()
  await page.getByRole('option', { name: '文本模型', exact: true }).click()
  await page.screenshot({ path: path.join(screenshotDirectory, 'workspace-model-form.png'), fullPage: true })
  await page.locator('#api-key').fill(deepSeekKey)
  await page.getByRole('button', { name: '保存 API 模型', exact: true }).click()
  await page.getByText('DeepSeek 文本整理', { exact: true }).waitFor()

  await page.getByRole('button', { name: '提交转写', exact: true }).click()
  const providerSelect = page.getByLabel('语音模型方案')
  const providerStyle = await providerSelect.evaluate((element) => {
    const style = getComputedStyle(element)
    return { borderWidth: style.borderTopWidth, boxShadow: style.boxShadow }
  })
  assert.equal(providerStyle.borderWidth, '2px', 'model selector is missing the RetroUI border')
  assert.notEqual(providerStyle.boxShadow, 'none', 'model selector is missing the RetroUI hard shadow')
  await page.getByLabel('文本模型方案').waitFor()
  await page.getByLabel('录音人数').click()
  await page.getByRole('option', { name: '双人' }).click()
  await page.locator('input[type="file"]').first().setInputFiles(fixture)
  await page.getByRole('button', { name: '上传并开始转写' }).click()
  await page.getByText('提交成功', { exact: true }).waitFor({ timeout: 120_000 })
  assert.ok(chunkUploads > 0, 'the first submission did not upload any chunks')
  assert.equal(jobCreates, 1, 'the first submission did not create exactly one job request')
  const successAlert = page.getByRole('alert').filter({ hasText: '提交成功' })
  const successButton = successAlert.getByRole('button', { name: '前往工作空间监测任务' })
  const [alertBox, buttonBox] = await Promise.all([
    successAlert.boundingBox(),
    successButton.boundingBox(),
  ])
  assert.ok(alertBox && buttonBox, 'success alert or action button is not visible')
  assert.ok(buttonBox.x >= alertBox.x && buttonBox.x + buttonBox.width <= alertBox.x + alertBox.width,
    'success action button overflows the alert')
  await page.screenshot({
    path: path.join(screenshotDirectory, 'workspace-submission-success.png'),
    fullPage: true,
  })

  taskPolls = 0
  await page.getByRole('button', { name: '前往工作空间监测任务' }).click()
  await page.getByRole('heading', { name: '转写任务', exact: true }).waitFor()
  await page.getByText('two-speaker-zh.wav', { exact: true }).first().waitFor()
  await page.locator('[role="progressbar"]').first().waitFor()
  await page.waitForTimeout(5_500)
  assert.ok(taskPolls >= 2, `expected an initial load and 5-second poll, got ${taskPolls}`)
  await page.getByText('success', { exact: true }).waitFor({ timeout: 180_000 })

  await page.getByRole('button', { name: '查看独立任务页面' }).click()
  await page.waitForURL(/\/workspace\/tasks\/[0-9a-f-]+$/)
  await page.getByText('success', { exact: true }).waitFor()
  await page.getByText('two-speaker-zh.wav', { exact: true }).first().waitFor()
  await page.locator('[role="progressbar"]').waitFor()
  assert.equal(await page.getByText('时间片段', { exact: true }).count(), 0,
    'independent task detail still renders timestamp segments')
  await page.getByText('双人', { exact: true }).waitFor()
  await page.getByText('用户1', { exact: true }).first().waitFor()
  await page.getByText('用户2', { exact: true }).first().waitFor()
  const leftMessages = page.locator('[data-slot="dialogue-message"][data-side="left"]')
  const rightMessages = page.locator('[data-slot="dialogue-message"][data-side="right"]')
  assert.ok(await leftMessages.count() >= 1, '任务详情应显示左侧对话气泡')
  assert.ok(await rightMessages.count() >= 1, '任务详情应显示右侧对话气泡')
  const leftBox = await leftMessages.first().boundingBox()
  const rightBox = await rightMessages.first().boundingBox()
  assert.ok(leftBox && rightBox && leftBox.x < rightBox.x, '用户对话应按左右位置排列')
  const [htmlDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'HTML', exact: true }).click(),
  ])
  assert.match(htmlDownload.suggestedFilename(), /\.html$/)
  const htmlPath = await htmlDownload.path()
  assert.ok(htmlPath, 'HTML export did not produce a local download')
  const htmlContent = await readFile(htmlPath, 'utf8')
  assert.match(htmlContent, /class="conversation"/)
  assert.match(htmlContent, /message (left|right)/)
  const exportPage = await browser.newPage({ viewport: { width: 1200, height: 900 } })
  await exportPage.setContent(htmlContent)
  await exportPage.getByText('对话转写记录', { exact: true }).waitFor()
  await exportPage.screenshot({ path: path.join(screenshotDirectory, 'dialogue-html-export.png'), fullPage: true })
  await exportPage.close()
  await page.screenshot({
    path: path.join(screenshotDirectory, 'workspace-task-detail.png'),
    fullPage: true,
  })

  await page.getByRole('button', { name: '历史文件', exact: true }).click()
  await page.getByRole('heading', { name: '历史文件', exact: true }).waitFor()
  await page.getByLabel('语音模型方案').waitFor()
  await page.getByLabel('文本模型方案').waitFor()
  await page.getByText('two-speaker-zh.wav', { exact: true }).first().waitFor()
  await page.getByRole('button', { name: '使用所选模型重新解析' }).waitFor()

  chunkUploads = 0
  jobCreates = 0
  await page.getByRole('button', { name: '提交转写', exact: true }).click()
  await page.locator('input[type="file"]').first().setInputFiles(fixture)
  await page.getByRole('button', { name: '上传并开始转写' }).click()
  await page.getByText('已跳过重复文件', { exact: true }).waitFor({ timeout: 120_000 })
  assert.equal(chunkUploads, 0, 'an identical historical file was uploaded again')
  assert.equal(jobCreates, 0, 'an identical historical file created another parsing job')
  verifiedDuplicateChunkUploads = chunkUploads
  verifiedDuplicateJobCreates = jobCreates
  await page.getByRole('button', { name: '前往历史文件' }).click()
  await page.getByRole('heading', { name: '历史文件', exact: true }).waitFor()

  await page.getByRole('button', { name: '转写任务', exact: true }).click()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  const taskDeleteDialog = page.getByRole('alertdialog')
  await taskDeleteDialog.waitFor()
  const dialogStyle = await taskDeleteDialog.evaluate((element) => {
    const style = getComputedStyle(element)
    return { borderWidth: style.borderTopWidth, boxShadow: style.boxShadow }
  })
  assert.equal(dialogStyle.borderWidth, '4px', 'delete dialog is missing the RetroUI border')
  assert.notEqual(dialogStyle.boxShadow, 'none', 'delete dialog is missing the RetroUI hard shadow')
  await taskDeleteDialog.getByRole('button', { name: '取消', exact: true }).click()
  await taskDeleteDialog.waitFor({ state: 'hidden' })
  await page.getByText('two-speaker-zh.wav', { exact: true }).first().waitFor()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: '确认删除', exact: true }).click()
  await page.getByText('暂无转写任务', { exact: true }).waitFor()
  await page.getByRole('button', { name: '历史文件', exact: true }).click()
  await page.getByText('暂无历史文件', { exact: true }).waitFor()

  await page.getByRole('button', { name: '提交转写', exact: true }).click()
  await page.locator('input[type="file"]').first().setInputFiles(fixture)
  await page.getByRole('button', { name: '上传并开始转写' }).click()
  await page.getByText('提交成功', { exact: true }).waitFor({ timeout: 120_000 })
  await page.getByRole('button', { name: '前往工作空间监测任务' }).click()
  await page.getByText('success', { exact: true }).waitFor({ timeout: 180_000 })
  await page.getByRole('button', { name: '历史文件', exact: true }).click()
  await page.getByRole('button', { name: '删除', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: '确认删除', exact: true }).click()
  await page.getByText('暂无历史文件', { exact: true }).waitFor()
  await page.getByRole('button', { name: '转写任务', exact: true }).click()
  await page.getByText('暂无转写任务', { exact: true }).waitFor()
  assert.deepEqual(pageErrors, [], `browser page errors: ${pageErrors.join('; ')}`)

  process.stdout.write(
    `${JSON.stringify({ tenantSlug, headingSize, taskPolls, duplicateChunkUploads: verifiedDuplicateChunkUploads, duplicateJobCreates: verifiedDuplicateJobCreates })}\n`,
  )
} catch (error) {
  process.stderr.write(`pageErrors=${JSON.stringify(pageErrors)}\n`)
  throw error
} finally {
  await browser.close()
}
