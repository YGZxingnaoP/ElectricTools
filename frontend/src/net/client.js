// WebSocket 客户端（主通道）：实时求解 + 断线重连
export class SolverClient {
  constructor(url) {
    this.url = url;
    this.ws = null;
    this.seq = 0;
    this.onStatus = null;   // (state: 'on'|'off') => void
    this.onResult = null;   // (payload) => void
    this.onAiReply = null;  // (payload) => void   旧接口（仅早期校验错误用）
    this.onAiStart = null;  // () => void
    this.onAiDelta = null;  // ({kind:'thinking'|'content', text}) => void
    this.onAiTool = null;   // ({name, args, result}) => void
    this.onAiDone = null;   // ({stopped, trace}) => void
    this.onAiError = null;  // ({error}) => void
    this.onAiStopped = null; // () => void  后端确认收到停止
    this.onAiDeleted = null; // ({removed}) => void
    this.onNodeDetail = null; // (payload) => void
    this.onError = null;
    this._retry = 0;
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url);
    } catch (e) {
      this._scheduleReconnect();
      return;
    }
    this.ws.onopen = () => { this._retry = 0; this.onStatus && this.onStatus('on'); };
    this.ws.onclose = () => { this.onStatus && this.onStatus('off'); this._scheduleReconnect(); };
    this.ws.onerror = () => { this.onStatus && this.onStatus('off'); };
    this.ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === 'solve_result') this.onResult && this.onResult(msg.payload);
      else if (msg.type === 'sweep_result') this.onSweep && this.onSweep(msg.payload);
      else if (msg.type === 'ai_reply') this.onAiReply && this.onAiReply(msg.payload);
      else if (msg.type === 'ai_start') this.onAiStart && this.onAiStart(msg.payload);
      else if (msg.type === 'ai_delta') this.onAiDelta && this.onAiDelta(msg.payload);
      else if (msg.type === 'ai_tool') this.onAiTool && this.onAiTool(msg.payload);
      else if (msg.type === 'ai_done') this.onAiDone && this.onAiDone(msg.payload);
      else if (msg.type === 'ai_error') this.onAiError && this.onAiError(msg.payload);
      else if (msg.type === 'ai_stopped') this.onAiStopped && this.onAiStopped(msg.payload);
      else if (msg.type === 'ai_deleted') this.onAiDeleted && this.onAiDeleted(msg.payload);
      else if (msg.type === 'node_detail') this.onNodeDetail && this.onNodeDetail(msg.payload);
      else if (msg.type === 'error') this.onError && this.onError(msg.payload);
    };
  }

  _scheduleReconnect() {
    const delay = Math.min(8000, 500 * 2 ** this._retry++);
    setTimeout(() => this.connect(), delay);
  }

  get ready() { return this.ws && this.ws.readyState === WebSocket.OPEN; }

  send(type, payload) {
    if (!this.ready) return false;
    const id = String(++this.seq);
    this.ws.send(JSON.stringify({ type, id, payload }));
    return true;
  }

  solve(sessionId, schematic, mode, domain = {}) {
    return this.send('solve_request', {
      session_id: sessionId,
      schematic,
      mode,        // numeric | symbolic | both
      analysis: domain.domain || 'dc',
      domain: domain.domain || 'dc',   // dc | ac | tran
      freq: domain.freq,               // 交流频率 Hz
      tstop: domain.tstop,             // 暂态终止时间 s
      nsteps: domain.nsteps            // 暂态步数
    });
  }

  sweep(sessionId, schematic, f0 = 10, f1 = 1e5, points = 61, kind = 'reactive') {
    return this.send('sweep_request', {
      session_id: sessionId, schematic, f0, f1, points, kind,
    });
  }

  ask(sessionId, message, schematic, mentions) {
    return this.send('ai_chat', {
      session_id: sessionId,
      message,
      schematic,
      mentions: mentions || []
    });
  }

  /** 停止正在生成的回答（后端在数据块之间轮询该标志） */
  stopAi(sessionId) {
    return this.send('ai_stop', { session_id: sessionId });
  }

  /** 删除第 round 轮（该轮 user 消息及其后的全部记录） */
  deleteAiRound(sessionId, round) {
    return this.send('ai_delete_round', { session_id: sessionId, round });
  }

  probe(sessionId, node, schematic) {
    return this.send('node_probe', { session_id: sessionId, node, schematic });
  }
}
