/**
 * Energy dashboard — matches test2.vue VueFlow layout.
 * Dynamic flow animation: direction/speed/color based on power data.
 * Simulated data when no hardware, real API when available.
 */

// ---- Clock ----
function updateDashClock() {
  const now = new Date();
  const el = document.getElementById('dashClock');
  const el2 = document.getElementById('dashDate');
  if (el) el.textContent = now.toLocaleTimeString('zh-CN', {hour12:false, hour:'2-digit', minute:'2-digit', second:'2-digit'});
  if (el2) el2.textContent = now.toLocaleDateString('zh-CN', {year:'numeric',month:'long',day:'numeric',weekday:'long'});
}

// ---- Helpers ----
function getVal(d, k) { return (d && d.data && d.data[k]) ? d.data[k].value : null; }
function fmt(v, d) { return (v === null || v === undefined) ? '--' : Number(v).toFixed(d === undefined ? 1 : d); }
function setText(id, t) { const e = document.getElementById(id); if (e) e.textContent = t; }

// ---- Simulated data (matches test2.vue mock, updates dynamically) ----
const sim = {
  grid: { power: 47.8 }, solar: { voltage: 720.5, current: 92.3, power: 66.4 },
  storage: { voltage: 51.8, current: -158.2, power: -25.6, soc: 82 },
  charging: { power: 93.4 }, office: { power: 30.0 },
};
function rnd() { return Math.floor(Math.random() * 100); }
function updateSim() {
  sim.grid.power = +(47 + (rnd() - 50) * 0.1).toFixed(1);
  sim.solar.power = +(60 + rnd() * 0.3).toFixed(1);
  sim.solar.current = +(85 + rnd() * 0.2).toFixed(1);
  sim.storage.soc = Math.max(0, Math.min(100, sim.storage.soc + (rnd() - 50) * 0.02));
  sim.storage.power = +(sim.storage.soc > 50 ? -25 + (rnd()-50)*0.2 : 25 + (rnd()-50)*0.2).toFixed(1);
  sim.charging.power = +(90 + rnd() * 0.05).toFixed(1);
  const h = new Date().getHours();
  sim.office.power = +((h >= 9 && h <= 18) ? 25 + rnd()*0.1 : 8 + rnd()*0.05).toFixed(1);
}

// ---- Flow edge class based on power value ----
function edgeClass(baseCls, power) {
  if (power === null || power === undefined) return baseCls + ' dashed idle';
  const abs = Math.abs(power);
  if (abs < 0.1) return baseCls + ' dashed idle';
  let cls = baseCls + ' animated';
  if (power < 0) cls += ' reverse';
  if (abs > 50) cls += ' fast';
  else if (abs < 5) cls += ' slow';
  return cls;
}

// ---- SVG Flow Diagram — strict left-right symmetric ----
let flowPower = { grid:0, pv1:0, pv2:0, storage:0, dc:0, ac:0, office:0 };

