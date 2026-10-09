// Markdown 公式保护（纯函数，无 DOM / 无外部依赖，便于单测）
//
// 目标：把 $...$ 与 $$...$$ 先替换为占位符，交给 marked 解析，最后再插回
// KaTeX 渲染后的 HTML。这样 KaTeX 生成的 <span>/<math> 不会被消毒环节破坏。
// 同时避免把「围栏代码块」与「行内代码」里的 $ 误当成公式。

const PLACEHOLDER = '@@MATH';

export function protectMath(text, render) {
  const stash = [];
  const store = (html) => {
    stash.push(html);
    return `${PLACEHOLDER}${stash.length - 1}@@`;
  };

  const parts = String(text ?? '').split(/(```[\s\S]*?```)/g);
  const prepared = parts
    .map((part, i) => {
      if (i % 2 === 1) return part; // 围栏代码块：原样保留
      return part
        .split(/(`[^`]*`)/g)
        .map((seg, j) => {
          if (j % 2 === 1) return seg; // 行内代码：原样保留
          return seg
            .replace(/\$\$([\s\S]+?)\$\$/g, (_m, tex) => store(render(tex, true)))
            .replace(/\$([^$\n]+?)\$/g, (_m, tex) => store(render(tex, false)));
        })
        .join('');
    })
    .join('');

  return { text: prepared, stash };
}

export function restoreMath(html, stash) {
  return String(html ?? '').replace(/@@MATH(\d+)@@/g, (_m, n) => stash[Number(n)] ?? '');
}
