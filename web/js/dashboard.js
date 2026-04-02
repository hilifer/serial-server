/**
 * Energy dashboard — fetches real meter data from Flask API.
 *
 * Meter address mapping:
 *   1: 电网侧 (ADL400)     → gridData
 *   2: 逆变侧 (ADL400)     → inverterData
 *   4: 用户负载 (ADL400)    → loadData
 *   5: 整流侧 (DJSF-RN6)   → storageData (rectifier side)
 *   6: 电池柜 (DJSF-RN)    → batteryData
 *   8: 直流充电桩1 (DJSF-RN) → chargeData1
 *   9: 直流充电桩2 (DJSF-RN) → chargeData2
 *  10: 光伏1 (DJSF-RN)      → solarData1
 *  11: 光伏2 (DJSF-RN)      → solarData2
 */

// ---- Clock ----
function updateDashClock() {
  const now = new Date();
  const el = document.getElementById('dashClock');
  const el2 = document.getElementById('dashDate');
  if (el) el.textContent = now.toLocaleTimeString('zh-CN', {hour12:false});
  if (el2) el2.textContent = now.toLocaleDateString('zh-CN', {year:'numeric',month:'long',day:'numeric',weekday:'long'});
  const ut = document.getElementById('updateTime');
  if (ut) ut.textContent = now.toLocaleTimeString('zh-CN', {hour12:false});
}

// ---- Helpers ----
function getVal(data, key) {
  if (!data || !data.data || !data.data[key]) return null;
  return data.data[key].value;
}