function renderFlowDiagram() {
  const wrap = document.getElementById('flowDiagram');
  if (!wrap) return;
  const W = wrap.clientWidth || 800;
  const H = wrap.clientHeight || 500;
  const CX = W / 2; // exact center axis

  // Symmetric spacing from center
  const topY = H * 0.16;       // top row y
  const midY = H * 0.46;       // center box y
  const botY = H * 0.80;       // bottom row y
  const d1 = W * 0.30;         // outer nodes offset (电网, 储能)
  const d2 = W * 0.12;         // inner nodes offset (光伏1, 光伏2)
  const d3 = W * 0.26;         // bottom outer offset (直流桩, 办公室)
  const R = 42;                 // top node radius
  const RB = 48;                // bottom node radius
  const rectHW = 62, rectHH = 26; // center rect half-size

  // Strictly symmetric node positions
  const N = {
    grid:    { x:CX-d1, y:topY, icon:'⚡', name:'电网',      bc:'#ff6b6b', lc:'#ff8c00', r:R },
    pv1:     { x:CX-d2, y:topY, icon:'☀️', name:'光伏1',     bc:'#ff9500', lc:'#ff9500', r:R },
    pv2:     { x:CX+d2, y:topY, icon:'☀️', name:'光伏2',     bc:'#ff9500', lc:'#ff9500', r:R },
    storage: { x:CX+d1, y:topY, icon:'🔋', name:'储能',      bc:'#00ffff', lc:'#00ffff', r:R },
    center:  { x:CX,    y:midY, name:'光储系统', bc:'#3b82f6', isRect:true },
    dc:      { x:CX-d3, y:botY, icon:'🚗', name:'直流充电桩', bc:'#ff9500', lc:'#ff9500', r:RB },
    ac:      { x:CX,    y:botY, icon:'🚗', name:'交流充电桩', bc:'#ff9500', lc:'#ff9500', r:RB },
    office:  { x:CX+d3, y:botY, icon:'💻', name:'办公室',    bc:'#4ecdc4', lc:'#8899bb', r:RB },
  };

  // ---- Path builders (matching lizi screenshot exactly) ----

  // 电网/储能: 底部垂直下到光储系统同高 → 水平转弯接光储系统左/右侧（一个直角弯）
  function sideToCenter(node, side) {
    const x = node.x, y1 = node.y + R;
    const targetX = side === 'left' ? CX - rectHW : CX + rectHW;
    return `M${x},${y1} L${x},${midY} L${targetX},${midY}`;
  }

  // 光伏1/2: 底部垂直下 → 汇合到CX竖线 → 下到光储系统顶部
  function pvToCenter(node) {
    const x = node.x, y1 = node.y + R, y2 = midY - rectHH;
    // 先垂直下到汇合高度，再水平到CX，再垂直下到光储系统顶部
    const junctY = y1 + (y2 - y1) * 0.35;
    if (Math.abs(x - CX) < 3) return `M${x},${y1} L${x},${y2}`;
    return `M${x},${y1} L${x},${junctY} L${CX},${junctY} L${CX},${y2}`;
  }

  // 下方节点: 光储系统底部 → 垂直下到分叉高度 → 水平到节点x → 垂直下到节点顶部
  function centerToBot(node) {
    const x = node.x, y1 = midY + rectHH, y2 = node.y - node.r;
    const junctY = y1 + (y2 - y1) * 0.4;
    if (Math.abs(x - CX) < 3) return `M${CX},${y1} L${x},${y2}`;
    return `M${CX},${y1} L${CX},${junctY} L${x},${junctY} L${x},${y2}`;
  }

  const edges = [
    { id:'eGrid', path: sideToCenter(N.grid, 'left'),    type:'grid-line', pk:'grid' },
    { id:'ePv1',  path: pvToCenter(N.pv1),                type:'solar',     pk:'pv1' },
    { id:'ePv2',  path: pvToCenter(N.pv2),                type:'solar',     pk:'pv2' },
    { id:'eStor', path: sideToCenter(N.storage, 'right'), type:'storage',   pk:'storage' },
    { id:'eDc',   path: centerToBot(N.dc),                type:'charge',    pk:'dc' },
    { id:'eAc',   path: centerToBot(N.ac),                type:'charge',    pk:'ac' },
    { id:'eOff',  path: centerToBot(N.office),            type:'office-line',pk:'office' },
  ];

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">`;

  // Draw edges
  edges.forEach(e => {
    const isDashed = e.id === 'eGrid';
    const cls = isDashed
      ? edgeClass('flow-edge dashed ' + e.type, flowPower[e.pk])
      : edgeClass('flow-edge ' + e.type, flowPower[e.pk]);
    svg += `<path id="${e.id}" d="${e.path}" class="${cls}"/>`;
  });

  // Draw nodes
  Object.entries(N).forEach(([k, n]) => {
    svg += `<g class="flow-node-group" style="--node-color:${n.bc}">`;
    if (n.isRect) {
      svg += `<rect x="${n.x-rectHW}" y="${n.y-rectHH}" width="${rectHW*2}" height="${rectHH*2}" rx="5"
        fill="rgba(0,20,60,0.9)" stroke="${n.bc}" stroke-width="2" stroke-dasharray="5 3"/>`;
      svg += `<text x="${n.x}" y="${n.y+5}" text-anchor="middle" font-size="14" fill="#00d4ff" font-weight="bold">${n.name}</text>`;
    } else {
      svg += `<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="rgba(0,20,60,0.9)" stroke="${n.bc}" stroke-width="2"/>`;
      svg += `<text x="${n.x}" y="${n.y-6}" text-anchor="middle" font-size="26">${n.icon}</text>`;
      svg += `<text x="${n.x}" y="${n.y+18}" text-anchor="middle" font-size="12" fill="#fff" font-weight="bold">${n.name}</text>`;
    }
    svg += `</g>`;
  });

  // Power labels
  const lg = 16;
  svg += `<text id="fG1" x="${N.grid.x}" y="${N.grid.y+R+lg}" text-anchor="middle" font-size="11" fill="${N.grid.lc}" font-weight="bold"></text>`;
  svg += `<text id="fG2" x="${N.grid.x}" y="${N.grid.y+R+lg+14}" text-anchor="middle" font-size="11" fill="${N.grid.lc}" font-weight="bold"></text>`;
  svg += `<text id="fG3" x="${N.grid.x}" y="${N.grid.y+R+lg+28}" text-anchor="middle" font-size="11" fill="${N.grid.lc}" font-weight="bold"></text>`;
  svg += `<text id="fPv1" x="${N.pv1.x}" y="${N.pv1.y+R+lg}" text-anchor="middle" font-size="11" fill="${N.pv1.lc}" font-weight="bold"></text>`;
  svg += `<text id="fPv2" x="${N.pv2.x}" y="${N.pv2.y+R+lg}" text-anchor="middle" font-size="11" fill="${N.pv2.lc}" font-weight="bold"></text>`;
  svg += `<text id="fStor" x="${N.storage.x}" y="${N.storage.y+R+lg}" text-anchor="middle" font-size="11" fill="${N.storage.lc}" font-weight="bold"></text>`;
  svg += `<text id="fDc" x="${N.dc.x}" y="${N.dc.y-RB-10}" text-anchor="middle" font-size="12" fill="${N.dc.lc}" font-weight="bold"></text>`;
  svg += `<text id="fAc" x="${N.ac.x}" y="${N.ac.y-RB-10}" text-anchor="middle" font-size="12" fill="${N.ac.lc}" font-weight="bold"></text>`;
  svg += `<text id="fOff" x="${N.office.x}" y="${N.office.y-RB-10}" text-anchor="middle" font-size="12" fill="${N.office.lc}" font-weight="bold"></text>`;

  svg += '</svg>';
  wrap.innerHTML = svg;
}

