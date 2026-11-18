'use strict';
/* 의존성 없는 SVG 차트 + 마스코트 '모모' */
const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null && v !== false) node.setAttribute(k, String(v));
  for (const c of children.flat()) if (c != null && c !== false) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

function shortWon(n) {
  if (n >= 1e8) return `${(n / 1e8).toFixed(1).replace(/\.0$/, '')}억`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(n >= 1e5 ? 0 : 1).replace(/\.0$/, '')}만`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1).replace(/\.0$/, '')}천`;
  return String(Math.round(n));
}

/* 도넛 차트: segments [{value, color, label}] */
function donutChart(segments, { size = 180, thickness = 26, title = '', subtitle = '' } = {}) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const label = total > 0 ? segments.map((s) => `${s.label} ${Math.round((s.value / total) * 100)}%`).join(', ') : '지출 기록 없음';
  const root = svgEl('svg', { viewBox: `0 0 ${size} ${size}`, class: 'donut', role: 'img', 'aria-label': `카테고리별 지출: ${label}` });
  root.append(svgEl('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--track)', 'stroke-width': thickness }));
  let offset = 0;
  if (total > 0) {
    for (const s of segments) {
      if (!s.value) continue;
      const len = (s.value / total) * c;
      const gap = segments.length > 1 ? Math.min(2, len / 3) : 0;
      root.append(svgEl('circle', {
        cx: size / 2, cy: size / 2, r, fill: 'none', stroke: s.color, 'stroke-width': thickness,
        'stroke-dasharray': `${Math.max(0, len - gap)} ${c}`, 'stroke-dashoffset': -offset,
        transform: `rotate(-90 ${size / 2} ${size / 2})`, 'stroke-linecap': 'butt',
      }));
      offset += len;
    }
  }
  root.append(svgEl('text', { x: size / 2, y: size / 2 - 4, 'text-anchor': 'middle', class: 'donut-title' }, title));
  root.append(svgEl('text', { x: size / 2, y: size / 2 + 16, 'text-anchor': 'middle', class: 'donut-sub' }, subtitle));
  return root;
}

/* 막대 차트: bars [{label, value, muted, highlight}] */
function barChart(bars, { height = 150, avg = null, labelEvery = 1, ariaLabel = '' } = {}) {
  const w = 320; const top = 14; const bottom = 22;
  const max = Math.max(1, ...bars.map((b) => b.value), avg || 0);
  const slot = w / bars.length;
  const bw = Math.max(3, Math.min(26, slot * 0.62));
  const ih = height - top - bottom;
  const root = svgEl('svg', { viewBox: `0 0 ${w} ${height}`, class: 'bars', role: 'img', 'aria-label': ariaLabel });
  root.append(svgEl('line', { x1: 0, x2: w, y1: top + ih, y2: top + ih, class: 'axis' }));
  bars.forEach((b, i) => {
    const h = b.value > 0 ? Math.max(2, (b.value / max) * ih) : 0;
    const x = i * slot + (slot - bw) / 2;
    const cls = b.highlight ? 'bar hi' : b.muted ? 'bar muted' : 'bar';
    if (h) {
      const rect = svgEl('rect', { x, y: top + ih - h, width: bw, height: h, rx: Math.min(6, bw / 2), class: cls });
      rect.append(svgEl('title', {}, `${b.label}: ${formatWon(b.value)}`));
      root.append(rect);
    }
    if (b.showValue && b.value > 0) root.append(svgEl('text', { x: x + bw / 2, y: top + ih - h - 4, 'text-anchor': 'middle', class: 'bar-val' }, shortWon(b.value)));
    if (i % labelEvery === 0 || i === bars.length - 1) {
      root.append(svgEl('text', { x: x + bw / 2, y: height - 6, 'text-anchor': 'middle', class: 'bar-label' }, b.label));
    }
  });
  if (avg) {
    const y = top + ih - (avg / max) * ih;
    root.append(svgEl('line', { x1: 0, x2: w, y1: y, y2: y, class: 'avg-line' }));
    root.append(svgEl('text', { x: w - 2, y: y - 4, 'text-anchor': 'end', class: 'avg-label' }, `평균 ${shortWon(avg)}`));
  }
  return root;
}

