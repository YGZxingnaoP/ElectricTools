// AI 答疑面板：提问、@节点选择、思维链/工具轨迹展示（Markdown + KaTeX 渲染）
import { renderMarkdown, addCopyButtons } from './markdown.js';

export function setupAiPanel(opts) {
  const { logEl, textEl, sendEl, client, state, pinPositions } = opts;
  const sidOf = typeof opts.sessionId === 'function' ? opts.sessionId : () => opts.sessionId;
  let nodeIds = [];
  let pendingEl = null;
  let pendingTimer = null;

  const setNodes = (ids) => { nodeIds = ids || []; };

  // 清除「思考中…」占位（可附带一条提示）
  function clearPending(msg) {
    if (pendingTimer) { clearTimeout(pendingTimer); pendingTimer = null; }
    if (pendingEl) { pendingEl.remove(); pendingEl = null; }
    if (msg) append('assistant', msg);
  }
  // 供外部（连接断开等）调用，避免「思考中…」永远卡住
  const abort = (msg) => { if (pendingEl) clearPending(msg || '⚠️ 请求已中断。'); };

  client.onAiReply = (p) => {
    clearPending();
    if (p && p.error) { append('assistant', '⚠️ ' + p.error); return; }
    if (p && p.reasoning) appendThink(p.reasoning);
    append('assistant', (p && p.content) || '(空回复)');
    if (p && p.trace && p.trace.length) appendTrace(p.trace);
  };

  function send() {
    const text = textEl.value.trim();
    if (!text) return;
    if (!client.ready) { append('assistant', '⚠️ 未连接求解服务'); return; }
    const mentions = [...text.matchAll(/@([A-Za-z0-9_]+)/g)].map((m) => m[1]);
    append('user', text);
    textEl.value = '';
    hidePopup();
    clearPending();
    pendingEl = append('assistant', '思考中…');
    // 安全网：长时间无响应（AI 超时 / 后端无响应）时解除卡住状态
    pendingTimer = setTimeout(() => {
      if (pendingEl) clearPending('⚠️ 长时间未收到回复（可能 AI 超时或后端无响应），请重试。');
    }, 240000);
    client.ask(sidOf(), text, state.toNetlist(pinPositions), mentions);
  }

  sendEl.addEventListener('click', send);
  textEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });

  // ---- @ 节点选择 ----
  const popup = document.createElement('div');
  popup.className = 'mention-popup';
  popup.style.display = 'none';
  document.body.appendChild(popup);

  textEl.addEventListener('input', () => {
    const v = textEl.value;
    if (v.endsWith('@')) showPopup();
    else hidePopup();
  });

  function showPopup() {
    if (!nodeIds.length) { hidePopup(); return; }
    const r = textEl.getBoundingClientRect();
    popup.style.left = r.left + 'px';
    popup.style.top = (r.top - 8) + 'px';
    popup.innerHTML = nodeIds.map((n) => `<div data-n="${n}">@${n}</div>`).join('');
    popup.style.display = 'block';
    popup.querySelectorAll('div').forEach((d) => {
      d.onclick = () => {
        textEl.value = textEl.value + d.dataset.n + ' ';
        hidePopup();
        textEl.focus();
      };
    });
  }
  function hidePopup() { popup.style.display = 'none'; }

  // ---- DOM 辅助 ----
  function append(role, text, isPending) {
    const el = document.createElement('div');
    el.className = 'msg ' + role + (isPending ? ' pending' : '');
    if (role === 'assistant') {
      setMd(el, text);
    } else {
      el.textContent = text;          // 用户输入按纯文本显示
    }
    logEl.appendChild(el);
    logEl.scrollTop = logEl.scrollHeight;
    return el;
  }

  function setMd(el, text) {
    try {
      el.innerHTML = renderMarkdown(text);
      addCopyButtons(el);
    } catch {
      el.textContent = text;
    }
  }

  function appendThink(text) {
    const el = document.createElement('details');
    el.className = 'msg assistant think-box';
    const s = document.createElement('summary');
    s.textContent = '思维链（点击展开）';
    const body = document.createElement('div');
    body.className = 'think md';
    setMd(body, text);
    el.appendChild(s);
    el.appendChild(body);
    logEl.appendChild(el);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function appendTrace(trace) {
    const el = document.createElement('details');
    el.className = 'msg assistant trace-box';
    const s = document.createElement('summary');
    s.textContent = `工具调用（${trace.length}）`;
    el.appendChild(s);
    const box = document.createElement('div');
    box.className = 'think md';
    const lines = trace
      .map((t) => `▸ ${t.tool}(${JSON.stringify(t.args)})\n   → ${JSON.stringify(t.result).slice(0, 400)}`)
      .join('\n\n');
    setMd(box, '```text\n' + lines + '\n```');
    el.appendChild(box);
    logEl.appendChild(el);
    logEl.scrollTop = logEl.scrollHeight;
  }

  // 从后端记录恢复历史（刷新 / 重开后）
  function restore(messages) {
    clearPending();
    logEl.innerHTML = '';
    for (const m of (messages || [])) {
      if (m.role === 'user') append('user', stripContext(m.content));
      else if (m.role === 'assistant' && m.content) append('assistant', m.content);
    }
    logEl.scrollTop = logEl.scrollHeight;
  }

  function stripContext(text) {
    const t = String(text || '');
    const marker = '[用户提问]';
    if (!t.includes(marker)) return t;
    const parts = t.split(marker);
    return (parts[1] || '').trim();
  }

  function clearLog() {
    clearPending();
    logEl.innerHTML = '';
  }

  return { setNodes, send, restore, clear: clearLog, abort };
}