// ---- Update edge animation dynamically (without re-rendering SVG) ----
function updateEdgeStyles() {
  const updates = [
    ['eGrid', edgeClass('flow-edge dashed grid-line', flowPower.grid)],
    ['ePv1',  edgeClass('flow-edge solar', flowPower.pv1)],
    ['ePv2',  edgeClass('flow-edge solar', flowPower.pv2)],
    ['eStor', edgeClass('flow-edge storage', flowPower.storage)],
    ['eDc',   edgeClass('flow-edge charge', flowPower.dc)],
    ['eAc',   edgeClass('flow-edge charge', flowPower.ac)],
    ['eOff',  edgeClass('flow-edge office-line', flowPower.office)],
  ];
  updates.forEach(([id, cls]) => {
    const el = document.getElementById(id);
    if (el) el.setAttribute('class', cls);
  });
}

// ---- Data polling & update ----
const meterAddrs = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11];
let allMeterData = {};
let hasRealData = false;

function updateFlowLabels() {
  const real = hasRealData;
  let gP, pv1P, pv2P, sP, sI, dcP, acP, oP;

  if (real) {
    gP  = getVal(allMeterData[1], 'power_total');
    pv1P = getVal(allMeterData[10], 'power');
    pv2P = getVal(allMeterData[11], 'power');
    sP  = getVal(allMeterData[5], 'power');
    sI  = getVal(allMeterData[5], 'current');
    dcP = (Math.abs(getVal(allMeterData[8],'power')||0) + Math.abs(getVal(allMeterData[9],'power')||0)) || null;
    acP = getVal(allMeterData[3], 'power_total');
    oP  = getVal(allMeterData[4], 'power_total');
  } else {
    updateSim();
    gP = sim.grid.power; pv1P = sim.solar.power; pv2P = sim.solar.power;
    sP = sim.storage.power; sI = sim.storage.power;
    dcP = sim.charging.power; acP = sim.charging.power; oP = sim.office.power;
  }

  // Update flow power for edge animation
  flowPower.grid = gP; flowPower.pv1 = pv1P; flowPower.pv2 = pv2P;
  flowPower.storage = sP; flowPower.dc = dcP; flowPower.ac = acP; flowPower.office = oP;
  updateEdgeStyles();

  // Labels — format matches test2.vue templates exactly
  const gI = real ? getVal(allMeterData[1],'current_a') : 10;
  setText('fG1', fmt(gP)+'V '+fmt(gI,0)+'A');
  setText('fG2', fmt(gP)+'V '+fmt(gI,0)+'A');
  setText('fG3', fmt(gP)+'V '+fmt(gI,0)+'A');

  const pv1I = real ? getVal(allMeterData[10],'current') : 10;
  const pv2I = real ? getVal(allMeterData[11],'current') : 10;
  setText('fPv1', fmt(pv1P,0)+'V '+fmt(pv1I,0)+'A');
  setText('fPv2', fmt(pv2P,0)+'V '+fmt(pv2I,0)+'A');

  setText('fStor', fmt(sP)+'V '+fmt(sI)+'A');

  setText('fDc',  fmt(dcP)+'kW');
  setText('fAc',  fmt(acP)+'kW');
  setText('fOff', fmt(oP)+'kW');

  // Right panel solar
  setText('solarPowerBig', fmt(Math.abs(pv1P||0)+Math.abs(pv2P||0)));
  // PV1 voltage/current
  const pv1VVal = real ? getVal(allMeterData[10],'voltage') : sim.solar.voltage;
  const pv1IVal = real ? Math.abs(getVal(allMeterData[10],'current')||0) : sim.solar.current;
  setText('pv1Voltage', fmt(pv1VVal)+'V');
  setText('pv1Current', fmt(pv1IVal)+'A');
  // PV2 voltage/current
  const pv2VVal = real ? getVal(allMeterData[11],'voltage') : sim.solar.voltage;
  const pv2IVal = real ? Math.abs(getVal(allMeterData[11],'current')||0) : sim.solar.current;
  setText('pv2Voltage', fmt(pv2VVal)+'V');
  setText('pv2Current', fmt(pv2IVal)+'A');

  updateEnergyCards(real, gP);
}

