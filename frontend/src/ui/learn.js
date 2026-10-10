/**
 * 学习文档：以可视化方式介绍各种计算方法与公式。
 * 打开方式：左侧「学习文档」按钮 → 弹出独立卡片窗口（左目录 / 右正文）。
 * 每篇包含：什么时候用 → 步骤 → 公式 → 小例子，配 SVG 示意图。
 */
const SVG_HEAD = 'viewBox="0 0 360 150" style="width:100%;max-width:420px;display:block;margin:6px 0 10px"';

function box(x, y, w, h, label, color = '#4f9cf9') {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" fill="#121822" stroke="${color}"/>` +
    `<text x="${x + w / 2}" y="${y + h / 2 + 4}" fill="${color}" font-size="11" text-anchor="middle">${label}</text>`;
}

function wire(x1, y1, x2, y2, color = '#7d8899') {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="1.5"/>`;
}

function dot(x, y, color = '#7d8899') {
  return `<circle cx="${x}" cy="${y}" r="2.6" fill="${color}"/>`;
}

function arrow(x1, y1, x2, y2, color = '#f9a04f') {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="1.6" marker-end="url(#ah)"/>`;
}

const DEFS = `<defs><marker id="ah" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
  <path d="M0,0 L6,3 L0,6 z" fill="#f9a04f"/></marker></defs>`;

