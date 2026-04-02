/**
 * Energy dashboard — matches test2.vue VueFlow layout exactly.
 * Data: real API when available, simulated otherwise (like lizi).
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
function setSvgText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ---- Simulated data (matches test2.vue mock data, updates dynamically) ----
const simData = {
  grid:    { voltage: 380.2, current: 125.6, power: 47.8 },
  solar:   { voltage: 720.5, current: 92.3, power: 66.4 },
  storage: { voltage: 51.8, current: -158.2, power: -25.6, soc: 82 },
  charging:{ voltage: 380.0, current: 245.7, power: 93.4 },
  office:  { voltage: 220.0, current: 136.4, power: 30.0 },
};

function rnd() { return Math.floor(Math.random() * 100); }

function updateSimData() {
  simData.grid.voltage = 380 + (rnd() - 50) * 0.1;
  simData.grid.current = 120 + rnd() * 0.2;
  simData.grid.power = +(47 + (rnd() - 50) * 0.1).toFixed(1);
  simData.solar.power = +(60 + rnd() * 0.3).toFixed(1);
  simData.solar.current = +(85 + rnd() * 0.2).toFixed(1);
  simData.storage.soc = Math.max(0, Math.min(100, simData.storage.soc + (rnd() - 50) * 0.02));
  simData.storage.current = simData.storage.soc > 50 ? +(-140 + rnd() * 0.4).toFixed(1) : +(140 + rnd() * 0.4).toFixed(1);
  simData.storage.power = +(simData.storage.current * simData.storage.voltage / 1000).toFixed(1);
  const hour = new Date().getHours();
  simData.office.power = (hour >= 9 && hour <= 18) ? +(25 + rnd() * 0.1).toFixed(1) : +(8 + rnd() * 0.05).toFixed(1);
  simData.charging.power = +(90 + rnd() * 0.05).toFixed(1);
}

// ---- SVG Flow Diagram — exact VueFlow layout from test2.vue ----
function renderFlowDiagram() {
  const wrap = document.getElementById('flowDiagram');
  if (!wrap) return;
  const W = wrap.clientWidth || 800;
  const H = wrap.clientHeight || 500;

  // Map VueFlow coords to SVG viewport
  // VueFlow: x range [-250, 250], y range [-200, 250] → center each node is 120x120
  const cx = W * 0.48, cy = H * 0.42;
  const sx = W / 600, sy = H / 550; // scale factors

  function mapX(vx) { return cx + vx * sx; }
  function mapY(vy) { return cy + vy * sy; }

  // Node definitions — positions from test2.vue source
  const N = {
    grid:    { vx:-250, vy:-200, icon:'⚡', name:'电网',      border:'#ff6b6b', labelColor:'#ff8c00', r:48 },
    pv1:     { vx:-80,  vy:-200, icon:'☀️', name:'光伏1',     border:'#ff9500', labelColor:'#ff9500', r:48 },
    pv2:     { vx:80,   vy:-200, icon:'☀️', name:'光伏2',     border:'#ff9500', labelColor:'#ff9500', r:48 },
    storage: { vx:250,  vy:-200, icon:'🔋', name:'储能',      border:'#00ffff', labelColor:'#00ffff', r:48 },
    center:  { vx:0,    vy:0,    icon:'',   name:'光储系统',  border:'#3b82f6', isRect:true },
    dc:      { vx:-200, vy:250,  icon:'🚗', name:'直流充电桩', border:'#ff9500', labelColor:'#ff9500', r:52 },
    ac:      { vx:0,    vy:250,  icon:'🚗', name:'交流充电桩', border:'#ff9500', labelColor:'#ff9500', r:52 },
    office:  { vx:200,  vy:250,  icon:'💻', name:'办公室',    border:'#4ecdc4', labelColor:'#8899bb', r:52 },
  };

  // Compute screen positions
  Object.values(N).forEach(n => { n.x = mapX(n.vx); n.y = mapY(n.vy); });

  // Step-type edge path builder (orthogonal, matching VueFlow step edge)
  function stepPath(from, to, fromSide, toSide) {
    let x1 = from.x, y1 = from.y, x2 = to.x, y2 = to.y;
    const R = from.r || 30;
    const R2 = to.r || 30;
    const rectH = 30, rectW = 65;

    // Adjust start/end points based on sides
    if (fromSide === 'bottom') y1 += R;
    else if (fromSide === 'right') x1 += (from.isRect ? rectW : R);
    else if (fromSide === 'left') x1 -= (from.isRect ? rectW : R);

    if (toSide === 'top') y2 -= R2;
    else if (toSide === 'left') { x2 -= (to.isRect ? rectW : R2); }
    else if (toSide === 'right') { x2 += (to.isRect ? rectW : R2); }
    else if (toSide === 'bottom') y2 += R2;

    // VueFlow step: midpoint horizontal or vertical
    if (fromSide === 'bottom' && toSide === 'top') {
      const midY = (y1 + y2) / 2;
      return `M${x1},${y1} L${x1},${midY} L${x2},${midY} L${x2},${y2}`;
    }
    if (fromSide === 'bottom' && toSide === 'left') {
      const midY = (y1 + y2) / 2;
      return `M${x1},${y1} L${x1},${midY} L${x2},${midY} L${x2},${y2}`;
    }
    if (fromSide === 'right' && toSide === 'bottom') {
      const midX = (x1 + x2) / 2;
      return `M${x1},${y1} L${midX},${y1} L${midX},${y2} L${x2},${y2}`;
    }
    // Default
    const midY = (y1 + y2) / 2;
    return `M${x1},${y1} L${x1},${midY} L${x2},${midY} L${x2},${y2}`;
  }

  // Edges — from test2.vue source
  const edges = [
    { from:'grid',   to:'center', fromSide:'bottom', toSide:'left',   dashed:true },  // 0→5 targetHandle:sl
    { from:'pv1',    to:'center', fromSide:'bottom', toSide:'top',    animated:true }, // 1→5
    { from:'pv2',    to:'center', fromSide:'bottom', toSide:'top',    animated:true }, // 6→5
    { from:'center', to:'storage',fromSide:'right',  toSide:'bottom', animated:true }, // 5→2 sourceHandle:sr
    { from:'center', to:'dc',     fromSide:'bottom', toSide:'top',    animated:true }, // 5→3
    { from:'center', to:'ac',     fromSide:'bottom', toSide:'top',    animated:true }, // 5→7
    { from:'center', to:'office', fromSide:'bottom', toSide:'top',    animated:true }, // 5→4
  ];

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">`;

  // Draw edges
  edges.forEach(e => {
    const s = N[e.from], t = N[e.to];
    const d = stepPath(s, t, e.fromSide, e.toSide);
    let cls = 'flow-edge';
    if (e.animated) cls += ' animated';
    if (e.dashed) cls += ' dashed';
    svg += `<path d="${d}" class="${cls}"/>`;
  });

  // Draw nodes
  Object.entries(N).forEach(([key, n]) => {
    svg += `<g class="flow-node-group" style="--node-color:${n.border}">`;
    if (n.isRect) {
      const rw = 130, rh = 56;
      svg += `<rect x="${n.x-rw/2}" y="${n.y-rh/2}" width="${rw}" height="${rh}" rx="5"
        fill="rgba(0,20,60,0.9)" stroke="${n.border}" stroke-width="2" stroke-dasharray="5 3"/>`;
      svg += `<text x="${n.x}" y="${n.y+5}" text-anchor="middle" font-size="14" fill="#00d4ff" font-weight="bold">${n.name}</text>`;
    } else {
      svg += `<circle cx="${n.x}" cy="${n.y}" r="${n.r}" fill="rgba(0,20,60,0.9)"
        stroke="${n.border}" stroke-width="2"/>`;
      svg += `<text x="${n.x}" y="${n.y-6}" text-anchor="middle" font-size="28">${n.icon}</text>`;
      svg += `<text x="${n.x}" y="${n.y+20}" text-anchor="middle" font-size="13" fill="#fff" font-weight="bold">${n.name}</text>`;
    }
    svg += `</g>`;
  });

  // Power labels — top row: below node; bottom row: above node
  // Grid: 3 lines (matching test2.vue template)
  const gx = N.grid.x, gy = N.grid.y;
  svg += `<text id="fG1" x="${gx}" y="${gy+N.grid.r+18}" text-anchor="middle" font-size="11" fill="#ff8c00" font-weight="bold">--</text>`;
  svg += `<text id="fG2" x="${gx}" y="${gy+N.grid.r+33}" text-anchor="middle" font-size="11" fill="#ff8c00" font-weight="bold">--</text>`;
  svg += `<text id="fG3" x="${gx}" y="${gy+N.grid.r+48}" text-anchor="middle" font-size="11" fill="#ff8c00" font-weight="bold">--</text>`;
  // PV1, PV2
  svg += `<text id="fPv1" x="${N.pv1.x}" y="${N.pv1.y+N.pv1.r+18}" text-anchor="middle" font-size="11" fill="#ff9500" font-weight="bold">--</text>`;
  svg += `<text id="fPv2" x="${N.pv2.x}" y="${N.pv2.y+N.pv2.r+18}" text-anchor="middle" font-size="11" fill="#ff9500" font-weight="bold">--</text>`;
  // Storage
  svg += `<text id="fStor" x="${N.storage.x}" y="${N.storage.y+N.storage.r+18}" text-anchor="middle" font-size="11" fill="#00ffff" font-weight="bold">--</text>`;
  // Bottom row: labels ABOVE nodes
  svg += `<text id="fDc" x="${N.dc.x}" y="${N.dc.y-N.dc.r-10}" text-anchor="middle" font-size="12" fill="#ff9500" font-weight="bold">--</text>`;
  svg += `<text id="fAc" x="${N.ac.x}" y="${N.ac.y-N.ac.r-10}" text-anchor="middle" font-size="12" fill="#ff9500" font-weight="bold">--</text>`;
  svg += `<text id="fOff" x="${N.office.x}" y="${N.office.y-N.office.r-10}" text-anchor="middle" font-size="12" fill="#8899bb" font-weight="bold">--</text>`;

  svg += '</svg>';
  wrap.innerHTML = svg;
}

// ---- Data update (real API + simulated fallback) ----
const meterAddrs = [1, 2, 3, 4, 5, 6, 8, 9, 10, 11];
let allMeterData = {};
let hasRealData = false;

function updateFlowLabels() {
  // Determine data source: real API or simulated
  const useReal = hasRealData;

  let gridPower, gridCurrent;
  let pv1Power, pv1Current, pv2Power, pv2Current;
  let storPower, storCurrent;
  let chargingPower, officePower;

  if (useReal) {
    gridPower   = getVal(allMeterData[1], 'power_total');
    gridCurrent = getVal(allMeterData[1], 'current_a');
    pv1Power    = getVal(allMeterData[10], 'power');
    pv1Current  = getVal(allMeterData[10], 'current');
    pv2Power    = getVal(allMeterData[11], 'power');
    pv2Current  = getVal(allMeterData[11], 'current');
    storPower   = getVal(allMeterData[5], 'power');
    storCurrent = getVal(allMeterData[5], 'current');
    chargingPower = (Math.abs(getVal(allMeterData[8],'power')||0) + Math.abs(getVal(allMeterData[9],'power')||0)) || null;
    officePower = getVal(allMeterData[4], 'power_total');
  } else {
    updateSimData();
    gridPower   = simData.grid.power;
    gridCurrent = 10;
    pv1Power    = simData.solar.power;
    pv1Current  = 10;
    pv2Power    = simData.solar.power;
    pv2Current  = 10;
    storPower   = simData.storage.power;
    storCurrent = simData.storage.power;
    chargingPower = simData.charging.power;
    officePower = simData.office.power;
  }

  // Flow labels — matching test2.vue template format exactly:
  // 电网: gridData.power + "V 10A" × 3 lines
  setSvgText('fG1', fmt(gridPower) + 'V ' + fmt(gridCurrent,0) + 'A');
  setSvgText('fG2', fmt(gridPower) + 'V ' + fmt(gridCurrent,0) + 'A');
  setSvgText('fG3', fmt(gridPower) + 'V ' + fmt(gridCurrent,0) + 'A');
  // 光伏: solarData.power + "V 10A"
  setSvgText('fPv1', fmt(pv1Power,0) + 'V ' + fmt(pv1Current,0) + 'A');
  setSvgText('fPv2', fmt(pv2Power,0) + 'V ' + fmt(pv2Current,0) + 'A');
  // 储能: storageData.power + "V" + storageData.power + "A"
  setSvgText('fStor', fmt(storPower) + 'V ' + fmt(storCurrent) + 'A');
  // 充电桩: chargingData.power + "kW"
  setSvgText('fDc', fmt(chargingPower) + 'kW');
  setSvgText('fAc', fmt(chargingPower) + 'kW');
  // 办公室: officeLoad.power + "kW"
  setSvgText('fOff', fmt(officePower) + 'kW');

  // Right panel — solar hero
  const totalSolarP = Math.abs(pv1Power||0) + Math.abs(pv2Power||0);
  setText('solarPowerBig', fmt(totalSolarP));
  setText('solarVoltage', fmt(useReal ? getVal(allMeterData[10],'voltage') : simData.solar.voltage) + 'V');
  setText('solarCurrent', fmt(useReal ? Math.abs(getVal(allMeterData[10],'current')||0) : simData.solar.current) + 'A');

  // Energy cards
  updateEnergyCards();
}

function updateEnergyCards() {
  const useReal = hasRealData;

  if (useReal) {
    // Grid (addr 1)
    const gF = getVal(allMeterData[1], 'energy_forward_total');
    const gR = getVal(allMeterData[1], 'energy_reverse_total');
    setText('gridMonthE', fmt(gF,1)); setText('gridYearE', fmt(gF,1)); setText('gridTotalE', fmt(gF ? gF+(gR||0) : null,1));
    // Load (addr 4)
    const lF = getVal(allMeterData[4], 'energy_forward_total');
    setText('loadMonthE', fmt(lF,1)); setText('loadYearE', fmt(lF,1)); setText('loadTotalE', fmt(lF,1));
    setText('officeMonthE', fmt(lF,1)); setText('officeYearE', fmt(lF,1)); setText('officeTotalE', fmt(lF,1));
    // DC (addr 8+9)
    const d8 = getVal(allMeterData[8],'energy_forward_total')||0;
    const d9 = getVal(allMeterData[9],'energy_forward_total')||0;
    setText('dcMonthE', fmt(d8+d9,1)); setText('dcYearE', fmt(d8+d9,1)); setText('dcTotalE', fmt(d8+d9,1));
    // AC (addr 3)
    const aF = getVal(allMeterData[3], 'energy_forward_total');
    setText('acMonthE', fmt(aF,1)); setText('acYearE', fmt(aF,1)); setText('acTotalE', fmt(aF,1));
    // PV (addr 10, 11)
    const p1 = getVal(allMeterData[10],'energy_forward_total');
    const p2 = getVal(allMeterData[11],'energy_forward_total');
    setText('pv1MonthE',fmt(p1,1)); setText('pv1YearE',fmt(p1,1)); setText('pv1TotalE',fmt(p1,1));
    setText('pv2MonthE',fmt(p2,1)); setText('pv2YearE',fmt(p2,1)); setText('pv2TotalE',fmt(p2,1));
    // Battery (addr 6)
    const bF = getVal(allMeterData[6],'energy_forward_total');
    const bR = getVal(allMeterData[6],'energy_reverse_total');
    setText('batChargeMonth',fmt(bF,1)); setText('batChargeYear',fmt(bF,1)); setText('batChargeTotal',fmt(bF,1));
    setText('batDischargeMonth',fmt(bR,1)); setText('batDischargeYear',fmt(bR,1)); setText('batDischargeTotal',fmt(bR,1));
  } else {
    // Simulated energy values (like test2.vue computed properties)
    const gp = simData.grid.power;
    const sp = simData.solar.power;
    const op = simData.office.power;
    const cp = simData.charging.power;
    const stoP = Math.abs(simData.storage.power);
    const gridNet = +(gp + op + cp + stoP).toFixed(1);
    setText('gridMonthE', fmt(gp,1)); setText('gridYearE', fmt(gridNet,1)); setText('gridTotalE', fmt(gridNet,1));
    setText('loadMonthE', fmt(gp,1)); setText('loadYearE', fmt(gridNet,1)); setText('loadTotalE', fmt(gridNet,1));
    setText('dcMonthE', fmt(gp,1)); setText('dcYearE', fmt(gridNet,1)); setText('dcTotalE', fmt(gridNet,1));
    setText('acMonthE', fmt(gp,1)); setText('acYearE', fmt(gridNet,1)); setText('acTotalE', fmt(gridNet,1));
    setText('officeMonthE', fmt(gp,1)); setText('officeYearE', fmt(gridNet,1)); setText('officeTotalE', fmt(gridNet,1));
    setText('pv1MonthE', fmt(gp,1)); setText('pv1YearE', fmt(gridNet,1)); setText('pv1TotalE', fmt(gridNet,1));
    setText('pv2MonthE', fmt(gp,1)); setText('pv2YearE', fmt(gridNet,1)); setText('pv2TotalE', fmt(gridNet,1));
    setText('batChargeMonth', fmt(gp,1)); setText('batChargeYear', fmt(gridNet,1)); setText('batChargeTotal', fmt(gridNet,1));
    setText('batDischargeMonth', fmt(gp,1)); setText('batDischargeYear', fmt(gridNet,1)); setText('batDischargeTotal', fmt(gridNet,1));
  }
}

async function pollAllMeters() {
  const promises = meterAddrs.map(async addr => {
    const data = await getMeterRealtime(addr);
    if (data && data.data) { allMeterData[addr] = data; hasRealData = true; }
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

  // Poll real API
  startPolling(pollAllMeters, 5000);

  // Simulated data update every 2 seconds (like test2.vue dataTimer)
  setInterval(() => {
    if (!hasRealData) updateFlowLabels();
  }, 2000);

  // Initial simulated display
  setTimeout(updateFlowLabels, 500);
});
