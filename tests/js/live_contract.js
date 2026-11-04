// 共享实时控制器的真实行为验证（由 tests/test_audit_regressions.py 调用）。
//
// 输入：stdin = 渲染后的 dashboard.html
// 做法：抽出 SAPPER_LIVE_START / SAPPER_LIVE_END 两个标记之间的共享 JS，
//      在 Node vm 里注入最小 DOM、fetch、location、storage 桩，真实执行。
// 覆盖：暂停不刷新、只认已渲染版本、HTTP 错误/脏响应/断连不刷新、
//      postLive 失败不乐观翻转、file 协议不轮询、跨页语言状态。
'use strict';

const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync(0, 'utf8');
const match = html.match(/\/\* SAPPER_LIVE_START \*\/([\s\S]*?)\/\* SAPPER_LIVE_END \*\//);
if (!match) {
  console.error('FAIL: dashboard.html 缺少共享实时控制器标记');
  process.exit(2);
}
const code = match[1];

function makeEl(id) {
  const classes = new Set();
  return {
    id,
    textContent: '',
    hidden: false,
    disabled: false,
    className: '',
    value: '',
    style: {},
    children: [],
    tagName: 'DIV',
    classList: {
      add(...items) { items.forEach((x) => classes.add(x)); },
      remove(...items) { items.forEach((x) => classes.delete(x)); },
      contains(item) { return classes.has(item); },
    },
    handlers: {},
    addEventListener(event, fn) { this.handlers[event] = fn; },
    click() { if (this.handlers.click) this.handlers.click.call(this); },
    setAttribute() {},
    getAttribute() { return null; },
    querySelectorAll() { return []; },
    appendChild() {},
  };
}

function makeContext(fetchImpl, protocol, sharedStore) {
  const elements = {};
  const store = sharedStore || {};
  const session = {};
  const document = {
    getElementById(id) {
      if (!elements[id]) elements[id] = makeEl(id);
      return elements[id];
    },
    querySelectorAll() { return []; },
    documentElement: { lang: '' },
    body: { classList: { add() {}, remove() {} }, children: [] },
  };
  const location = {
    protocol: protocol || 'http:',
    reloads: 0,
    reload() { this.reloads += 1; },
  };
  const ctx = {
    document,
    location,
    console,
    localStorage: {
      getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
      setItem(k, v) { store[k] = String(v); },
    },
    sessionStorage: {
      getItem(k) { return Object.prototype.hasOwnProperty.call(session, k) ? session[k] : null; },
      setItem(k, v) { session[k] = String(v); },
    },
    fetch: fetchImpl,
    setInterval() { return 1; },
    clearInterval() {},
    requestAnimationFrame(cb) { cb(); },
    setTimeout(cb) { cb(); return 1; },
    window: { addEventListener() {} },
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  return { ctx, elements, location };
}

const START = { badgeId: 'live-badge', textId: 'live-text', toggleId: 'live-toggle' };

function version(ledger, rendered, live) {
  return {
    ledger_sha256: ledger,
    rendered_sha256: rendered,
    rendered_at: '2026-01-01T00:00:00Z',
    live_enabled: live,
    now: '2026-01-01T00:00:00Z',
  };
}
function ok(payload) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
}
function bad(status) {
  return Promise.resolve({ ok: false, status, json: () => Promise.resolve({ error: 'boom' }) });
}
function down() {
  return Promise.reject(new Error('connection lost'));
}
function queue(responders) {
  let i = 0;
  return function () {
    const responder = responders[Math.min(i, responders.length - 1)];
    i += 1;
    return responder();
  };
}
async function settle() {
  for (let i = 0; i < 5; i += 1) await new Promise((r) => setImmediate(r));
}

const failures = [];
function check(condition, message) {
  if (!condition) failures.push(`FAIL: ${message}`);
}

async function main() {
  // 1. 暂停态：账本 hash 变了也不能 reload（H1）
  {
    const env = makeContext(queue([() => ok(version('NEW', 'OLD', false))]));
    env.ctx.SapperLive.start(START);
    await settle();
    check(env.ctx.SapperLive.state.status === 'paused', '暂停时状态应为 paused');
    check(env.location.reloads === 0, '暂停时不得整页 reload');
    await env.ctx.SapperLive.poll();
    await settle();
    check(env.location.reloads === 0, '暂停态持续时不得 reload');
  }

  // 2. 已渲染版本变化才刷新（H2）
  {
    const env = makeContext(queue([
      () => ok(version('A', 'A', true)),
      () => ok(version('B', 'B', true)),
    ]));
    env.ctx.SapperLive.start(START);
    await settle();
    check(env.location.reloads === 0, '首次探测不得 reload');
    await env.ctx.SapperLive.poll();
    await settle();
    check(env.location.reloads === 1, 'rendered_sha256 变化应触发一次 reload');
  }

  // 3. 渲染竞态：账本先变、HTML 未重渲染时不得刷新（H2 核心）
  {
    const env = makeContext(queue([
      () => ok(version('A', 'A', true)),
      () => ok(version('B', 'A', true)),
      () => ok(version('B', 'B', true)),
    ]));
    env.ctx.SapperLive.start(START);
    await settle();
    await env.ctx.SapperLive.poll();
    await settle();
    check(env.location.reloads === 0, '账本先变但尚未重渲染时不得 reload');
    await env.ctx.SapperLive.poll();
    await settle();
    check(env.location.reloads === 1, '重渲染完成后才 reload');
  }

  // 4. HTTP 500：显式错误态，不得刷新风暴（H3）
  {
    const env = makeContext(queue([() => bad(500)]));
    env.ctx.SapperLive.start(START);
    await settle();
    check(env.ctx.SapperLive.state.status === 'error', 'HTTP 500 应显示 error 态');
    check(env.location.reloads === 0, 'HTTP 500 不得 reload');
  }

  // 5. 脏响应（无 rendered_sha256）：不得当作版本变化（H3）
  {
    const env = makeContext(queue([() => ok({ error: 'half-written ledger line' })]));
    env.ctx.SapperLive.start(START);
    await settle();
    check(env.ctx.SapperLive.state.status === 'error', '脏响应应显示 error 态');
    check(env.location.reloads === 0, '脏响应不得 reload');
  }

  // 6. 连接断开：区分 disconnected，保持轮询不放弃（H3 / M7）
  {
    const env = makeContext(queue([down]));
    env.ctx.SapperLive.start(START);
    await settle();
    check(env.ctx.SapperLive.state.status === 'disconnected', '网络失败应显示 disconnected');
    check(env.location.reloads === 0, '连接断开不得 reload');
  }

  // 7. postLive 失败不乐观翻转；成功后按服务端响应更新（M7）
  {
    const env = makeContext((url, options) => {
      if (options && options.method === 'POST') return down();
      return ok(version('A', 'A', true));
    });
    env.ctx.SapperLive.start(START);
    await settle();
    check(env.ctx.SapperLive.state.on === true, '初始应为 live');
    await env.ctx.SapperLive.postLive(false);
    await settle();
    check(env.ctx.SapperLive.state.on === true, 'POST 失败不得乐观翻转开关');
    check(env.ctx.SapperLive.state.status === 'error', 'POST 失败应显示 error 态');
  }
  {
    const env = makeContext((url, options) => {
      if (options && options.method === 'POST') return ok({ live_enabled: false, now: 't' });
      return ok(version('A', 'A', true));
    });
    env.ctx.SapperLive.start(START);
    await settle();
    await env.ctx.SapperLive.postLive(false);
    await settle();
    check(env.ctx.SapperLive.state.on === false, 'POST 成功后应落到服务端状态');
    check(env.ctx.SapperLive.state.status === 'paused', 'POST 成功后应显示暂停态');
  }

  // 8. file:// 离线快照：不发起任何请求
  {
    let calls = 0;
    const env = makeContext(() => { calls += 1; return ok(version('A', 'A', true)); }, 'file:');
    env.ctx.SapperLive.start(START);
    await settle();
    check(calls === 0, 'file:// 不得发起轮询请求');
    check(env.ctx.SapperLive.state.status === 'offline', 'file:// 应显示离线快照');
  }

  // 9. 跨页语言：写入 localStorage，另一页面读取同一状态（M3）
  {
    const shared = {};
    const first = makeContext(() => ok(version('A', 'A', true)), 'http:', shared);
    first.ctx.SapperLang.bind();
    first.ctx.SapperLang.toggle();
    const second = makeContext(() => ok(version('A', 'A', true)), 'http:', shared);
    check(second.ctx.SapperLang.current() === 'en', '语言状态应跨页保持');
  }

  if (failures.length) {
    console.error(failures.join('\n'));
    process.exit(1);
  }
  console.log('LIVE_JS_OK 9 scenarios');
}

main().catch((err) => {
  console.error(`FAIL: 控制器执行异常: ${err && err.stack ? err.stack : err}`);
  process.exit(1);
});