function updateEnergyCards(real, gP) {
  if (real) {
    const gF=getVal(allMeterData[1],'energy_forward_total'), gR=getVal(allMeterData[1],'energy_reverse_total');
    setText('gridMonthE',fmt(gF,1)); setText('gridYearE',fmt(gF,1)); setText('gridTotalE',fmt(gF?(gF+(gR||0)):null,1));
    const lF=getVal(allMeterData[4],'energy_forward_total');
    setText('loadMonthE',fmt(lF,1)); setText('loadYearE',fmt(lF,1)); setText('loadTotalE',fmt(lF,1));
    setText('officeMonthE',fmt(lF,1)); setText('officeYearE',fmt(lF,1)); setText('officeTotalE',fmt(lF,1));
    const d8=getVal(allMeterData[8],'energy_forward_total')||0, d9=getVal(allMeterData[9],'energy_forward_total')||0;
    setText('dcMonthE',fmt(d8+d9,1)); setText('dcYearE',fmt(d8+d9,1)); setText('dcTotalE',fmt(d8+d9,1));
    const aF=getVal(allMeterData[3],'energy_forward_total');
    setText('acMonthE',fmt(aF,1)); setText('acYearE',fmt(aF,1)); setText('acTotalE',fmt(aF,1));
    const p1=getVal(allMeterData[10],'energy_forward_total'), p2=getVal(allMeterData[11],'energy_forward_total');
    setText('pv1MonthE',fmt(p1,1)); setText('pv1YearE',fmt(p1,1)); setText('pv1TotalE',fmt(p1,1));
    setText('pv2MonthE',fmt(p2,1)); setText('pv2YearE',fmt(p2,1)); setText('pv2TotalE',fmt(p2,1));
    const bF=getVal(allMeterData[6],'energy_forward_total'), bR=getVal(allMeterData[6],'energy_reverse_total');
    setText('batChargeMonth',fmt(bF,1)); setText('batChargeYear',fmt(bF,1)); setText('batChargeTotal',fmt(bF,1));
    setText('batDischargeMonth',fmt(bR,1)); setText('batDischargeYear',fmt(bR,1)); setText('batDischargeTotal',fmt(bR,1));
  } else {
    const sp=sim.solar.power, op=sim.office.power, cp=sim.charging.power, stp=Math.abs(sim.storage.power);
    const net=+(gP+op+cp+stp).toFixed(1);
    ['gridMonthE','loadMonthE','dcMonthE','acMonthE','officeMonthE','pv1MonthE','pv2MonthE','batChargeMonth','batDischargeMonth'].forEach(id=>setText(id,fmt(gP,1)));
    ['gridYearE','loadYearE','dcYearE','acYearE','officeYearE','pv1YearE','pv2YearE','batChargeYear','batDischargeYear'].forEach(id=>setText(id,fmt(net,1)));
    ['gridTotalE','loadTotalE','dcTotalE','acTotalE','officeTotalE','pv1TotalE','pv2TotalE','batChargeTotal','batDischargeTotal'].forEach(id=>setText(id,fmt(net,1)));
  }
}

async function pollAllMeters() {
  const results = await Promise.all(meterAddrs.map(async addr => {
    const data = await getMeterRealtime(addr);
    if (data && data.data) { allMeterData[addr] = data; return true; }
    return false;
  }));
  hasRealData = results.some(r => r);
  updateFlowLabels();
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  updateDashClock();
  setInterval(updateDashClock, 1000);

  renderFlowDiagram();
  window.addEventListener('resize', () => { renderFlowDiagram(); updateFlowLabels(); });

  startPolling(pollAllMeters, 5000);
  // Simulated data refresh every 2s (like test2.vue)
  setInterval(() => { if (!hasRealData) updateFlowLabels(); }, 2000);
  setTimeout(updateFlowLabels, 300);
});
