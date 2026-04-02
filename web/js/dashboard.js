/**
 * Energy dashboard — matches test2.vue from lizi.
 * SVG flow diagram with step-type paths and real meter data.
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
function getVal(data, key) {
  if (!data || !data.data || !data.data[key]) return null;
  return data.data[key].value;
}
function fmt(v, d) {
  if (v === null || v === undefined) return '--';
  return Number(v).toFixed(d === undefined ? 1 : d);
}
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ---- SVG Flow Diagram ----
function renderFlowDiagram() {
  const wrap = document.getElementById('flowDiagram');
  if (!wrap) return;
  const W = wrap.clientWidth || 800;
  const H = wrap.clientHeight || 500;

  // Node layout — top row: grid, pv1, pv2, storage; center: hub; bottom: dc, ac, office
  const topY = H * 0.18;
  const centerY = H * 0.48;
  const bottomY = H * 0.82;

  const nodes = [
    { id:'grid',    x: W*0.14, y: topY,    icon:'⚡', name:'电网',      borderColor:'#ff6b6b', labelColor:'#ff8c00', r: 42 },
    { id:'pv1',     x: W*0.38, y: topY,    icon:'☀️', name:'光伏1',     borderColor:'#ff9500', labelColor:'#ff9500', r: 42 },
    { id:'pv2',     x: W*0.58, y: topY,    icon:'☀️', name:'光伏2',     borderColor:'#ff9500', labelColor:'#ff9500', r: 42 },
    { id:'storage', x: W*0.82, y: topY,    icon:'🔋', name:'储能',      borderColor:'#00ffff', labelColor:'#00ffff', r: 42 },
    { id:'center',  x: W*0.48, y: centerY, icon:'',   name:'光储系统',  borderColor:'#3b82f6', isRect: true },
    { id:'dc',      x: W*0.18, y: bottomY, icon:'🚗', name:'直流充电桩', borderColor:'#ff9500', labelColor:'#ff9500', r: 42 },
    { id:'ac',      x: W*0.48, y: bottomY, icon:'🚗', name:'交流充电桩', borderColor:'#ff9500', labelColor:'#ff9500', r: 42 },
    { id:'office',  x: W*0.78, y: bottomY, icon:'💻', name:'办公室',    borderColor:'#4ecdc4', labelColor:'#8899aa', r: 42 },
  ];
  const nodeMap = {};
  nodes.forEach(n => nodeMap[n.id] = n);

  // Edges: step-type paths
  const edges = [
    { from:'grid',   to:'center', dashed: true },
    { from:'pv1',    to:'center', animated: true },
    { from:'pv2',    to:'center', animated: true },
    { from:'center', to:'storage', animated: true },
    { from:'center', to:'dc',      animated: true },
    { from:'center', to:'ac',      animated: true },
    { from:'center', to:'office',  animated: true },
  ];

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">`;

  // Draw step-path edges
  edges.forEach(e => {
    const s = nodeMap[e.from], t = nodeMap[e.to];
    const R = 42;
    let path;

    if (s.id === 'center') {
      // center → bottom nodes: go down from center, then horizontal to target, then down
      const startY = s.y + 30;
      const midY = (s.y + t.y) / 2;
      path = `M${s.x},${startY} L${s.x},${midY} L${t.x},${midY} L${t.x},${t.y - R}`;
    } else if (t.id === 'center') {
      // top nodes → center: go down from node, then horizontal to center, then down to center
      const startY = s.y + R;
      const midY = (s.y + t.y) / 2;
      if (Math.abs(s.x - t.x) < 5) {
        // Directly above — straight line
        path = `M${s.x},${startY} L${t.x},${t.y - 30}`;
      } else {
        path = `M${s.x},${startY} L${s.x},${midY} L${t.x},${midY} L${t.x},${t.y - 30}`;
      }
    } else {
      // center → storage (horizontal right)
      const startX = s.x + 55;
      path = `M${startX},${s.y} L${t.x - R},${t.y}`;
    }

    const cls = e.animated ? 'flow-edge animated' : 'flow-edge' + (e.dashed ? ' dashed' : '');
    svg += `<path d="${path}" class="${cls}"/>`;
  });

  // Draw nodes — each wrapped in <g> for hover effect
  nodes.forEach(n => {
    svg += `<g class="flow-node-group" style="--node-color:${n.borderColor}">`;
    if (n.isRect) {
      const rw = 110, rh = 50;
      svg += `<rect x="${n.x - rw/2}" y="${n.y - rh/2}" width="${rw}" height="${rh}" rx="4"
        fill="rgba(0,20,60,0.9)" stroke="${n.borderColor}" stroke-width="2" stroke-dasharray="5 3"/>`;
      svg += `<text x="${n.x}" y="${n.y + 5}" text-anchor="middle" font-size="14" fill="#00d4ff" font-weight="bold">${n.name}</text>`;
    } else {
      svg += `<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="rgba(0,20,60,0.9)"
        stroke="${n.borderColor}" stroke-width="2"/>`;
      svg += `<text x="${n.x}" y="${n.y - 4}" text-anchor="middle" font-size="24">${n.icon}</text>`;
      svg += `<text x="${n.x}" y="${n.y + 18}" text-anchor="middle" font-size="12" fill="#fff" font-weight="bold">${n.name}</text>`;
    }
    svg += `</g>`;
  });

  // Power labels — positioned below top-row nodes, above bottom-row nodes
  // Each label is a <text> with id for dynamic update
  const labels = [
    // Grid: 3 lines below node (3-phase data)
    { id:'fGrid1', x: nodeMap.grid.x, y: topY + 55, color:'#ff8c00' },
    { id:'fGrid2', x: nodeMap.grid.x, y: topY + 70, color:'#ff8c00' },
    { id:'fGrid3', x: nodeMap.grid.x, y: topY + 85, color:'#ff8c00' },
    // PV1, PV2: below
    { id:'fPv1', x: nodeMap.pv1.x, y: topY + 58, color:'#ff9500' },
    { id:'fPv2', x: nodeMap.pv2.x, y: topY + 58, color:'#ff9500' },
    // Storage: below
    { id:'fStor', x: nodeMap.storage.x, y: topY + 58, color:'#00ffff' },
    // DC pile, AC pile, Office: above
    { id:'fDc',     x: nodeMap.dc.x,     y: bottomY - 55, color:'#ff9500' },
    { id:'fAc',     x: nodeMap.ac.x,     y: bottomY - 55, color:'#ff9500' },
    { id:'fOffice', x: nodeMap.office.x, y: bottomY - 55, color:'#8899aa' },
  ];
  labels.forEach(l => {
    svg += `<text id="${l.id}" x="${l.x}" y="${l.y}" text-anchor="middle" font-size="11" fill="${l.color}" font-weight="bold">--</text>`;
  });

  svg += '</svg>';
  wrap.innerHTML = svg;
}

// ---- Data polling & update ----
const meterAddrs = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11];
let allMeterData = {};

function updateFlowLabels() {
  // Grid (addr 1) — 3-phase voltage/current
  const gVa = getVal(allMeterData[1], 'voltage_a');
  const gIa = getVal(allMeterData[1], 'current_a');
  const gVb = getVal(allMeterData[1], 'voltage_b');
  const gIb = getVal(allMeterData[1], 'current_b');
  const gVc = getVal(allMeterData[1], 'voltage_c');
  const gIc = getVal(allMeterData[1], 'current_c');
  const gP  = getVal(allMeterData[1], 'power_total');
  setText('fGrid1', gVa ? fmt(gP)+'V ' + fmt(gIa)+'A' : '--');
  setText('fGrid2', gVb ? fmt(gP)+'V ' + fmt(gIb)+'A' : '--');
  setText('fGrid3', gVc ? fmt(gP)+'V ' + fmt(gIc)+'A' : '--');

  // PV1 (addr 10), PV2 (addr 11)
  const pv1V = getVal(allMeterData[10], 'voltage');
  const pv1I = getVal(allMeterData[10], 'current');
  const pv2V = getVal(allMeterData[11], 'voltage');
  const pv2I = getVal(allMeterData[11], 'current');
  setText('fPv1', pv1V ? fmt(pv1V,0)+'V ' + fmt(Math.abs(pv1I),0)+'A' : '--');
  setText('fPv2', pv2V ? fmt(pv2V,0)+'V ' + fmt(Math.abs(pv2I),0)+'A' : '--');

  // Storage (addr 5) — show negative values
  const sV = getVal(allMeterData[5], 'voltage');
  const sP = getVal(allMeterData[5], 'power');
  const sI = getVal(allMeterData[5], 'current');
  setText('fStor', sV ? fmt(sP)+'V ' + fmt(sI)+'A' : '--');

  // DC piles (addr 8+9 combined power)
  const dc8P = getVal(allMeterData[8], 'power') || 0;
  const dc9P = getVal(allMeterData[9], 'power') || 0;
  const dcTotal = Math.abs(dc8P) + Math.abs(dc9P);
  setText('fDc', dcTotal ? fmt(dcTotal)+'kW' : '--');

  // AC pile (addr 3)
  const acP = getVal(allMeterData[3], 'power_total');
  setText('fAc', acP !== null ? fmt(Math.abs(acP))+'kW' : '--');

  // Office (addr 4)
  const offP = getVal(allMeterData[4], 'power_total');
  setText('fOffice', offP !== null ? fmt(Math.abs(offP))+'kW' : '--');

  // Right panel — solar hero
  const pv1P = Math.abs(getVal(allMeterData[10], 'power') || 0);
  const pv2P = Math.abs(getVal(allMeterData[11], 'power') || 0);
  setText('solarPowerBig', fmt(pv1P + pv2P));
  setText('solarVoltage', pv1V ? fmt(pv1V)+'V' : '--V');
  setText('solarCurrent', pv1I ? fmt(Math.abs(pv1I))+'A' : '--A');

  // Energy cards
  updateEnergyCards();
}

function updateEnergyCards() {
  // Grid energy (addr 1 — ADL400)
  const gridFwd = getVal(allMeterData[1], 'energy_forward_total');
  const gridRev = getVal(allMeterData[1], 'energy_reverse_total');
  setText('gridMonthE', fmt(gridFwd, 1));
  setText('gridYearE',  fmt(gridFwd, 1));
  setText('gridTotalE', fmt(gridFwd ? gridFwd + (gridRev||0) : null, 1));

  // Load/Office (addr 4 — ADL400)
  const loadFwd = getVal(allMeterData[4], 'energy_forward_total');
  setText('loadMonthE',   fmt(loadFwd, 1));
  setText('loadYearE',    fmt(loadFwd, 1));
  setText('loadTotalE',   fmt(loadFwd, 1));
  setText('officeMonthE', fmt(loadFwd, 1));
  setText('officeYearE',  fmt(loadFwd, 1));
  setText('officeTotalE', fmt(loadFwd, 1));

  // DC pile (addr 8+9 — DJSF)
  const dc8Fwd = getVal(allMeterData[8], 'energy_forward_total') || 0;
  const dc9Fwd = getVal(allMeterData[9], 'energy_forward_total') || 0;
  setText('dcMonthE', fmt(dc8Fwd + dc9Fwd, 1));
  setText('dcYearE',  fmt(dc8Fwd + dc9Fwd, 1));
  setText('dcTotalE', fmt(dc8Fwd + dc9Fwd, 1));

  // AC pile (addr 3 — ADL400)
  const acFwd = getVal(allMeterData[3], 'energy_forward_total');
  setText('acMonthE', fmt(acFwd, 1));
  setText('acYearE',  fmt(acFwd, 1));
  setText('acTotalE', fmt(acFwd, 1));

  // PV1 (addr 10), PV2 (addr 11)
  const pv1Fwd = getVal(allMeterData[10], 'energy_forward_total');
  const pv2Fwd = getVal(allMeterData[11], 'energy_forward_total');
  setText('pv1MonthE', fmt(pv1Fwd, 1));
  setText('pv1YearE',  fmt(pv1Fwd, 1));
  setText('pv1TotalE', fmt(pv1Fwd, 1));
  setText('pv2MonthE', fmt(pv2Fwd, 1));
  setText('pv2YearE',  fmt(pv2Fwd, 1));
  setText('pv2TotalE', fmt(pv2Fwd, 1));

  // Battery charge/discharge (addr 6 — DJSF)
  const batFwd = getVal(allMeterData[6], 'energy_forward_total');
  const batRev = getVal(allMeterData[6], 'energy_reverse_total');
  setText('batChargeMonth',    fmt(batFwd, 1));
  setText('batChargeYear',     fmt(batFwd, 1));
  setText('batChargeTotal',    fmt(batFwd, 1));
  setText('batDischargeMonth', fmt(batRev, 1));
  setText('batDischargeYear',  fmt(batRev, 1));
  setText('batDischargeTotal', fmt(batRev, 1));
}

async function pollAllMeters() {
  const promises = meterAddrs.map(async addr => {
    const data = await getMeterRealtime(addr);
    if (data) allMeterData[addr] = data;
  });
  await Promise.all(promises);
  updateFlowLabels();
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  updateDashClock();
  setInterval(updateDashClock, 1000);

  renderFlowDiagram();
  window.addEventListener('resize', () => { renderFlowDiagram(); updateFlowLabels(); });

  startPolling(pollAllMeters, 5000);
});
