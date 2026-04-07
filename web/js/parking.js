/**
 * Parking map — renders cars and charging piles on base map.
 * Matches D2Viewer.vue display logic from lizi project.
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

// 18 charging pile positions (left%, top%)
// Numbered from rightmost column, top-to-bottom, right-to-left:
//   col6(right): 1,2,3  col5: 4,5,6  col4: 7,8,9
//   col3: 10,11,12  col2: 13,14,15  col1(left): 16,17,18
const PILE_POSITIONS = [
  {id:16, left:6.03,  top:27.92}, {id:17, left:4.39,  top:41.85},
  {id:18, left:2.90,  top:57.78}, {id:13, left:29.52, top:27.82},
  {id:14, left:29.18, top:42.59}, {id:15, left:28.76, top:58.29},
  {id:10, left:35.35, top:27.78}, {id:11, left:35.04, top:42.36},
  {id:12, left:34.73, top:58.10}, {id:7,  left:55.46, top:27.73},
  {id:8,  left:56.08, top:42.41}, {id:9,  left:56.71, top:58.19},
  {id:4,  left:61.25, top:27.82}, {id:5,  left:62.02, top:42.31},
  {id:6,  left:62.70, top:58.01}, {id:1,  left:81.32, top:28.19},
  {id:2,  left:82.77, top:42.92}, {id:3,  left:84.34, top:59.03},
];

// Pile type by display ID: 17号,18号 are DC 120kW (physical pos 1,2), rest AC 7kW
function getPileTypeById(pileId) {
  return (pileId === 17 || pileId === 18) ? {type:'直流', power:'120kW'} : {type:'交流', power:'7kW'};
}

// State
let parkingData = {};   // {space_id: {status, label}}
let gunData = {};       // {gun_id: gun_object}
let pileData = {};      // {pile_id: pile_object}

// ---- Single car layer: one small car.png per occupied space ----
// No full-screen overlay images, no duplication, minimal resources
let carElements = {}; // reuse DOM elements

function renderCars() {
  const layer = document.getElementById('carsLayer');
  if (!layer) return;

  CAR_POSITIONS.forEach(pos => {
    const space = parkingData[pos.id];
    const occupied = space && space.status === 1;
    let el = carElements[pos.id];

    if (!el) {
      // Create once, reuse
      el = document.createElement('div');
      el.className = 'car-item';
      el.style.left = pos.left + '%';
      el.style.top = pos.top + '%';
      const img = document.createElement('img');
      img.src = '/images/car.png';
      img.alt = pos.id + '号';
      el.appendChild(img);
      el.addEventListener('click', (e) => showCarPopup(e, pos.id, parkingData[pos.id]));
      layer.appendChild(el);
      carElements[pos.id] = el;
    }

    // Toggle visibility
    el.style.opacity = occupied ? '1' : '0';
    el.style.pointerEvents = occupied ? 'auto' : 'none';
  });
}

// ---- Render charging piles (matches D2Viewer.vue .map-pile with UPageCard) ----
function renderPiles() {
  const layer = document.getElementById('pilesLayer');
  if (!layer) return;
  layer.innerHTML = '';

  PILE_POSITIONS.forEach((pos, idx) => {
    const pileType = getPileTypeById(pos.id);
    const isFree = isPileFree(pos.id);
    const statusClass = isFree ? 'free' : 'busy';

    const div = document.createElement('div');
    div.className = 'pile-label ' + statusClass;
    div.style.left = pos.left + '%';
    div.style.top = pos.top + '%';

    const bubble = document.createElement('div');
    bubble.className = 'pile-bubble ' + statusClass;

    const title = document.createElement('div');
    title.className = 'pile-title';
    title.textContent = pos.id + '号';

    bubble.appendChild(title);

    // Add gun status lines
    const gunLines = getGunLinesForPile(pos.id);
    gunLines.forEach(line => {
      const d = document.createElement('div');
      d.className = 'pile-info-line';
      d.textContent = line;
      bubble.appendChild(d);
    });

    // Default info if no gun data
    if (gunLines.length === 0) {
      const info = document.createElement('div');
      info.className = 'pile-info-line';
      info.textContent = pileType.type + '：' + pileType.power;
      bubble.appendChild(info);
    }

    div.appendChild(bubble);
    layer.appendChild(div);
  });
}

// Odoo pile ID -> display index mapping (populated from API)
let pileIdToIndex = {};

function isPileFree(pileIndex) {
  const guns = Object.values(gunData);
  let hasGun = false;
  for (const gun of guns) {
    if (gun.pile_id && gun.pile_id[0]) {
      const idx = pileIdToIndex[gun.pile_id[0]];
      if (idx === pileIndex) {
        hasGun = true;
        if (gun.status === '02') return true;
      }
    }
  }
  return !hasGun; // Default free if no gun matched
}

function getGunLinesForPile(pileIndex) {
  const lines = [];
  const guns = Object.values(gunData);
  const statusMap = {'02':'空闲','00':'离线','01':'故障','03':'充电'};
  for (const gun of guns) {
    if (gun.pile_id && gun.pile_id[0]) {
      const idx = pileIdToIndex[gun.pile_id[0]];
      if (idx === pileIndex) {
        const gunNum = gun.gun_number || '?';
        const gunLabel = {'01':'A','02':'B','1':'A','2':'B'}[gunNum] || gunNum;
        lines.push(gunLabel + '枪 ' + statusText);
        // Determine type from pile data
        const pile = pileData[gun.pile_id[0]];
        if (pile) {
          const pType = pile.pile_type === '00' ? '直流' : '交流';
          const pPower = pile.pile_type === '00' ? '120kW' : '7kW';
          lines.push(pType + '：' + pPower);
        }
        // Charging details — voltage, current, time, energy
        if (gun.status === '03') {
          if (gun.output_voltage || gun.output_current) {
            lines.push(gun.output_voltage + 'V ' + gun.output_current + 'A');
          }
          if (gun.total_charge_time) lines.push('时长:' + gun.total_charge_time + '分钟');
          if (gun.charge_degree) lines.push('电量:' + gun.charge_degree + '度');
        }
      }
    }
  }
  return lines;
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
    renderPiles();
  }
}

async function pollPiles() {
  const result = await getChargingPiles();
  if (result && result.result) {
    pileData = {};
    // Odoo pile IDs in physical position order (left-top to right-bottom)
    // from lizi source: ids=[2312,2240,2241,2313,...,2325,2326,2327]
    const positionIds = [2312,2240,2241,2313,2314,2315,2316,2317,2318,2319,2320,2321,2322,2323,2324,2325,2326,2327];
    // New display numbers per position (right-to-left, top-to-bottom):
    // position 0(左上)=16, 1=17, 2=18, 3=13, 4=14, 5=15, 6=10, 7=11, 8=12,
    // 9=7, 10=8, 11=9, 12=4, 13=5, 14=6, 15=1, 16=2, 17=3
    const posToDisplay = [16,17,18, 13,14,15, 10,11,12, 7,8,9, 4,5,6, 1,2,3];

    pileIdToIndex = {};
    result.result.forEach(p => { pileData[p.id] = p; });
    positionIds.forEach((id, posIdx) => {
      pileIdToIndex[id] = posToDisplay[posIdx];
    });
    // Map any unknown piles
    let nextIdx = 19;
    result.result.forEach(p => {
      if (!(p.id in pileIdToIndex)) { pileIdToIndex[p.id] = nextIdx++; }
    });
  }
}

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
  // Initial render with empty state
  renderCars();
  renderPiles();

  // Start polling
  startPolling(pollParking, 30000); // 30秒读一次车位
  startPolling(pollGuns, 30000);    // 30秒读一次充电枪
  pollPiles();

  // Close popup on outside click
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.car-item') &&
        !e.target.closest('.pile-label') &&
        !e.target.closest('.popup')) {
      hidePopup();
    }
  });
});
