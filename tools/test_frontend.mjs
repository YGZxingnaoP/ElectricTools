/** 前端启动冒烟：esbuild 打包 + DOM 打桩，验证模块顶层不抛异常。
 *  「打开程序不读取存档」正是模块顶层异常（变量在声明前使用）导致的 —— 这个测试能抓到它。
 *  用法：node tools/test_frontend.mjs   （自己会调 esbuild 打包）
 */
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const failures = [];

// 自己打包（避免用旧产物）
try {
  execFileSync('npx', ['esbuild', 'src/main.js', '--bundle', '--format=esm', '--loader:.css=empty',
    '--outfile=../tools/_bundle.mjs'],
    { cwd: 'frontend', stdio: 'pipe', shell: true });
} catch (e) {
  console.log('  FAIL - esbuild 打包失败：' + String(e.message).slice(0, 200));
  process.exit(1);
}
if (!existsSync('tools/_bundle.mjs')) {
  console.log('  FAIL - 没生成打包产物');
  process.exit(1);
}

function fakeEl(id = '') {
  const el = {
    id, tagName: 'DIV', innerHTML: '', textContent: '', value: '', checked: false,
    style: {}, dataset: {}, children: [], files: [],
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener() {}, removeEventListener() {}, appendChild() {}, removeChild() {},
    setAttribute() {}, getAttribute: () => null, focus() {}, blur() {}, click() {},
    querySelector: () => fakeEl(), querySelectorAll: () => [], closest: () => null,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600 }),
    insertAdjacentHTML() {}, scrollIntoView() {}, contains: () => false,
    getContext: () => ctx2d,
  };
  return el;
}
const ctx2d = new Proxy({}, {
  get: (t, k) => {
    if (k === 'canvas') return fakeEl('canvas');
    if (k === 'measureText') return () => ({ width: 10 });
    if (k === 'createLinearGradient' || k === 'createRadialGradient') return () => ({ addColorStop() {} });
    if (k === 'getImageData') return () => ({ data: new Uint8ClampedArray(4) });
    return () => {};
  },
  set: () => true,
});
const store = new Map();
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.removeEventListener = () => {};
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '', width: '0px', height: '0px' });
try { Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'node', clipboard: { writeText: async () => {} } }, configurable: true }); } catch {}
globalThis.alert = () => {};
globalThis.confirm = () => false;
globalThis.prompt = () => null;
globalThis.location = { href: 'http://127.0.0.1:5173/', protocol: 'http:', host: '127.0.0.1:5173' };
globalThis.devicePixelRatio = 1;
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
globalThis.document = {
  getElementById: (id) => fakeEl(id),
  querySelector: () => fakeEl(),
  querySelectorAll: () => [],
  createElement: () => fakeEl(),
  createElementNS: () => fakeEl(),
  addEventListener() {}, body: fakeEl('body'), documentElement: fakeEl('html'),
};
globalThis.requestAnimationFrame = (fn) => setTimeout(() => fn(0), 0);
globalThis.cancelAnimationFrame = () => {};
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
globalThis.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
globalThis.WebSocket = class { constructor() { this.readyState = 1; } send() {} close() {} };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => '' });
globalThis.katex = { render: () => {}, renderToString: () => '' };

try {
  await import('./_bundle.mjs');
  console.log('  ok   - 前端主模块加载成功（没有顶层异常）');
} catch (err) {
  failures.push(err);
  console.log('  FAIL - 主模块加载就抛异常：' + err.constructor.name + ': ' + err.message);
  console.log('         ' + String(err.stack || '').split('\n').slice(0, 5).join('\n         '));
}

// 启动后跑一小会儿，看有没有异步异常（存档读取就发生在这阶段）
await new Promise((r) => setTimeout(r, 300));
console.log(failures.length ? '  FAIL - 启动阶段有异常' : '  ok   - 启动阶段（含存档读取路径）无异常');
process.exit(failures.length ? 1 : 0);