// ---------------------------------------------------------------- 文章
export const DOCS = [
  {
    id: 'dc',
    title: '① 直流电路基础',
    when: '只有电阻和直流电源时，一切从这两条定律出发。',
    body: `
      <h4>基尔霍夫定律</h4>
      <p><b>KCL（电流）</b>：任意节点，流入电流 = 流出电流。</p>
      <p><b>KVL（电压）</b>：任意回路，各段电压代数和 = 0。</p>
      <div class="tex" data-tex="\\sum I_{\\text{出}} = 0,\\qquad \\sum U_{\\text{回路}} = 0"></div>
      <h4>欧姆定律与串并联</h4>
      <div class="tex" data-tex="U=IR,\\quad R_{\\text{串}}=R_1+R_2,\\quad \\frac{1}{R_{\\text{并}}}=\\frac{1}{R_1}+\\frac{1}{R_2}"></div>
      <svg ${SVG_HEAD}>${DEFS}
        ${box(30, 60, 60, 30, 'R₁')}${box(120, 60, 60, 30, 'R₂')}
        ${wire(90, 75, 120, 75)}${wire(30, 75, 10, 75)}${wire(180, 75, 200, 75)}
        <text x="105" y="115" fill="#8894a8" font-size="10">串联：首尾相接，电流相同</text>
        ${box(230, 40, 60, 30, 'R₁', '#f9a04f')}${box(230, 90, 60, 30, 'R₂', '#f9a04f')}
        ${wire(220, 40, 220, 105)}${wire(260, 40, 260, 55)}${wire(260, 90, 260, 105)}
        <text x="215" y="135" fill="#8894a8" font-size="10">并联：两端同节点，电压相同</text>
      </svg>
      <h4>小例子</h4>
      <p>10 V 电源接 5 Ω 与 5 Ω 串联：总电阻 10 Ω → I = 1 A → 每个电阻上 5 V。</p>`,
  },
  {
    id: 'nodal',
    title: '② 节点电压法',
    when: '岔路多、回路少时最省事：只设节点电压当未知量。',
    steps: [
      '选一个节点当参考点（电位记 0，通常接地）。',
      '其余每个节点设一个未知电压 V₁、V₂…',
      '对每个独立节点写 KCL：把每条支路电流用 (V本 − V邻)/R 表示。',
      '解线性方程组（方程个数 = 独立节点数）。',
      '回代求各支路电流：I = (V本 − V邻)/R。',
    ],
    body: `
      <h4>核心公式</h4>
      <div class="tex" data-tex="\\sum_{\\text{接在该节点的支路}} \\frac{V_{\\text{本}}-V_{\\text{邻}}}{R} + \\sum I_{\\text{源}} = 0"></div>
      <h4>小例子（2 节点）</h4>
      <p>V₁=10 V 经 R₁=5 Ω 到 n₂，n₂ 再经 R₂=5 Ω 到地：</p>
      <div class="tex" data-tex="\\frac{V_2-10}{5}+\\frac{V_2-0}{5}=0\\ \\Rightarrow\\ V_2=5\\ \\text{V}"></div>
      <p>再由欧姆定律回代：I₁=(10−5)/5=1 A，I₂=5/5=1 A。</p>
      <h4>注意</h4>
      <p>① 含电压源的支路电流不好直接写，先设成未知电流 I，再把"电压源电压固定"当附加方程；
      ② 含电流源的项直接移到等号右边。</p>`,
  },
  {
    id: 'super',
    title: '③ 叠加定理',
    when: '电路里有 2 个以上独立源，且全是线性元件。',
    steps: [
      '只保留一个独立源，其余置零：电压源短路、电流源开路。',
      '解这一次电路，得到待求量的分量。',
      '每个源各做一次。',
      '把所有分量代数相加（注意正负号）。',
    ],
    body: `
      <h4>为什么可以这样做</h4>
      <p>线性电路中，响应与激励成正比（齐次性），且多个激励的总响应等于各自响应之和（可加性）。</p>
      <div class="tex" data-tex="u = u^{(1)} + u^{(2)} + \\cdots"></div>
      <h4>不能用的场合</h4>
      <p><b>功率不能叠加</b>！P = I²R 是二次函数；也<b>不能用于含受控源</b>的电路直接置零（受控源要保留）。</p>
      <div class="tex" data-tex="P \\ne P^{(1)}+P^{(2)},\\qquad P=\\frac{U_{\\text{总}}^2}{R}"></div>`,
  },
  {
    id: 'thevenin',
    title: '④ 戴维南等效 / 诺顿等效',
    when: '只关心某个元件（或某两个端子）上的电压电流时，把其余部分打包成一个电源。',
    steps: [
      '把待求元件从端口断开。',
      '求端口开路电压 U_oc（这一步很多题就是待求量）。',
      '把所有独立源置零，求端口看进去的等效电阻 R_th。',
      '用 U_oc 与 R_th 的串联（戴维南）或等值的电流源并联（诺顿）替换原网络。',
    ],
    body: `
      <div class="tex" data-tex="R_{th}=\\frac{U_{oc}}{I_{sc}},\\qquad I_N=\\frac{U_{oc}}{R_{th}}"></div>
      <svg ${SVG_HEAD}>${DEFS}
        ${box(20, 45, 90, 60, '线性\n含源网络')}
        ${wire(110, 60, 170, 60)}${wire(110, 95, 170, 95)}
        ${dot(170, 60)}${dot(170, 95)}
        <text x="130" y="52" fill="#4f9cf9" font-size="10">U_oc</text>
        <path d="M195,60 L225,60" stroke="#7d8899"/>${arrow(215, 60, 225, 60)}
        ${box(230, 45, 60, 25, 'U_oc', '#7ee787')}${box(230, 78, 60, 25, 'R_th', '#7ee787')}
        ${wire(260, 70, 260, 78)}${wire(290, 58, 320, 58)}${wire(290, 90, 320, 90)}
        <text x="18" y="130" fill="#8894a8" font-size="10">原网络 → 一个电压源串联一个电阻</text>
      </svg>
      <h4>小例子</h4>
      <p>10 V 电源 与 5 Ω、5 Ω 串联，从第二个电阻两端看：</p>
      <p>断开负载 → U_oc = 5 V；电源短路 → R_th = 5∥5 = 2.5 Ω。</p>`,
  },
  {
    id: 'maxp',
    title: '⑤ 最大功率传输',
    when: '问"负载取多大时功率最大"。',
    body: `
      <p>把电源侧等效成 U_oc 串联 R_th，负载 R_L 上的功率：</p>
      <div class="tex" data-tex="P_L=\\frac{U_{oc}^2 R_L}{(R_{th}+R_L)^2}"></div>
      <p>对 R_L 求导令零 → <b>R_L = R_th</b> 时最大：</p>
      <div class="tex" data-tex="P_{\\max}=\\frac{U_{oc}^2}{4R_{th}}"></div>
      <svg ${SVG_HEAD}>${DEFS}
        <polyline points="40,20 40,120 120,120" fill="none" stroke="#4f9cf9" stroke-width="1.6"/>
        <circle cx="52" cy="60" r="2.6" fill="#7ee787"/>
        <text x="60" y="45" fill="#7ee787" font-size="10">峰值在 R_L = R_th</text>
        <text x="40" y="136" fill="#8894a8" font-size="9">R_L</text>
        <text x="6" y="30" fill="#8894a8" font-size="9">P_L</text>
      </svg>
      <p><b>注意</b>：最大功率时效率只有 50%（一半功率消耗在内阻上），电力系统追求效率、不追求这个。</p>`,
  },
  {
    id: 'ac',
    title: '⑥ 正弦交流与相量法',
    when: '电源是正弦、电路已进入稳态（暂态已结束）。',
    body: `
      <h4>三要素与相量</h4>
      <p>正弦量用<b>有效值、频率、初相</b>三个量描述。同频率下相位差固定，可用<b>相量</b>（复数）代替三角函数运算。</p>
      <div class="tex" data-tex="u(t)=U_m\\cos(\\omega t+\\varphi)\\ \\Longleftrightarrow\\ \\dot U=U\\angle\\varphi,\\quad U=\\frac{U_m}{\\sqrt2}"></div>
      <h4>元件阻抗</h4>
      <div class="tex" data-tex="Z_R=R,\\qquad Z_L=j\\omega L,\\qquad Z_C=\\frac{1}{j\\omega C}=-j\\frac{1}{\\omega C}"></div>
      <svg ${SVG_HEAD}>${DEFS}
        <line x1="60" y1="75" x2="320" y2="75" stroke="#3a4453"/>
        <line x1="190" y1="10" x2="190" y2="140" stroke="#3a4453"/>
        ${arrow(190, 75, 300, 75, '#4f9cf9')}<text x="304" y="72" fill="#4f9cf9" font-size="10">I</text>
        ${arrow(190, 75, 235, 30, '#f9a04f')}<text x="238" y="28" fill="#f9a04f" font-size="10">U_R</text>
        ${arrow(190, 75, 190, 20, '#7ee787')}<text x="196" y="18" fill="#7ee787" font-size="10">U_L</text>
        <text x="14" y="130" fill="#8894a8" font-size="10">电感电压超前电流 90°，可画成直角三角形</text>
      </svg>
      <h4>功率</h4>
      <div class="tex" data-tex="P=UI\\cos\\varphi,\\quad Q=UI\\sin\\varphi,\\quad S=UI\\ (\\cos\\varphi=\\text{功率因数})"></div>
      <p>电感、电容只交换能量不做功（无功 Q）；电阻才真正消耗（有功 P）。</p>`,
  },
  {
    id: 'resonance',
    title: '⑦ 谐振',
    when: 'L 与 C 同时存在，问"什么频率下电流最大 / 电压最大"。',
    body: `
      <p><b>串联谐振</b>（L、C 与 R 串联）：ωL = 1/(ωC) 时，L 与 C 的电压互相抵消，阻抗最小 = R，电流最大。</p>
      <div class="tex" data-tex="f_0=\\frac{1}{2\\pi\\sqrt{LC}},\\qquad Q=\\frac{\\omega_0 L}{R}=\\frac{1}{\\omega_0 C R}"></div>
      <p>谐振时 U_L = U_C = <b>Q·U</b>（可能远大于电源电压，所以叫"电压谐振"，要注意过压）。</p>
      <p><b>并联谐振</b>：支路电流互相抵消，总电流最小，叫"电流谐振"。</p>
      <h4>小例子</h4>
      <p>L=1 mH、C=1 µF → f₀ = 1/(2π√(10⁻³·10⁻⁶)) ≈ 5033 Hz。用「曲线」栏的<b>扫频</b>就能看到峰。</p>`,
  },
  {
    id: 'three',
    title: '⑧ 三相电路',
    when: '工业用电：三相对称电源 + 三相负载。',
    body: `
      <p>三相电源：幅值相同、相位互差 120°。</p>
      <div class="tex" data-tex="\\dot U_U=U\\angle0^\\circ,\\ \\dot U_V=U\\angle-120^\\circ,\\ \\dot U_W=U\\angle+120^\\circ"></div>
      <h4>线量 / 相量关系</h4>
      <div class="tex" data-tex="\\text{Y 接：}U_L=\\sqrt3 U_P,\\ I_L=I_P\\qquad \\text{Δ 接：}U_L=U_P,\\ I_L=\\sqrt3 I_P"></div>
      <svg ${SVG_HEAD}>${DEFS}
        <circle cx="180" cy="75" r="52" fill="none" stroke="#2c3444" stroke-dasharray="3 3"/>
        ${arrow(180, 75, 232, 75, '#4f9cf9')}
        ${arrow(180, 75, 154, 30, '#f9a04f')}
        ${arrow(180, 75, 154, 120, '#7ee787')}
        <text x="236" y="72" fill="#4f9cf9" font-size="10">U</text>
        <text x="140" y="26" fill="#f9a04f" font-size="10">V</text>
        <text x="140" y="126" fill="#7ee787" font-size="10">W</text>
        <text x="96" y="146" fill="#8894a8" font-size="10">对称三相相量：互差 120°，相量和为 0</text>
      </svg>
      <h4>功率与两表法</h4>
      <p>对称负载：P = √3 U_L I_L cosφ。三相三线制可用<b>两表法</b>：P = P₁ + P₂，其中</p>
      <div class="tex" data-tex="P_1=\\mathrm{Re}[\\dot U_{UV}\\dot I_U^*],\\qquad P_2=\\mathrm{Re}[\\dot U_{WV}\\dot I_W^*]"></div>`,
  },
  {
    id: 'tran',
    title: '⑨ 一阶暂态：三要素法',
    when: '含 1 个电容或电感，开关在 t=0 换路。',
    steps: [
      '求初值 f(0⁺)：电容电压 u_C、电感电流 i_L 不跃变，用换路前的稳态值。',
      '求稳态 f(∞)：换路后重新稳态——电容开路、电感短路。',
      '求时间常数 τ：把电源置零，求动态元件两端的等效电阻 R，τ = RC 或 L/R。',
      '套公式。',
    ],
    body: `
      <div class="tex" data-tex="f(t)=f(\\infty)+\\left[f(0^+)-f(\\infty)\\right]e^{-t/\\tau}"></div>
      <svg ${SVG_HEAD}>${DEFS}
        <line x1="40" y1="120" x2="330" y2="120" stroke="#3a4453"/><line x1="40" y1="15" x2="40" y2="120" stroke="#3a4453"/>
        <path d="M40,20 C90,20 120,95 320,112" fill="none" stroke="#4f9cf9" stroke-width="1.8"/>
        <line x1="40" y1="112" x2="320" y2="112" stroke="#2c3444" stroke-dasharray="3 3"/>
        <line x1="40" y1="20" x2="320" y2="20" stroke="#2c3444" stroke-dasharray="3 3"/>
        <circle cx="40" cy="20" r="2.6" fill="#f9a04f"/><text x="20" y="18" fill="#f9a04f" font-size="10">f(0⁺)</text>
        <text x="6" y="116" fill="#7ee787" font-size="10">f(∞)</text>
        <text x="150" y="138" fill="#8894a8" font-size="10">按指数规律过渡，τ 内走完 63.2%，3τ~5τ 基本结束</text>
      </svg>
      <h4>小例子</h4>
      <p>10 V 经 1 kΩ 给 1 µF 充电：τ = RC = 1 ms，u_C(t)=10(1−e^(−t/0.001)) V。
      t=1 ms 时约 6.32 V（正好 63.2%）。用「曲线」栏的<b>波形</b>可以直接看到这条曲线。</p>`,
  },
  {
    id: 'diode',
    title: '⑩ 二极管与稳压管',
    when: '判断二极管通断、算输出电压。',
    steps: [
      '先假设二极管截止，算出它两端电压。',
      '若正偏电压 > 导通压降（硅 0.7 V）→ 假设不成立，改成导通（电压源 0.7 V）重算。',
      '截止时视为开路，导通时视为恒压源（理想二极管 0 V）。',
    ],
    body: `
      <svg ${SVG_HEAD}>${DEFS}
        <text x="20" y="30" fill="#8894a8" font-size="10">导通（正偏）</text>
        ${arrow(30, 55, 90, 55, '#7ee787')}
        <path d="M95,42 L95,68 L115,55 z" fill="#121822" stroke="#7ee787"/>
        <line x1="115" y1="42" x2="115" y2="68" stroke="#7ee787"/>
        <text x="30" y="90" fill="#8894a8" font-size="10">截止（反偏）</text>
        <path d="M95,97 L95,123 L115,110 z" fill="none" stroke="#7d8899"/>
        <line x1="115" y1="97" x2="115" y2="123" stroke="#7d8899"/>
        <text x="200" y="30" fill="#8894a8" font-size="10">稳压管反向击穿</text>
        <path d="M210,55 L250,55" stroke="#f9a04f"/>
        <text x="200" y="80" fill="#f9a04f" font-size="10">U = Vz（如 5.1 V）保持稳定</text>
      </svg>
      <p><b>稳压管</b>接反了用：正常反向击穿区，端电压约等于 V_Z 且几乎不变，所以能稳压。
      串联限流电阻 R = (U_in − V_Z)/I，I 要小于最大允许电流。</p>
      <div class="tex" data-tex="R=\\frac{U_{\\text{in}}-V_Z}{I_Z+I_L}"></div>`,
  },
  {
    id: 'bjt',
    title: '⑪ 三极管与微变等效',
    when: '求静态工作点，再求放大倍数。',
    steps: [
      '直流：电容开路，用 V_BE≈0.7 V、I_C=βI_B 求 I_B、I_C、U_CE（判断是否在放大区）。',
      '交流：把三极管换成 π 模型（r_be 电阻 + g_m·V_be 受控电流源），直流电源置零。',
      '在等效电路上解 u_o/u_i 得放大倍数。',
    ],
    body: `
      <div class="tex" data-tex="r_{be}=r_{bb'}+(1+\\beta)\\frac{26\\,\\text{mV}}{I_E},\\qquad g_m=\\frac{\\beta}{r_{be}}"></div>
      <svg ${SVG_HEAD}>${DEFS}
        <text x="16" y="20" fill="#8894a8" font-size="10">π 模型</text>
        <line x1="60" y1="40" x2="60" y2="120" stroke="#7d8899"/>
        <line x1="60" y1="40" x2="120" y2="40" stroke="#7d8899"/>
        ${box(120, 30, 40, 20, 'r_be', '#7ee787')}
        <line x1="160" y1="40" x2="210" y2="40" stroke="#7d8899"/>
        <line x1="210" y1="40" x2="210" y2="120" stroke="#7d8899"/>
        <line x1="140" y1="40" x2="140" y2="100" stroke="#7d8899"/>
        ${arrow(140, 100, 200, 100, '#f9a04f')}
        <text x="150" y="94" fill="#f9a04f" font-size="10">g_m·U_be</text>
        <text x="20" y="135" fill="#8894a8" font-size="10">共射放大：A_u ≈ −βR_c/r_be（负号表示反相）</text>
      </svg>
      <h4>共射电压放大倍数</h4>
      <div class="tex" data-tex="A_u=-\\frac{\\beta R_c'}{r_{be}},\\qquad r_i\\approx r_{be},\\qquad r_o\\approx R_c"></div>
    `,
  },
  {
    id: 'opamp',
    title: '⑫ 集成运放（理想）',
    when: '运放工作在线性区（有负反馈）。',
    body: `
      <h4>两条金律</h4>
      <p>① <b>虚短</b>：u₊ = u₋（开环增益无穷大，两点电位相等）。</p>
      <p>② <b>虚断</b>：两个输入端电流为 0（输入电阻无穷大）。</p>
      <div class="tex" data-tex="u_+=u_-,\\qquad i_+=i_-=0"></div>
      <h4>常用电路结论</h4>
      <p>反相放大：u_o = −(R_f/R₁)·u_i；同相放大：u_o = (1+R_f/R₁)·u_i。</p>
      <div class="tex" data-tex="A_u=-\\frac{R_f}{R_1}\\ (\\text{反相}),\\qquad A_u=1+\\frac{R_f}{R_1}\\ (\\text{同相})"></div>
      <p><b>注意</b>：虚短只在负反馈时成立。开环或正反馈时运放饱和，u_o 等于 ±U_om。</p>`,
  },
];

// ---------------------------------------------------------------- 渲染
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export function renderLearn(container, activeId) {
  if (!container) return;
  const cur = DOCS.find((d) => d.id === activeId) || DOCS[0];
  const nav = DOCS.map((d) =>
    `<button class="learn-nav${d.id === cur.id ? ' active' : ''}" data-learn="${d.id}">${esc(d.title)}</button>`).join('');
  const steps = (cur.steps && cur.steps.length)
    ? `<h4>步骤</h4><ol class="learn-steps">${cur.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>` : '';
  container.innerHTML = `
    <div class="learn-wrap">
      <nav class="learn-side">${nav}</nav>
      <article class="learn-body">
        <h3>${esc(cur.title)}</h3>
        ${cur.when ? `<p class="learn-when">什么时候用：${esc(cur.when)}</p>` : ''}
        ${steps}
        ${cur.body}
      </article>
    </div>`;
  return container;
}
