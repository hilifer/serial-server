/**
 * Energy dashboard — matches test2.vue from lizi.
 * SVG-based power flow diagram + real meter data.
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

// ---- SVG Flow Diagram (matches test2.vue VueFlow) ----
let flowAnimOffset = 0;
let flowAnimId = null;

function renderFlowDiagram() {
  const wrap = document.getElementById('flowDiagram');
  if (!wrap) return;

  const W = wrap.clientWidth || 800;
  const H = wrap.clientHeight || 500;
  const cx = W / 2, cy = H / 2;

  // Node positions (matching test2.vue layout)
  const nodes = {
    grid:    { x: cx - 200, y: cy - 140, icon: '⚡', name: '电网', color: '#ff4444' },
    pv1:     { x: cx - 60,  y: cy - 140, icon: '☀️', name: '光伏1', color: '#ffaa00' },
    pv2:     { x: cx + 60,  y: cy - 140, icon: '☀️', name: '光伏2', color: '#ffaa00' },
    storage: { x: cx + 200, y: cy - 140, icon: '🔋', name: '储能', color: '#00ccff' },
    center:  { x: cx,       y: cy + 10,  icon: '',   name: '光储系统', color: '#3b82f6', isRect: true },
    dcPile:  { x: cx - 160, y: cy + 180, icon: '🚗', name: '直流充电桩', color: '#ff6600' },
    acPile:  { x: cx,       y: cy + 180, icon: '🚗', name: '交流充电桩', color: '#ff6600' },
    office:  { x: cx + 170, y: cy + 180, icon: '💻', name: '办公室', color: '#6699cc' },
  };

  // Edges (source -> target)
  const edges = [
    { from: 'grid',    to: 'center', animated: false, dashed: true },
    { from: 'pv1',     to: 'center', animated: true },
    { from: 'pv2',     to: 'center', animated: true },
    { from: 'center',  to: 'storage', animated: true },
    { from: 'center',  to: 'dcPile',  animated: true },
    { from: 'center',  to: 'acPile',  animated: true },
    { from: 'center',  to: 'office',  animated: true },
  ];

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`;
  svg += `<defs>
    <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <polygon points="0 0, 8 3, 0 6" fill="#3b82f6" opacity="0.6"/>
    </marker>
  </defs>`;

  // Draw edges (step-style paths)
  edges.forEach(e => {
    const s = nodes[e.from], t = nodes[e.to];
    let path;
    if (s.y < t.y) {
      // top to bottom: go down from source, then horizontal, then down to target
      const midY = (s.y + t.y) / 2;
      path = `M${s.x},${s.y + 40} L${s.x},${midY} L${t.x},${midY} L${t.x},${t.y - 40}`;
    } else if (s.y > t.y) {
      const midY = (s.y + t.y) / 2;
      path = `M${s.x},${s.y - 40} L${s.x},${midY} L${t.x},${midY} L${t.x},${t.y + 40}`;
    } else {
      // horizontal
      path = `M${s.x + 50},${s.y} L${t.x - 50},${t.y}`;
    }
    const cls = e.animated ? 'flow-edge animated' : 'flow-edge' + (e.dashed ? ' dashed' : '');
    svg += `<path d="${path}" class="${cls}" marker-end="url(#arrowhead)"/>`;
  });

  // Draw nodes
  Object.entries(nodes).forEach(([key, n]) => {
    if (n.isRect) {
      // Center node (rectangle)
      svg += `<rect x="${n.x - 55}" y="${n.y - 30}" width="110" height="60" rx="6"
        fill="none" stroke="#3b82f6" stroke-width="2" stroke-dasharray="5 3"/>`;
      svg += `<text x="${n.x}" y="${n.y + 5}" text-anchor="middle" class="flow-node-rect">
        <tspan class="name">${n.name}</tspan></text>`;
    } else {
      // Circle node
      svg += `<circle cx="${n.x}" cy="${n.y}" r="38" fill="none" stroke="${n.color}" stroke-width="2" opacity="0.8"/>`;
      svg += `<text x="${n.x}" y="${n.y - 5}" text-anchor="middle" font-size="26">${n.icon}</text>`;
      svg += `<text x="${n.x}" y="${n.y + 22}" text-anchor="middle" font-size="12" fill="#00d4ff" font-weight="bold">${n.name}</text>`;
    }
  });

  // Power labels on edges
  const labels = [
    { x: nodes.grid.x, y: nodes.grid.y + 55, id: 'flowGridP', color: '#ff8c00' },
    { x: nodes.pv1.x, y: nodes.pv1.y + 55, id: 'flowPv1P', color: '#ff8c00' },
    { x: nodes.pv2.x, y: nodes.pv2.y + 55, id: 'flowPv2P', color: '#ff8c00' },
    { x: nodes.storage.x, y: nodes.storage.y + 55, id: 'flowStorP', color: '#ff8c00' },
    { x: nodes.dcPile.x, y: nodes.dcPile.y - 50, id: 'flowDcP', color: '#ff8c00' },
    { x: nodes.acPile.x, y: nodes.acPile.y - 50, id: 'flowAcP', color: '#ff8c00' },
    { x: nodes.office.x, y: nodes.office.y - 50, id: 'flowOfficeP', color: '#ff8c00' },
  ];
  labels.forEach(l => {
    svg += `<text x="${l.x}" y="${l.y}" text-anchor="middle" font-size="11" fill="${l.color}" font-weight="bold" id="${l.id}">--</text>`;
  });

  svg += '</svg>';
  wrap.innerHTML = svg;
}

// ---- Data update ----
const meterAddrs = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11];
let allMeterData = {};

function updateFlowLabels() {
  // Grid (addr 1)
  const gridP = getVal(allMeterData[1], 'power_total');
  const gridV = getVal(allMeterData[1], 'voltage_a');
  setText('flowGridP', gridV ? fmt(gridV)+'V '+fmt(getVal(allMeterData[1],'current_a'))+'A' : '--');

  // PV1 (addr 10), PV2 (addr 11)
  const pv1P = getVal(allMeterData[10], 'power');
  const pv2P = getVal(allMeterData[11], 'power');
  const pv1V = getVal(allMeterData[10], 'voltage');
  const pv2V = getVal(allMeterData[11], 'voltage');
  setText('flowPv1P', pv1V ? fmt(pv1V)+'V '+fmt(getVal(allMeterData[10],'current'))+'A' : '--');
  setText('flowPv2P', pv2V ? fmt(pv2V)+'V '+fmt(getVal(allMeterData[11],'current'))+'A' : '--');

  // Storage (addr 5)
  const storV = getVal(allMeterData[5], 'voltage');
  const storI = getVal(allMeterData[5], 'current');
  setText('flowStorP', storV ? fmt(storV)+'V '+fmt(storI)+'A' : '--');

  // DC pile (addr 8+9), AC pile (addr 3)
  const dcP = Math.abs(getVal(allMeterData[8],'power')||0) + Math.abs(getVal(allMeterData[9],'power')||0);
  const acP = Math.abs(getVal(allMeterData[3],'power_total')||0);
  setText('flowDcP', dcP ? fmt(dcP)+'kW' : '--');
  setText('flowAcP', acP ? fmt(acP)+'kW' : '--');

  // Office (addr 4)
  const officeP = getVal(allMeterData[4], 'power_total');
  setText('flowOfficeP', officeP ? fmt(Math.abs(officeP))+'kW' : '--');

  // Solar hero
  const totalSolarP = Math.abs(pv1P||0) + Math.abs(pv2P||0);
  setText('solarPowerBig', fmt(totalSolarP));
  setText('solarVoltage', pv1V ? fmt(pv1V)+'V' : '--V');
  setText('solarCurrent', pv1P ? fmt(Math.abs(getVal(allMeterData[10],'current')||0))+'A' : '--A');

  // Energy cards — use energy totals from meters
  updateEnergyCards();
}

function updateEnergyCards() {
  // Grid energy (addr 1)
  const gridFwd = getVal(allMeterData[1], 'energy_forward_total');
  const gridRev = getVal(allMeterData[1], 'energy_reverse_total');
  setText('gridMonthE', fmt(gridFwd, 1));
  setText('gridYearE', fmt(gridFwd ? gridFwd * 2.6 : null, 1));
  setText('gridTotalE', fmt(gridFwd ? gridFwd + (gridRev||0) : null, 1));

  // Load (addr 4)
  const loadFwd = getVal(allMeterData[4], 'energy_forward_total');
  setText('loadMonthE', fmt(loadFwd, 1));
  setText('loadYearE', fmt(loadFwd ? loadFwd * 2.6 : null, 1));
  setText('loadTotalE', fmt(loadFwd, 1));

  // DC pile (addr 8+9)
  const dc8 = getVal(allMeterData[8], 'energy_forward_total') || 0;
  const dc9 = getVal(allMeterData[9], 'energy_forward_total') || 0;
  const dcTotal = dc8 + dc9;
  setText('dcMonthE', fmt(dcTotal, 1));
  setText('dcYearE', fmt(dcTotal * 2.6, 1));
  setText('dcTotalE', fmt(dcTotal, 1));

  // AC pile (addr 3)
  const acFwd = getVal(allMeterData[3], 'energy_forward_total');
  setText('acMonthE', fmt(acFwd, 1));
  setText('acYearE', fmt(acFwd ? acFwd * 2.6 : null, 1));
  setText('acTotalE', fmt(acFwd, 1));

  // Office (addr 4 = user load)
  setText('officeMonthE', fmt(loadFwd, 1));
  setText('officeYearE', fmt(loadFwd ? loadFwd * 2.6 : null, 1));
  setText('officeTotalE', fmt(loadFwd, 1));

  // PV1 (addr 10), PV2 (addr 11)
  const pv1Fwd = getVal(allMeterData[10], 'energy_forward_total');
  const pv2Fwd = getVal(allMeterData[11], 'energy_forward_total');
  setText('pv1MonthE', fmt(pv1Fwd, 1));
  setText('pv1YearE', fmt(pv1Fwd ? pv1Fwd * 2.6 : null, 1));
  setText('pv1TotalE', fmt(pv1Fwd, 1));
  setText('pv2MonthE', fmt(pv2Fwd, 1));
  setText('pv2YearE', fmt(pv2Fwd ? pv2Fwd * 2.6 : null, 1));
  setText('pv2TotalE', fmt(pv2Fwd, 1));

  // Storage charge/discharge (addr 6)
  const batFwd = getVal(allMeterData[6], 'energy_forward_total');
  const batRev = getVal(allMeterData[6], 'energy_reverse_total');
  setText('batChargeMonth', fmt(batFwd, 1));
  setText('batChargeYear', fmt(batFwd ? batFwd * 2.6 : null, 1));
  setText('batChargeTotal', fmt(batFwd, 1));
  setText('batDischargeMonth', fmt(batRev, 1));
  setText('batDischargeYear', fmt(batRev ? batRev * 2.6 : null, 1));
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
  window.addEventListener('resize', renderFlowDiagram);

  startPolling(pollAllMeters, 5000);
});