function fmt(v, decimals) {
  if (v === null || v === undefined) return '--';
  return Number(v).toFixed(decimals === undefined ? 1 : decimals);
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ---- Update left panel (Storage + Solar) ----
function updateStorage(rectifier, battery) {
  // Use rectifier (addr 5) for main DC bus data
  const v = getVal(rectifier, 'voltage');
  const i = getVal(rectifier, 'current');
  const p = getVal(rectifier, 'power');
  const t = getVal(rectifier, 'temperature');

  setText('storV', fmt(v) + 'V');
  setText('storI', fmt(i) + 'A');
  setText('storP', fmt(Math.abs(p)) + 'kW');
  setText('storV2', fmt(v) + 'V');
  setText('storI2', fmt(i) + 'A');

  // SOC estimation: not directly available, show battery energy ratio
  const fwd = getVal(battery, 'energy_forward_total');
  const rev = getVal(battery, 'energy_reverse_total');
  // Simple SOC proxy (placeholder until real BMS data)
  const soc = 80; // TODO: get from BMS if available
  setText('socValue', soc + '%');
  const arc = document.getElementById('socArc');
  if (arc) arc.setAttribute('stroke-dashoffset', 339.292 - (soc / 100) * 339.292);

  // Power item color
  const pEl = document.getElementById('storP');
  if (pEl) pEl.className = 'val' + (p < 0 ? ' negative' : '');
}

function updateSolar(solar1, solar2) {
  // Combine two solar meters
  const v1 = getVal(solar1, 'voltage') || 0;
  const i1 = getVal(solar1, 'current') || 0;
  const p1 = getVal(solar1, 'power') || 0;
  const t1 = getVal(solar1, 'temperature');

  const v2 = getVal(solar2, 'voltage') || 0;
  const p2 = getVal(solar2, 'power') || 0;

  const totalP = Math.abs(p1) + Math.abs(p2);
  setText('solarP', fmt(totalP));
  setText('solarV', fmt(v1) + 'V');
  setText('solarI', fmt(Math.abs(i1)) + 'A');
  setText('solarT', t1 !== null ? fmt(t1) + '°C' : '--');
  setText('solarV2', fmt(v1) + 'V');
  setText('solarI2', fmt(Math.abs(i1)) + 'A');
}

// ---- Update center panel (Flow diagram) ----
function updateGrid(grid) {
  const v = getVal(grid, 'voltage_a');
  const i = getVal(grid, 'current_a');
  const p = getVal(grid, 'power_total');
  setText('gridV', fmt(v) + 'V');
  setText('gridI', fmt(i) + 'A');
  setText('gridP', fmt(p) + 'kW');
}

function updateCharging(c1, c2) {
  const v1 = getVal(c1, 'voltage') || 0;
  const i1 = getVal(c1, 'current') || 0;
  const p1 = getVal(c1, 'power') || 0;
  const p2 = getVal(c2, 'power') || 0;
  setText('chargeV', fmt(v1) + 'V');
  setText('chargeI', fmt(Math.abs(i1)) + 'A');
  setText('chargeP', fmt(Math.abs(p1) + Math.abs(p2)) + 'kW');
}

function updateLoad(load) {
  const v = getVal(load, 'voltage_a');
  const i = getVal(load, 'current_a');
  setText('loadV', fmt(v) + 'V');
  setText('loadI', fmt(i) + 'A');
}

// ---- Update right panel (Meter list + System status) ----
function updateMeterList(allData) {
  const list = document.getElementById('meterList');
  if (!list) return;

  const meterNames = {
    1: '电网侧', 2: '逆变侧', 3: '交流桩', 4: '用户负载',
    5: '整流侧', 6: '电池柜', 8: '充电桩1', 9: '充电桩2',
    10: '光伏1', 11: '光伏2'
  };

  let html = '';
  for (const [addr, name] of Object.entries(meterNames)) {
    const d = allData[addr];
    const online = d && d.data;
    const icon = online ? '✓' : '✗';
    const cls = online ? 'good' : 'warn';

    let info = '离线';
    if (online) {
      // Show key value based on meter type
      if (Number(addr) <= 4) {
        const p = getVal(d, 'power_total');
        info = p !== null ? fmt(p) + 'kW' : '在线';
      } else {
        const p = getVal(d, 'power');
        info = p !== null ? fmt(p) + 'kW' : '在线';
      }
    }

    html += `<div class="status-row">
      <div class="status-icon ${cls}">${icon}</div>
      <span class="status-name">[${addr}] ${name}</span>
      <span class="status-val">${info}</span>
    </div>`;
  }
  list.innerHTML = html;
}

function updateSystemStatus() {
  getSystemStatus().then(data => {
    const el = document.getElementById('sysStatus');
    if (!el || !data || !data.ports) return;

    let html = '';
    for (const [name, info] of Object.entries(data.ports)) {
      const ok = info.status === 'connected';
      html += `<div class="status-row">
        <div class="status-icon ${ok ? 'good' : 'warn'}">${ok ? '✓' : '!'}</div>
        <span class="status-name">${name}</span>
        <span class="status-val">${ok ? '已连接' : info.last_error || '断开'}</span>
      </div>`;
    }
    el.innerHTML = html;
  });
}

// ---- Update charging pile grid ----
function updatePileGrid() {
  getChargingGuns().then(data => {
    const grid = document.getElementById('pileGrid');
    if (!grid) return;

    // Simple 8-pile display
    const piles = [];
    for (let i = 1; i <= 8; i++) {
      piles.push({num: i, free: Math.random() > 0.4}); // TODO: real data from Odoo
    }

    let free = 0, busy = 0;
    let html = '';
    piles.forEach(p => {
      const cls = p.free ? 'free' : 'busy';
      if (p.free) free++; else busy++;
      html += `<div class="pile-cell ${cls}">
        <div class="pile-num">${p.num}</div>
        <div class="pile-status ${cls}">${p.free ? '空闲' : '占用'}</div>
      </div>`;
    });
    grid.innerHTML = html;

    setText('mapFree', free);
    setText('mapBusy', busy);
  });
}

// ---- Solar generation estimate ----
function updateTodayGen(solar1, solar2) {
  const p1 = Math.abs(getVal(solar1, 'power') || 0);
  const p2 = Math.abs(getVal(solar2, 'power') || 0);
  // Rough estimate: current power × hours of daylight so far
  const hour = new Date().getHours();
  const sunHours = Math.max(0, Math.min(hour - 6, 12));
  const est = (p1 + p2) * sunHours * 0.6; // capacity factor
  setText('todayGen', fmt(est, 0));
}

// ---- Main polling loop ----
const meterAddrs = [1, 2, 4, 5, 6, 8, 9, 10, 11];
let allMeterData = {};

async function pollAllMeters() {
  const promises = meterAddrs.map(async addr => {
    const data = await getMeterRealtime(addr);
    if (data) allMeterData[addr] = data;
  });
  await Promise.all(promises);

  // Update all panels
  updateGrid(allMeterData[1]);
  updateStorage(allMeterData[5], allMeterData[6]);
  updateSolar(allMeterData[10], allMeterData[11]);
  updateCharging(allMeterData[8], allMeterData[9]);
  updateLoad(allMeterData[4]);
  updateMeterList(allMeterData);
  updateTodayGen(allMeterData[10], allMeterData[11]);

  const alert = document.getElementById('alertMsg');
  if (alert) {
    const t5 = getVal(allMeterData[5], 'temperature');
    if (t5 && t5 > 40) {
      alert.textContent = '⚠️ 整流侧温度偏高: ' + fmt(t5) + '°C';
    } else {
      alert.textContent = '';
    }
  }
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  updateDashClock();
  setInterval(updateDashClock, 1000);

  // Poll meters every 5 seconds
  startPolling(pollAllMeters, 5000);

  // System status every 10 seconds
  startPolling(updateSystemStatus, 10000);

  // Pile grid every 5 seconds
  startPolling(updatePileGrid, 5000);
});
