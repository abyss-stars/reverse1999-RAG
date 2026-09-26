/**
 * 前端端到端验证（无需第三方依赖）。
 *
 * 为什么不用 `edge --screenshot`：那种方式要靠 `--virtual-time-budget` 等页面"跑完"，
 * 而虚拟时钟会被 setInterval（我们的计时器）瞬间烧完，于是截图总是停在流式中途。
 * 这里改用 CDP：真起一个 headless 浏览器，**轮询 DOM 直到回答落地**再断言 + 截图。
 *
 * 用法：
 *   node scripts/verify-app.mjs                       # 默认跑一条真问题
 *   node scripts/verify-app.mjs --base http://localhost:5173
 *   node scripts/verify-app.mjs --question "…" --preset sweep --timeout 180000
 *
 * 退出码：0 = 全部断言通过；1 = 有断言失败。
 */

import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = resolve(HERE, '..', '..', 'docs', 'ref')

const argv = process.argv.slice(2)
const arg = (name, fallback) => {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback
}

const BASE = arg('base', 'http://localhost:5173')
const QUESTION = arg('question', '「这是我的箱子，请还给我。」这句话是谁说的？')
const PRESET = arg('preset', 'pinpoint')
const VER = arg('ver', '')
const CAT = arg('cat', '')
const CH = arg('ch', '')
/** 传了就把视口模拟成这个宽度（用于验窄屏无横向溢出）。 */
const WIDTH = Number(arg('width', '0')) || 0
const TIMEOUT = Number(arg('timeout', '240000'))
const PORT = Number(arg('port', '9222'))
const EDGE =
  arg('edge', '') ||
  [
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ].find((p) => existsSync(p))

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitForPort() {
  const deadline = Date.now() + 20000
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/version`)
      if (res.ok) return true
    } catch {
      /* not up yet */
    }
    await sleep(300)
  }
  return false
}

async function main() {
  if (!EDGE) {
    console.error('[x] 找不到 Edge/Chrome，可用 --edge <path> 指定。')
    process.exit(1)
  }

  const extra = [
    VER ? `ver=${encodeURIComponent(VER)}` : '',
    CAT ? `cat=${encodeURIComponent(CAT)}` : '',
    CH ? `ch=${encodeURIComponent(CH)}` : '',
  ]
    .filter(Boolean)
    .join('&')
  const url = `${BASE}/#/?q=${encodeURIComponent(QUESTION)}&preset=${encodeURIComponent(PRESET)}${extra ? `&${extra}` : ''}`
  console.log(`[i] 目标: ${url}`)

  const child = spawn(
    EDGE,
    [
      '--headless=new',
      '--disable-gpu',
      '--hide-scrollbars',
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${resolve(OUT_DIR, 'edge-profile')}`,
      '--window-size=1440,1400',
      '--no-first-run',
      url,
    ],
    { stdio: 'ignore' },
  )

  try {
    if (!(await waitForPort())) throw new Error('调试端口未就绪')

    // 找到页面 target
    let target = null
    for (let i = 0; i < 40 && !target; i++) {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
      target = list.find((t) => t.type === 'page' && t.url.includes('localhost'))
      if (!target) await sleep(500)
    }
    if (!target) throw new Error('没找到页面 target')

    const ws = new WebSocket(target.webSocketDebuggerUrl)
    await new Promise((res, rej) => {
      ws.onopen = res
      ws.onerror = rej
    })

    let id = 0
    const pending = new Map()
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && pending.has(msg.id)) {
        pending.get(msg.id)(msg)
        pending.delete(msg.id)
      }
    }
    const send = (method, params = {}) =>
      new Promise((res) => {
        const myId = ++id
        pending.set(myId, res)
        ws.send(JSON.stringify({ id: myId, method, params }))
      })

    const evaluate = async (expression) => {
      const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: false })
      return r.result?.result?.value
    }

    await send('Runtime.enable')

    // 窄屏验证用 CDP 直接模拟视口 —— 比 `--window-size` 可靠：
    // Windows 上 headless 浏览器有最小窗口宽度（约 500px），给 390 也只会得到 504px 布局视口。
    if (WIDTH > 0) {
      await send('Emulation.setDeviceMetricsOverride', {
        width: WIDTH,
        height: 900,
        deviceScaleFactor: 1,
        mobile: WIDTH < 760,
      })
      console.log(`[i] 已模拟视口宽度 ${WIDTH}px`)
    }

    // 轮询：等 .readout 出现（它只在流式结束后渲染）
    const started = Date.now()
    let readout = null
    let lastStage = ''
    while (Date.now() - started < TIMEOUT) {
      const stage = await evaluate(`document.querySelector('.chip.on')?.textContent || ''`)
      if (stage && stage !== lastStage) {
        lastStage = stage
        console.log(`[i] 阶段: ${stage}  (${((Date.now() - started) / 1000).toFixed(1)}s)`)
      }
      readout = await evaluate(`document.querySelector('.readout')?.textContent || null`)
      if (readout) break
      await sleep(500)
    }

    const answerText = await evaluate(`document.querySelector('.ans-body')?.innerText || ''`)
    const refCount = await evaluate(`document.querySelectorAll('.ref[id]').length`)
    const ungrounded = await evaluate(
      `!!document.querySelector('.ans-body .ph-note') && document.querySelector('.ans-body .ph-note').textContent.includes('未检索到可靠依据')`,
    )
    const citeCount = await evaluate(`document.querySelectorAll('.ans-body .cite').length`)
    const firstRefWhere = await evaluate(`document.querySelector('.ref .where')?.textContent || ''`)
    const scopeReport = await evaluate(`document.querySelector('.scope-report')?.innerText || ''`)
    // 错误框也必须留证：否则"正文为空"会被误当成模型没答，而不是后端报错。
    const errBox = await evaluate(`document.querySelector('.err')?.innerText || ''`)
    const refFiles = await evaluate(
      `Array.from(document.querySelectorAll('.ref .file')).map(e=>e.textContent).join('|')`,
    )
    const metrics = await evaluate(
      `JSON.stringify({vw: document.documentElement.clientWidth, sw: document.documentElement.scrollWidth})`,
    )
    const { vw, sw } = JSON.parse(metrics || '{"vw":0,"sw":0}')

    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    mkdirSync(OUT_DIR, { recursive: true })
    const shotPath = resolve(OUT_DIR, 'app-e2e.png')
    writeFileSync(shotPath, Buffer.from(shot.result.data, 'base64'))

    // 折叠上限 + 角标提升。放在截图之后做，避免改动 DOM 影响留档截图。
    // 只断言"卡片 ≤ 4"是不够的：正文里可能写着 [7]、而第 7 条被折叠掉，
    // 点角标毫无反应 —— 那才是这条需求最容易出的回归。
    // 一次点多个（最多 5 个）不同的 >4 角标：单点一个若偶发失败会像是"没实现"，
    // 多点几个才分得清是"实现不对"还是"某个编号有问题"。
    // aria-pressed 用来看点击是否真的到达了 React（它直接反映 AnswerPanel 的 active）。
    const idsOf = `JSON.stringify(Array.from(document.querySelectorAll('.ref[id]')).map((e) => e.id))`
    const idsBefore = await evaluate(idsOf)
    const badges = JSON.parse(
      (await evaluate(
        `JSON.stringify(Array.from(document.querySelectorAll('.ans-body .cite')).map((b) => Number(b.textContent.trim())))`,
      )) || '[]',
    )
    const targets = [...new Set(badges.filter((n) => n > 4))].slice(0, 5)

    const promo = []
    for (const n of targets) {
      const before = JSON.parse((await evaluate(idsOf)) || '[]').includes(`ref-${n}`)
      await evaluate(
        `Array.from(document.querySelectorAll('.ans-body .cite')).find((b) => Number(b.textContent.trim()) === ${n}).click()`,
      )
      await sleep(500)
      const after = JSON.parse((await evaluate(idsOf)) || '[]').includes(`ref-${n}`)
      const pressed = await evaluate(
        `Array.from(document.querySelectorAll('.ans-body .cite')).find((b) => Number(b.textContent.trim()) === ${n})?.getAttribute('aria-pressed')`,
      )
      promo.push({ n, before, after, pressed })
    }
    const idsAfter = await evaluate(idsOf)

    const checks = [
      ['流程走完（readout 出现）', Boolean(readout)],
      ['拿到答案正文', (answerText ?? '').length > 20],
      ['答案里含引用角标', Number(citeCount) > 0],
      ['引用面板有卡片', Number(refCount) > 0],
      ['默认最多展示 4 条引用卡', Number(refCount) <= 4],
      ['引用卡解析出了章节信息', /第 \d+ 章/.test(firstRefWhere ?? '')],
      ['未被判为无依据', ungrounded === false],
    ]
    if (promo.length) {
      const bad = promo.filter((p) => p.after !== true)
      checks.push([
        `点击 ${promo.length} 个 >4 的角标，全部被提升为可见（${promo.map((p) => `[${p.n}]`).join(' ')}）`,
        bad.length === 0,
        bad.length ? `未提升: ${bad.map((p) => `[${p.n}](before=${p.before},pressed=${p.pressed})`).join(' ')}` : '',
      ])
    } else {
      console.log(`[i] 本次回答没有编号 > 4 的角标，跳过「角标提升」验证（上限断言仍生效）`)
    }
    if (VER || CAT || CH) {
      checks.push(['显示了范围限定回报条', Boolean(scopeReport && scopeReport.includes('已限定检索范围'))])
    }
    // 验收标准 6：窄屏无横向溢出
    checks.push([`无横向溢出（${WIDTH || '窗口'}px, scrollWidth ${sw} ≤ ${vw}）`, sw <= vw + 1])

    console.log('\n=== 断言 ===')
    let failed = 0
    for (const [name, ok, extra] of checks) {
      console.log(`  ${ok ? '[PASS]' : '[FAIL]'} ${name}${!ok && extra ? `  ← ${extra}` : ''}`)
      if (!ok) failed++
    }

    console.log('\n=== 取证 ===')
    console.log(`  用时        : ${((Date.now() - started) / 1000).toFixed(1)}s`)
    console.log(`  readout     : ${readout}`)
    console.log(`  正文长度    : ${(answerText ?? '').length}`)
    console.log(`  引用角标/卡片: ${citeCount} / ${refCount}`)
    console.log(
      `  折叠上限    : 默认 ${refCount} 张；点过 ${promo.length} 个角标 -> ` +
        (promo.length
          ? promo.map((p) => `[${p.n}]${p.after ? '✓' : '✗'}(pressed=${p.pressed})`).join(' ')
          : '本次无 >4 的角标'),
    )
    console.log(`  引用卡 id   : 点前 ${idsBefore}`)
    if (promo.length) console.log(`               点后 ${idsAfter}`)
    console.log(`  首条引用    : ${firstRefWhere}`)
    if (errBox) console.log(`  错误框      : ${String(errBox).replace(/\s+/g, ' ')}`)
    if (scopeReport) console.log(`  范围回报    : ${String(scopeReport).replace(/\s+/g, ' ')}`)
    if (refFiles) console.log(`  引用文件    : ${String(refFiles).split('|').join(', ')}`)
    console.log(`  首 160 字   : ${(answerText ?? '').replace(/\s+/g, ' ').slice(0, 160)}`)
    console.log(`  截图        : ${shotPath}`)

    ws.close()
    process.exit(failed === 0 ? 0 : 1)
  } finally {
    child.kill()
  }
}

main().catch((e) => {
  console.error('[x]', e)
  process.exit(1)
})
