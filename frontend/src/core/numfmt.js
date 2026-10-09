// 统一的数值格式化：消除浮点噪声、限制有效数字，避免显示“一长串小数”。
// 例：3.3333333333333335 → 3.333；2.5000000000000004 → 2.5；0.0016666… → 0.001667

/** 按有效数字（默认 4 位）取整，消除浮点误差（如 2.5000000000000004 → 2.5）。 */
export function roundSig(v, sig = 4) {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return n === 0 ? 0 : n;
  const r = Number(n.toPrecision(sig));
  return r === 0 ? 0 : r;
}

/** 纯数值显示：如 "2.5"、"3.333"、"0.001667"、"1e-7"。 */
export function fmtNum(v, sig = 4) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '—';
  const n = roundSig(v, sig);
  if (n === 0) return '0';
  return String(n);
}

const ENG = [
  [1e9, 'G'], [1e6, 'M'], [1e3, 'k'], [1, ''],
  [1e-3, 'm'], [1e-6, 'µ'], [1e-9, 'n'], [1e-12, 'p'],
];

/** 带工程前缀 + 单位：1000→"1k"、4700→"4.7k"、0.0025→"2.5m"、0.01→"10m"。 */
export function fmtEng(v, unit = '', sig = 4) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  if (n === 0) return '0' + unit;
  const a = Math.abs(n);
  const [factor, prefix] = ENG.find(([f]) => a >= f) || ENG[ENG.length - 1];
  return `${roundSig(n / factor, sig)}${prefix}${unit}`;
}