/* 마스코트 모모: 말랑한 찹쌀떡 토끼. stage 0~3, item: 착용 아이템 id, mood: happy|worry|sleep */
function mascotSvg({ stage = 0, item = null, mood = 'happy', size = 120 } = {}) {
  const s = [0.82, 0.9, 0.96, 1][stage] || 1;
  const root = svgEl('svg', { viewBox: '0 0 120 120', width: size, height: size, class: 'mascot', 'aria-hidden': 'true' });
  const g = svgEl('g', { transform: `translate(60 66) scale(${s}) translate(-60 -66)` });
  // 그림자
  root.append(svgEl('ellipse', { cx: 60, cy: 108, rx: 30 * s, ry: 5, fill: 'rgba(120,90,120,.12)' }));
  // 귀
  g.append(svgEl('ellipse', { cx: 44, cy: 26, rx: 8, ry: 17, fill: '#FFE9EF', stroke: '#E9B9C8', 'stroke-width': 2, transform: 'rotate(-12 44 26)' }));
  g.append(svgEl('ellipse', { cx: 76, cy: 26, rx: 8, ry: 17, fill: '#FFE9EF', stroke: '#E9B9C8', 'stroke-width': 2, transform: 'rotate(12 76 26)' }));
  g.append(svgEl('ellipse', { cx: 44, cy: 28, rx: 3.5, ry: 10, fill: '#F7C6D3', transform: 'rotate(-12 44 28)' }));
  g.append(svgEl('ellipse', { cx: 76, cy: 28, rx: 3.5, ry: 10, fill: '#F7C6D3', transform: 'rotate(12 76 28)' }));
  // 몸
  g.append(svgEl('path', { d: 'M20 78c0-24 18-40 40-40s40 16 40 40c0 18-14 26-40 26S20 96 20 78z', fill: '#FFF6F2', stroke: '#E9B9C8', 'stroke-width': 2.2 }));
  // 동전 무늬 (저금 토끼)
  g.append(svgEl('rect', { x: 52, y: 41, width: 16, height: 3.2, rx: 1.6, fill: '#E9B9C8' }));
  // 볼
  g.append(svgEl('ellipse', { cx: 38, cy: 78, rx: 7, ry: 4.5, fill: '#F9C9D6' }));
  g.append(svgEl('ellipse', { cx: 82, cy: 78, rx: 7, ry: 4.5, fill: '#F9C9D6' }));
  // 눈
  if (mood === 'sleep') {
    g.append(svgEl('path', { d: 'M42 70q5 4 10 0M68 70q5 4 10 0', fill: 'none', stroke: '#5B4660', 'stroke-width': 2.4, 'stroke-linecap': 'round' }));
  } else {
    g.append(svgEl('ellipse', { cx: 47, cy: 69, rx: 3.6, ry: 4.4, fill: '#5B4660' }));
    g.append(svgEl('ellipse', { cx: 73, cy: 69, rx: 3.6, ry: 4.4, fill: '#5B4660' }));
    g.append(svgEl('circle', { cx: 48.3, cy: 67.4, r: 1.3, fill: '#fff' }));
    g.append(svgEl('circle', { cx: 74.3, cy: 67.4, r: 1.3, fill: '#fff' }));
  }
  // 입
  g.append(svgEl('path', {
    d: mood === 'worry' ? 'M54 82q6-4 12 0' : 'M54 79q3 4 6 0q3 4 6 0',
    fill: 'none', stroke: '#5B4660', 'stroke-width': 2, 'stroke-linecap': 'round',
  }));
  // 단계별 장식
  if (stage === 0) g.append(svgEl('path', { d: 'M60 38c0-7 5-11 11-11-1 7-5 11-11 11zM60 38c0-6-4-9-9-9 1 6 4 9 9 9z', fill: '#A8D8B9' }));
  if (stage >= 2) {
    g.append(svgEl('path', { d: 'M101 44l2 5 5 2-5 2-2 5-2-5-5-2 5-2z', fill: '#F5D08A' }));
    g.append(svgEl('path', { d: 'M17 52l1.5 3.5 3.5 1.5-3.5 1.5-1.5 3.5-1.5-3.5-3.5-1.5 3.5-1.5z', fill: '#C9A7EB' }));
  }
  if (stage >= 3) g.append(svgEl('path', { d: 'M34 98q26 10 52 0', fill: 'none', stroke: '#C9A7EB', 'stroke-width': 3, 'stroke-linecap': 'round' }));
  // 아이템
  const items = {
    ribbon: () => svgEl('g', {}, svgEl('path', { d: 'M78 14l-10-6v12zM78 14l10-6v12z', fill: '#F48FB1' }), svgEl('circle', { cx: 78, cy: 14, r: 3, fill: '#EC6F9A' })),
    glasses: () => svgEl('g', { fill: 'none', stroke: '#7A6380', 'stroke-width': 1.8 }, svgEl('circle', { cx: 47, cy: 69, r: 8 }), svgEl('circle', { cx: 73, cy: 69, r: 8 }), svgEl('path', { d: 'M55 69h10' })),
    flower: () => svgEl('g', {}, ...[0, 72, 144, 216, 288].map((a) => svgEl('ellipse', { cx: 36, cy: 44, rx: 3, ry: 5.5, fill: '#C9A7EB', transform: `rotate(${a} 36 49)` })), svgEl('circle', { cx: 36, cy: 49, r: 2.6, fill: '#F5D08A' })),
    scarf: () => svgEl('g', {}, svgEl('path', { d: 'M30 90q30 12 60 0l-2 7q-28 10-56 0z', fill: '#F7A8BE' }), svgEl('path', { d: 'M78 95l4 12 7-3-5-11z', fill: '#F48FB1' })),
    crown: () => svgEl('path', { d: 'M46 34l4-12 6 8 4-11 4 11 6-8 4 12z', fill: '#F5D08A', stroke: '#E0B25C', 'stroke-width': 1.2 }),
  };
  if (item && items[item]) g.append(items[item]());
  root.append(g);
  return root;
}

if (typeof module !== 'undefined') module.exports = { shortWon };
