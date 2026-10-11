// AI 答疑面板：流式回答 + 停止生成 + 删除某轮对话
// 流式协议（参考 D:\YOder）：ai_start → ai_delta* → (ai_tool*) → ai_done / ai_error
import { renderMarkdown, addCopyButtons } from './markdown.js';
import { wrapTextNodes } from './refs.js';

export function setupAiPanel(opts) {
  const { logEl, textEl, sendEl, client, state, pinPositions } = opts;
  const sidOf = typeof opts.sessionId === 'function' ? opts.sessionId : () => opts.sessionId;

  let nodeIds = [];
  let roundSeq = 0;            // 已出现的用户轮数（= 后端的历史轮序号）
  let cur = null;              // 当前流式中的 assistant 气泡
  let curRound = 0;            // 当前气泡所属轮
  let renderTimer = null;
  let lastRender = 0;
  let streaming = false;

  const setNodes = (ids) => { nodeIds = ids || []; };

  // ---- 停止按钮（插在发送按钮旁边）----
  const stopEl = document.createElement('button');
  stopEl.textContent = '⏹ 停止';
  stopEl.className = 'ai-stop-btn';
  stopEl.style.display = 'none';
  (sendEl.parentNode || logEl.parentNode).insertBefore(stopEl, sendEl.nextSibling);
  stopEl.addEventListener('click', () => {
    client.stopAi(sidOf());
    // 立刻本地停下（后端也在下一个数据块处停），不等网络往返
    finishStream(true);
  });

  function setStreaming(on) {
    streaming = on;
    stopEl.style.display = on ? '' : 'none';
    if (sendEl) sendEl.disabled = on;
    if (textEl) textEl.disabled = on;
  }

  // ---- 流式渲染（节流，避免每个字符都重排 Markdown）----
  function scheduleRender() {
    if (!cur) return;
    const now = performance.now();
    if (now - lastRender >= 100) { renderCur(); return; }
    if (renderTimer) return;
    renderTimer = setTimeout(() => { renderTimer = null; renderCur(); }, 100 - (now - lastRender));
  }

  function renderCur() {
    if (!cur) return;
    lastRender = performance.now();
    setMd(cur.bodyEl, (cur.content || '') + (cur.stopped ? '\n\n*（已停止生成）*' : ''));
    logEl.scrollTop = logEl.scrollHeight;
  }

  function finishStream(stopped) {
    if (!cur) { setStreaming(false); return; }
    cur.stopped = stopped || cur.stopped;
    clearTimeout(renderTimer); renderTimer = null;
    renderCur();
    cur = null;
    setStreaming(false);
  }

  // ══════════ 后端事件 ══════════
  client.onAiStart = () => {
    cur = newAssistantBubble(curRound);
    setStreaming(true);
  };

  client.onAiDelta = (p) => {
    if (!cur) cur = newAssistantBubble(curRound);
    if (!p) return;
    if (p.kind === 'thinking') {
      cur.thinking += p.text || '';
      setMd(cur.thinkEl, cur.thinking);
      cur.thinkBox.style.display = '';
    } else {
      cur.content += p.text || '';
      scheduleRender();
    }
  };

  client.onAiTool = (p) => {
    if (!p) return;
    appendTrace([{ tool: p.name, args: p.args, result: p.result }], curRound);
  };

  client.onAiDone = (p) => {
    finishStream(!!(p && p.stopped));
    if (p && p.trace && p.trace.length && !streaming) appendTrace(p.trace, curRound);
  };

  client.onAiError = (p) => {
    const msg = (p && p.error) || '未知错误';
    if (!cur) { const b = newAssistantBubble(curRound); cur = b; }
    cur.content += (cur.content ? '\n\n' : '') + '⚠️ ' + msg;
    finishStream(false);
  };

  // 旧接口（仅后端早期校验错误会用它）
  client.onAiReply = (p) => {
    if (p && p.error) { append('assistant', '⚠️ ' + p.error, curRound); setStreaming(false); return; }
    const b = newAssistantBubble(curRound);
    b.content = (p && p.content) || '(空回复)';
    if (p && p.reasoning) { b.thinking = p.reasoning; b.thinkBox.style.display = ''; setMd(b.thinkEl, p.reasoning); }
    renderCur();
    finishStream(false);
  };

  // ══════════ 发消息 ══════════
  function send() {
    const text = textEl.value.trim();
    if (!text || streaming) return;
    if (!client.ready) { append('assistant', '⚠️ 未连接求解服务', curRound); return; }
    const mentions = [...text.matchAll(/@([A-Za-z0-9_]+)/g)].map((m) => m[1]);
    append('user', text, roundSeq);
    curRound = roundSeq;              // 本轮序号：user 与其 assistant 共用
    roundSeq++;
    textEl.value = '';
    hidePopup();
    setStreaming(true);               // 立刻切到"停止"，不等 ai_start
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
    if (textEl.value.endsWith('@')) showPopup();
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

  // ══════════ DOM ══════════
  function wrap(el, role, round) {
    el.dataset.round = String(round);
    if (role === 'assistant') {
      const del = document.createElement('button');
      del.className = 'msg-del';
      del.textContent = '×';
      del.title = '删除这一轮（该提问及其回答，之后的也会一起删掉）';
      del.addEventListener('click', (ev) => { ev.stopPropagation(); deleteFrom(round); });
      el.appendChild(del);
    }
    return el;
  }

  function append(role, text, round = roundSeq) {
    const el = document.createElement('div');
    el.className = 'msg ' + role;
    if (role === 'assistant') setMd(el, text);
    else el.textContent = text;
    logEl.appendChild(el);
    wrap(el, role, round);
    logEl.scrollTop = logEl.scrollHeight;
    return el;
  }

  function newAssistantBubble(round) {
    const el = document.createElement('div');
    el.className = 'msg assistant streaming';
    const thinkBox = document.createElement('details');
    thinkBox.className = 'think-box';
    thinkBox.style.display = 'none';
    const s = document.createElement('summary');
    s.textContent = '思维链（生成中…）';
    const thinkEl = document.createElement('div');
    thinkEl.className = 'think md';
    thinkBox.appendChild(s);
    thinkBox.appendChild(thinkEl);
    el.appendChild(thinkBox);
    const bodyEl = document.createElement('div');
    bodyEl.className = 'md';
    el.appendChild(bodyEl);
    logEl.appendChild(el);
    wrap(el, 'assistant', round);
    logEl.scrollTop = logEl.scrollHeight;
    return { el, thinkBox, thinkEl, bodyEl, content: '', thinking: '', stopped: false };
  }

  function setMd(el, text) {
    try {
      el.innerHTML = renderMarkdown(text || '');
      wrapTextNodes(el);         // 把回复里的 n2 / R1 / 5 V 变成可悬停引用（悬停→画布高亮）
      addCopyButtons(el);
    } catch {
      el.textContent = text || '';
    }
  }

  function appendTrace(trace, round = roundSeq) {
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
    wrap(el, 'assistant', round);
    logEl.scrollTop = logEl.scrollHeight;
  }

  // ══════════ 删除某一轮 ══════════
  function deleteFrom(round) {
    const n = String(round);
    if (!confirm(`删除第 ${round + 1} 轮提问及其后的所有对话？（不可撤销）`)) return;
    client.deleteAiRound(sidOf(), round);
    // 本地立刻移除（后端同步删存档里的记录）
    [...logEl.children].forEach((el) => {
      if (Number(el.dataset.round) >= round) el.remove();
    });
    roundSeq = round;
    cur = null;
  }

  // 从后端记录恢复历史（刷新 / 重开后）
  function restore(messages) {
    clearLog();
    for (const m of (messages || [])) {
      if (m.role === 'user') {
        append('user', stripContext(m.content), roundSeq);
        curRound = roundSeq;
        roundSeq++;
      } else if (m.role === 'assistant' && (m.content || m.reasoning_content)) {
        const b = newAssistantBubble(Math.max(0, roundSeq - 1));
        b.thinkBox.remove();
        if (m.content) { b.content = m.content; setMd(b.bodyEl, m.content); }
        if (m.reasoning_content) appendThink(m.reasoning_content, Math.max(0, roundSeq - 1));
      }
    }
    cur = null;
    logEl.scrollTop = logEl.scrollHeight;
  }

  function appendThink(text, round = roundSeq) {
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
    wrap(el, 'assistant', round);
  }

  function stripContext(text) {
    const t = String(text || '');
    const marker = '[用户提问]';
    return t.includes(marker) ? (t.split(marker)[1] || '').trim() : t;
  }

  function clearLog() {
    cur = null;
    setStreaming(false);
    logEl.innerHTML = '';
    roundSeq = 0;
    curRound = 0;
  }

  return { setNodes, send, restore, clear: clearLog, abort: (m) => finishStream(true) };
}
