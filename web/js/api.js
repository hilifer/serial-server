/**
 * API helper — fetch from Flask backend with polling support.
 */
const API_BASE = '';  // Same origin

async function fetchJSON(url) {
    try {
        const resp = await fetch(API_BASE + url);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.error('API error:', url, e);
        return null;
    }
}

// ---- Parking ----
async function getParkingStatus(zone) {
    const q = zone ? `?zone=${zone}` : '';
    return fetchJSON(`/parking/status${q}`);
}

async function getParkingSpace(id) {
    return fetchJSON(`/parking/space/${id}`);
}

async function getParkingSummary() {
    return fetchJSON('/parking/summary');
}

// ---- Meters ----
async function getMeters() {
    return fetchJSON('/meters');
}

async function getMeterRealtime(addr) {
    return fetchJSON(`/meter/${addr}/realtime`);
}

async function getMeterDaily(addr, daysAgo) {
    return fetchJSON(`/meter/${addr}/daily?days_ago=${daysAgo || 1}`);
}

async function getMeterMonthly(addr, monthsAgo) {
    return fetchJSON(`/meter/${addr}/monthly?months_ago=${monthsAgo || 1}`);
}

async function getMeterYearly(addr) {
    return fetchJSON(`/meter/${addr}/yearly`);
}

async function getMeterCurrentMonth(addr) {
    return fetchJSON(`/meter/${addr}/current_month`);
}

// ---- Charging (Odoo proxy) ----
async function getChargingPiles() {
    return fetchJSON('/charging/piles');
}

async function getChargingGuns() {
    return fetchJSON('/charging/guns');
}

// ---- System status ----
async function getSystemStatus() {
    return fetchJSON('/status');
}

// ---- Polling helper ----
function startPolling(fn, intervalMs) {
    fn(); // Run immediately
    const id = setInterval(fn, intervalMs);
    return () => clearInterval(id);
}
