/**
 * Parking map — renders cars and charging piles on base map.
 * Positions extracted from lizi/public/images/car/*.png using Pillow.
 */

// 54 car center positions (left%, top%) — pixel-accurate from PNG extraction
const CAR_POSITIONS = [
  {id:1,  left:11.77, top:29.17}, {id:2,  left:11.48, top:32.80},
  {id:3,  left:11.20, top:36.57}, {id:4,  left:10.66, top:43.54},
  {id:5,  left:10.36, top:47.48}, {id:6,  left:10.05, top:51.53},
  {id:7,  left:9.47,  top:59.12}, {id:8,  left:9.15,  top:63.33},
  {id:9,  left:8.82,  top:67.73}, {id:10, left:27.42, top:29.10},
  {id:11, left:27.30, top:32.80}, {id:12, left:27.16, top:36.50},
  {id:13, left:26.91, top:43.52}, {id:14, left:26.78, top:47.50},
  {id:15, left:26.63, top:51.48}, {id:16, left:26.35, top:59.03},
  {id:17, left:26.21, top:63.31}, {id:18, left:26.05, top:67.64},
  {id:19, left:37.70, top:29.05}, {id:20, left:37.66, top:32.71},
  {id:21, left:37.62, top:36.46}, {id:22, left:37.55, top:43.43},
  {id:23, left:37.53, top:47.34}, {id:24, left:37.49, top:51.39},
  {id:25, left:37.42, top:58.94}, {id:26, left:37.40, top:63.17},
  {id:27, left:37.34, top:67.57}, {id:28, left:53.10, top:29.00},
  {id:29, left:53.22, top:32.71}, {id:30, left:53.33, top:36.41},
  {id:31, left:53.55, top:43.40}, {id:32, left:53.67, top:47.38},
  {id:33, left:53.80, top:51.37}, {id:34, left:54.02, top:58.87},
  {id:35, left:54.17, top:63.17}, {id:36, left:54.30, top:67.45},
  {id:37, left:63.33, top:28.96}, {id:38, left:63.54, top:32.59},
  {id:39, left:63.76, top:36.37}, {id:40, left:64.15, top:43.31},
  {id:41, left:64.38, top:47.20}, {id:42, left:64.61, top:51.27},
  {id:43, left:65.04, top:58.80}, {id:44, left:65.29, top:63.03},
  {id:45, left:65.55, top:67.41}, {id:46, left:78.62, top:28.91},
  {id:47, left:78.97, top:32.62}, {id:48, left:79.34, top:36.30},
  {id:49, left:80.03, top:43.29}, {id:50, left:80.42, top:47.25},
  {id:51, left:80.79, top:51.23}, {id:52, left:81.52, top:58.70},
  {id:53, left:81.95, top:62.99}, {id:54, left:82.36, top:67.29},
];

// 18 charging pile positions (left%, top%) — from zhuang/*.png extraction
const PILE_POSITIONS = [
  {id:1,  left:6.03,  top:27.92}, {id:2,  left:4.39,  top:41.85},
  {id:3,  left:2.90,  top:57.78}, {id:4,  left:29.52, top:27.82},
  {id:5,  left:29.18, top:42.59}, {id:6,  left:28.76, top:58.29},
  {id:7,  left:35.35, top:27.78}, {id:8,  left:35.04, top:42.36},
  {id:9,  left:34.73, top:58.10}, {id:10, left:55.46, top:27.73},
  {id:11, left:56.08, top:42.41}, {id:12, left:56.71, top:58.19},
  {id:13, left:61.25, top:27.82}, {id:14, left:62.02, top:42.31},
  {id:15, left:62.70, top:58.01}, {id:16, left:81.32, top:28.19},
  {id:17, left:82.77, top:42.92}, {id:18, left:84.34, top:59.03},
];

// Pile type: piles 2,3 are DC 120kW, rest are AC 7kW
function getPileType(index) {
  return (index === 1 || index === 2) ? {type:'直流', power:'120kW'} : {type:'交流', power:'7kW'};
}

// State
let parkingData = {};   // {space_id: {status, label}}
let gunData = {};       // {gun_id: gun_object}
let pileData = {};      // {pile_id: pile_object}
let activePopup = null;

// ---- Render cars ----
function renderCars() {
  const layer = document.getElementById('carsLayer');
  if (!layer) return;
  layer.innerHTML = '';

  CAR_POSITIONS.forEach(pos => {
    const space = parkingData[pos.id];
    const occupied = space && space.status === 1;

    const div = document.createElement('div');
    div.className = 'car-item ' + (occupied ? 'occupied' : 'empty');
    div.style.left = pos.left + '%';
    div.style.top = pos.top + '%';
    div.dataset.spaceId = pos.id;

    const img = document.createElement('img');
    img.src = '/images/car.png';
    img.alt = pos.id + '号车位';
    img.loading = 'lazy';
    div.appendChild(img);

    div.addEventListener('click', (e) => showCarPopup(e, pos.id, space));
    layer.appendChild(div);
  });
}

