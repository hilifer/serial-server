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

  // Symmetric spacing — generous, breathing room
  const topY = H * 0.14;       // top row y
  const midY = H * 0.45;       // center box y
  const botY = H * 0.82;       // bottom row y
  const d1 = W * 0.32;         // outer nodes offset (电网, 储能)
  const d2 = W * 0.13;         // inner nodes offset (光伏1, 光伏2)
  const d3 = W * 0.28;         // bottom outer offset (直流桩, 办公室)
  const R = Math.min(55, H * 0.1);    // top node radius — large
  const RB = Math.min(62, H * 0.11);  // bottom node radius — larger
  const rectHW = 72, rectHH = 34;     // center rect half-size — bigger

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
    const junctY = y1 + (y2 - y1) * 0.4;
    if (Math.abs(x - CX) < 3) return `M${x},${y1} L${x},${y2}`;
    return `M${x},${y1} L${x},${junctY} L${CX},${junctY} L${CX},${y2}`;
  }

  // 下方节点: 光储系统底部 → 垂直下到分叉高度 → 水平到节点x → 垂直下到节点顶部
  function centerToBot(node) {
    const x = node.x, y1 = midY + rectHH, y2 = node.y - node.r;
    const junctY = y1 + (y2 - y1) * 0.45;
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
    // Click-through: nodes with addr navigate to meter detail
    const clickAddr = { pv1:10, pv2:11, grid:1, storage:5, dc:8, ac:3, office:4 }[k];
    const clickAttr = clickAddr ? ` data-addr="${clickAddr}" style="cursor:pointer"` : '';
    svg += `<g class="flow-node-group"${clickAttr} style="--node-color:${n.bc}${clickAddr?';cursor:pointer':''}">`;
    if (n.isRect) {
      svg += `<rect x="${n.x-rectHW}" y="${n.y-rectHH}" width="${rectHW*2}" height="${rectHH*2}" rx="8"
        fill="rgba(0,20,60,0.9)" stroke="${n.bc}" stroke-width="2" stroke-dasharray="6 4"/>`;
      svg += `<text x="${n.x}" y="${n.y+6}" text-anchor="middle" font-size="16" fill="#00d4ff" font-weight="bold">${n.name}</text>`;
    } else {
      svg += `<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="rgba(0,20,60,0.9)" stroke="${n.bc}" stroke-width="2"/>`;
      svg += `<text x="${n.x}" y="${n.y - n.r*0.12}" text-anchor="middle" font-size="${n.r > 50 ? 34 : 30}">${n.icon}</text>`;
      svg += `<text x="${n.x}" y="${n.y + n.r*0.48}" text-anchor="middle" font-size="13" fill="#fff" font-weight="bold">${n.name}</text>`;
    }
    svg += `</g>`;
  });

  // Power labels — offset below top nodes, above bottom nodes
  const lg = 14;
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

  // Bind click handlers — nodes with data-addr navigate to meter detail
  wrap.querySelectorAll('[data-addr]').forEach(g => {
    g.addEventListener('click', () => {
      const a = g.getAttribute('data-addr');
      if (a) location.href = '/meter.html?addr=' + a;
    });
  });
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

  // Labels — use correct meter fields (voltage, not power!)
  // 电网 (addr 1, ADL400): 3-phase voltage + current
  const gVa = real ? getVal(allMeterData[1],'voltage_a') : 380;
  const gVb = real ? getVal(allMeterData[1],'voltage_b') : 380;
  const gVc = real ? getVal(allMeterData[1],'voltage_c') : 380;
  const gIa = real ? getVal(allMeterData[1],'current_a') : 10;
  const gIb = real ? getVal(allMeterData[1],'current_b') : 10;
  const gIc = real ? getVal(allMeterData[1],'current_c') : 10;
  setText('fG1', fmt(gVa)+'V '+fmt(gIa)+'A');
  setText('fG2', fmt(gVb)+'V '+fmt(gIb)+'A');
  setText('fG3', fmt(gVc)+'V '+fmt(gIc)+'A');

  // 光伏1/2 (addr 10/11, DJSF): voltage + current
  const pv1V = real ? getVal(allMeterData[10],'voltage') : sim.solar.voltage;
  const pv1I = real ? getVal(allMeterData[10],'current') : 10;
  const pv2V = real ? getVal(allMeterData[11],'voltage') : sim.solar.voltage;
  const pv2I = real ? getVal(allMeterData[11],'current') : 10;
  setText('fPv1', fmt(pv1V,0)+'V '+fmt(Math.abs(pv1I))+'A');
  setText('fPv2', fmt(pv2V,0)+'V '+fmt(Math.abs(pv2I))+'A');

  // 储能 (addr 5, DJSF): voltage + current (show sign for charge/discharge)
  const sV = real ? getVal(allMeterData[5],'voltage') : sim.storage.voltage;
  const sIval = real ? getVal(allMeterData[5],'current') : sim.storage.current;
  setText('fStor', fmt(sV)+'V '+fmt(sIval)+'A');

  setText('fDc',  fmt(dcP)+'kW');
  setText('fAc',  fmt(acP)+'kW');
  setText('fOff', fmt(oP)+'kW');

  // Right panel solar — PV power is negative (generating), show absolute
  setText('solarPowerBig', fmt(Math.abs(pv1P||0)+Math.abs(pv2P||0)));
  // Also update flow power — use absolute for animation direction
  flowPower.pv1 = Math.abs(pv1P||0);
  flowPower.pv2 = Math.abs(pv2P||0);
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
    // ---- 电网购电量 (addr 1, ADL400) ----
    // 总=组合有功总, 月/年=正向总(因为没有月冻结)
    const gridFwd = getVal(allMeterData[1],'energy_forward_total');
    const gridRev = getVal(allMeterData[1],'energy_reverse_total');
    const gridComb = getVal(allMeterData[1],'energy_combined_total');
    setText('gridMonthE', fmt(gridFwd,1));
    setText('gridYearE',  fmt(gridFwd,1));
    setText('gridTotalE', fmt(gridComb,1));

    // ---- 负载耗电量 (addr 4, ADL400) ----
    const loadFwd = getVal(allMeterData[4],'energy_forward_total');
    const loadComb = getVal(allMeterData[4],'energy_combined_total');
    setText('loadMonthE', fmt(loadFwd,1));
    setText('loadYearE',  fmt(loadFwd,1));
    setText('loadTotalE', fmt(loadComb || loadFwd,1));

    // ---- 直流桩耗电量 (addr 8+9, DJSF) ----
    const dc8 = getVal(allMeterData[8],'energy_forward_total') || 0;
    const dc9 = getVal(allMeterData[9],'energy_forward_total') || 0;
    setText('dcMonthE', fmt(dc8+dc9,1));
    setText('dcYearE',  fmt(dc8+dc9,1));
    setText('dcTotalE', fmt(dc8+dc9,1));

    // ---- 交流桩耗电量 (addr 3, ADL400) ----
    const acFwd = getVal(allMeterData[3],'energy_forward_total');
    const acComb = getVal(allMeterData[3],'energy_combined_total');
    setText('acMonthE', fmt(acFwd,1));
    setText('acYearE',  fmt(acFwd,1));
    setText('acTotalE', fmt(acComb || acFwd,1));

    // ---- 办公室耗电量 (addr 4, same as load) ----
    setText('officeMonthE', fmt(loadFwd,1));
    setText('officeYearE',  fmt(loadFwd,1));
    setText('officeTotalE', fmt(loadComb || loadFwd,1));

    // ---- 光伏1 (addr 10, DJSF) — 发电量在反向电能 ----
    const pv1Rev = getVal(allMeterData[10],'energy_reverse_total');
    const pv1Fwd = getVal(allMeterData[10],'energy_forward_total');
    setText('pv1MonthE', fmt(pv1Rev,1));
    setText('pv1YearE',  fmt(pv1Rev,1));
    setText('pv1TotalE', fmt(pv1Rev,1));

    // ---- 光伏2 (addr 11, DJSF) — 发电量在反向电能 ----
    const pv2Rev = getVal(allMeterData[11],'energy_reverse_total');
    setText('pv2MonthE', fmt(pv2Rev,1));
    setText('pv2YearE',  fmt(pv2Rev,1));
    setText('pv2TotalE', fmt(pv2Rev,1));

    // ---- 储能 (addr 6, DJSF) ----
    const batFwd = getVal(allMeterData[6],'energy_forward_total');  // 充电
    const batRev = getVal(allMeterData[6],'energy_reverse_total');  // 放电
    setText('batChargeMonth', fmt(batFwd,1));
    setText('batChargeYear',  fmt(batFwd,1));
    setText('batChargeTotal', fmt(batFwd,1));
    setText('batDischargeMonth', fmt(batRev,1));
    setText('batDischargeYear',  fmt(batRev,1));
    setText('batDischargeTotal', fmt(batRev,1));
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
