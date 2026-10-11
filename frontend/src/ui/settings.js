// 设置弹窗：DeepSeek API / 短期记忆 / 界面选项
export function setupSettings(opts) {
  const { button, modal, bodyEl, closeBtn, saveBtn, clearMemBtn, msgEl, onSaved } = opts;
  const nameOf = typeof opts.sessionId === 'function' ? opts.sessionId : () => opts.sessionId;

  const open = async () => {
    msgEl.textContent = '加载中…';
    modal.style.display = 'flex';
    try {
      const r = await fetch('/api/settings');
      const s = await r.json();
      render(s);
      msgEl.textContent = '';
    } catch (e) {
      msgEl.textContent = '加载失败：' + e.message;
    }
  };
  const close = () => { modal.style.display = 'none'; };

  function render(s) {
    const ai = s.ai || {};
    const ui = s.ui || {};
    bodyEl.innerHTML = `
      <div class="form-sec">DeepSeek API</div>
      <div class="form-grid">
        <label class="lab">启用 AI 答疑</label>
        <input type="checkbox" id="s-ai-enabled" ${ai.enabled ? 'checked' : ''} />
        <label class="lab">模型</label>
        <input type="text" id="s-model" value="${esc(ai.model || '')}"
               placeholder="自己填，如 deepseek-flash / gpt-4o-mini / qwen-plus" />
        <label class="lab"></label>
        <span class="hintline">填你的服务商支持的模型名（要跟上面的 Base URL 配套）。</span>
        <label class="lab">API Base URL</label>
        <input type="text" id="s-baseurl" value="${esc(ai.base_url || '')}" />
        <label class="lab">API Key ${ai.api_key_set ? `<span class="hintline">（已设置${esc(ai.api_key_hint || '')}，留空则不修改）</span>` : ''}</label>
        <input type="password" id="s-apikey" placeholder="${ai.api_key_set ? '••••（留空保持不变）' : 'sk-...'}" />
        <label class="lab">思维链 thinking</label>
        <select id="s-thinking">${opt('enabled', ai.thinking)}${opt('disabled', ai.thinking)}</select>
        <label class="lab">推理强度 reasoning_effort</label>
        <select id="s-effort">${opt('low', ai.reasoning_effort)}${opt('high', ai.reasoning_effort)}${opt('max', ai.reasoning_effort)}</select>
        <label class="lab">最大工具调用轮数</label>
        <input type="number" id="s-maxrounds" min="1" max="30" value="${num(ai.max_tool_rounds, 8)}" />
      </div>

      <div class="form-sec">短期记忆</div>
      <div class="form-grid">
        <label class="lab">启用短期记忆</label>
        <input type="checkbox" id="s-mem-enabled" ${ai.memory_enabled ? 'checked' : ''} />
        <label class="lab">保留对话轮数</label>
        <input type="number" id="s-mem-turns" min="0" max="100" value="${num(ai.memory_max_turns, 10)}" />
        <label class="lab"></label>
        <span class="hintline">关闭后每次提问都是无历史的一次性问答；轮数用于裁剪过久的历史（按用户提问边界裁剪，不破坏工具调用配对）。</span>
      </div>

      <div class="form-sec">界面与求解</div>
      <div class="form-grid">
        <label class="lab">电流方向约定</label>
        <select id="s-conv">${opt('reference', ui.current_convention, '参考方向（被动符号约定，课程）')}${opt('actual', ui.current_convention, '实际方向')}</select>
        <label class="lab">AC 表示域</label>
        <select id="s-ac">${opt('phasor', ui.ac_domain, '相量 / 频域')}${opt('timedomain', ui.ac_domain, '时域')}</select>
        <label class="lab">显示电流箭头</label>
        <input type="checkbox" id="s-arrows" ${ui.show_current_arrows !== false ? 'checked' : ''} />
        <label class="lab">电流动画</label>
        <input type="checkbox" id="s-anim" ${ui.current_animation !== false ? 'checked' : ''} />
        <label class="lab">动画速度倍率</label>
        <input type="number" id="s-speed" step="0.1" min="0.1" max="4" value="${num(ui.current_flow_speed, 1)}" />
        <label class="lab">吸附半径 (px)</label>
        <input type="number" id="s-snap" min="4" max="40" value="${num(ui.snap_radius_px, 14)}" />
      </div>
    `;
  }

  const collect = () => {
    const v = (id) => document.getElementById(id);
    const patch = {
      ai: {
        enabled: v('s-ai-enabled').checked,
        model: v('s-model').value,
        base_url: v('s-baseurl').value.trim(),
        thinking: v('s-thinking').value,
        reasoning_effort: v('s-effort').value,
        max_tool_rounds: parseInt(v('s-maxrounds').value, 10) || 8,
        memory_enabled: v('s-mem-enabled').checked,
        memory_max_turns: parseInt(v('s-mem-turns').value, 10) || 0
      },
      ui: {
        current_convention: v('s-conv').value,
        ac_domain: v('s-ac').value,
        show_current_arrows: v('s-arrows').checked,
        current_animation: v('s-anim').checked,
        current_flow_speed: parseFloat(v('s-speed').value) || 1,
        snap_radius_px: parseInt(v('s-snap').value, 10) || 14
      }
    };
    const key = v('s-apikey').value.trim();
    if (key) patch.ai.api_key = key;      // 留空则不修改
    return patch;
  };

  const save = async () => {
    msgEl.textContent = '保存中…';
    try {
      const r = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collect())
      });
      const s = await r.json();
      msgEl.textContent = '已保存 ✓';
      onSaved && onSaved(s);
      setTimeout(() => { msgEl.textContent = ''; }, 1500);
    } catch (e) {
      msgEl.textContent = '保存失败：' + e.message;
    }
  };

  const clearMemory = async () => {
    const name = nameOf();
    if (!name) { msgEl.textContent = '当前没有存档'; return; }
    if (!confirm(`清空存档「${name}」的聊天记录？（电路与结果不受影响）`)) return;
    try {
      await fetch('/api/memory/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      msgEl.textContent = '已清空本存档的聊天记录 ✓';
      setTimeout(() => { msgEl.textContent = ''; }, 1500);
    } catch (e) {
      msgEl.textContent = '清空失败：' + e.message;
    }
  };

  button && button.addEventListener('click', open);
  closeBtn && closeBtn.addEventListener('click', close);
  saveBtn && saveBtn.addEventListener('click', save);
  clearMemBtn && clearMemBtn.addEventListener('click', clearMemory);
  modal && modal.addEventListener('click', (e) => { if (e.target === modal) close(); });

  return { open, close, save };
}

function opt(value, current, label) {
  const sel = value === current ? 'selected' : '';
  return `<option value="${value}" ${sel}>${esc(label || value)}</option>`;
}
function num(v, d) {
  return v === null || v === undefined || Number.isNaN(Number(v)) ? d : v;
}
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