// ---- Render charging piles ----
function renderPiles() {
  const layer = document.getElementById('pilesLayer');
  if (!layer) return;
  layer.innerHTML = '';

  PILE_POSITIONS.forEach((pos, idx) => {
    const pileType = getPileType(idx);
    const isFree = isPileFree(pos.id);

    const div = document.createElement('div');
    div.className = 'pile-label';
    div.style.left = pos.left + '%';
    div.style.top = pos.top + '%';

    const bubble = document.createElement('div');
    bubble.className = 'pile-bubble ' + (isFree ? 'free' : 'busy');

    const title = document.createElement('div');
    title.className = 'pile-title';
    title.textContent = pos.id + '号';

    const info = document.createElement('div');
    info.className = 'pile-info-line';
    info.textContent = pileType.power + ' ' + pileType.type + '充电桩';

    // Add gun status lines
    const gunLines = getGunLinesForPile(pos.id);
    bubble.appendChild(title);
    bubble.appendChild(info);
    gunLines.forEach(line => {
      const d = document.createElement('div');
      d.className = 'pile-info-line';
      d.textContent = line;
      bubble.appendChild(d);
    });

    div.appendChild(bubble);
    div.addEventListener('click', (e) => showPilePopup(e, pos.id));
    layer.appendChild(div);
  });
}

function isPileFree(pileIndex) {
  // Check if any gun of this pile has status '02' (idle)
  const guns = Object.values(gunData);
  for (const gun of guns) {
    if (gun.pile_id && gun.pile_id[0] && matchPileIndex(gun.pile_id[0], pileIndex)) {
      if (gun.status === '02') return true;
    }
  }
  return guns.length === 0; // Default free if no gun data
}

function matchPileIndex(pileId, index) {
  // Map Odoo pile IDs to display indices (simplified)
  return true; // Will be refined when Odoo data is available
}

function getGunLinesForPile(pileIndex) {
  // Return status lines for guns belonging to this pile
  return [];
}

// ---- Popup for car ----
function showCarPopup(event, spaceId, space) {
  hidePopup();
  const popup = document.getElementById('popup');
  const content = document.getElementById('popupContent');
  const occupied = space && space.status === 1;
  const statusClass = occupied ? 'occupied' : 'empty';
  const statusText = occupied ? '占用' : '空闲';

  content.innerHTML = `
    <span class="close-btn" onclick="hidePopup()">&times;</span>
    <div class="popup-title">${spaceId}号车位</div>
    <div class="popup-row">
      <span class="lbl">车位状态：</span>
      <span class="status-tag ${statusClass}">${statusText}</span>
    </div>
  `;

  popup.style.display = 'block';
  positionPopup(popup, event);
}

function showPilePopup(event, pileId) {
  hidePopup();
  const popup = document.getElementById('popup');
  const content = document.getElementById('popupContent');
  const pt = getPileType(pileId - 1);

  content.innerHTML = `
    <span class="close-btn" onclick="hidePopup()">&times;</span>
    <div class="popup-title">${pileId}号充电桩</div>
    <div class="popup-row"><span class="lbl">类型：</span><span class="val">${pt.type} ${pt.power}</span></div>
  `;

  popup.style.display = 'block';
  positionPopup(popup, event);
}

function positionPopup(popup, event) {
  const x = event.clientX + 15;
  const y = event.clientY - 10;
  popup.style.left = Math.min(x, window.innerWidth - 250) + 'px';
  popup.style.top = Math.min(y, window.innerHeight - 200) + 'px';
}

function hidePopup() {
  const popup = document.getElementById('popup');
  if (popup) popup.style.display = 'none';
}

// ---- Update footer stats ----
function updateFooter(parkResult) {
  if (!parkResult) return;
  document.getElementById('parkFree').textContent = parkResult.empty || 0;
  document.getElementById('parkOccupied').textContent = parkResult.occupied || 0;
}

function updatePileFooter() {
  const guns = Object.values(gunData);
  const free = guns.filter(g => g.status === '02').length;
  const busy = guns.length - free;
  document.getElementById('pilesFree').textContent = free || '-';
  document.getElementById('pilesBusy').textContent = busy || '-';
}

// ---- Clock ----
function updateClock() {
  const now = new Date();
  const el = document.getElementById('clock');
  if (el) {
    el.textContent = now.toLocaleString('zh-CN', {
      year:'numeric', month:'2-digit', day:'2-digit',
      hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
    });
  }
}

// ---- Data polling ----
async function pollParking() {
  const result = await getParkingStatus();
  if (result && result.spaces) {
    parkingData = {};
    result.spaces.forEach(s => { parkingData[s.space_id] = s; });
    renderCars();
    updateFooter(result);
  }
}

async function pollGuns() {
  const result = await getChargingGuns();
  if (result && result.result) {
    gunData = {};
    result.result.forEach(g => { gunData[g.id] = g; });
    renderPiles();
    updatePileFooter();
  } else {
    renderPiles(); // Render with default state
  }
}

async function pollPiles() {
  const result = await getChargingPiles();
  if (result && result.result) {
    pileData = {};
    result.result.forEach(p => { pileData[p.id] = p; });
  }
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  updateClock();
  setInterval(updateClock, 1000);

  // Initial render with empty state
  renderCars();
  renderPiles();

  // Start polling
  startPolling(pollParking, 3000);
  startPolling(pollGuns, 5000);
  pollPiles(); // One-time load

  // Close popup on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.car-item') &&
        !e.target.closest('.pile-label') &&
        !e.target.closest('.popup')) {
      hidePopup();
    }
  });
});
