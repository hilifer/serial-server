# 光储充管理系统 API 文档

后端是个 Flask HTTP 服务，监听本机所有网卡的 8000 端口。Web 前端、其它机器、PLC、移动 App、Postman 等都可以直接调。所有接口返回 JSON。

---

## 0. 局域网访问

### 服务器侧

服务器进程在 `server.py` 启动时已经绑定到 `0.0.0.0:8000`（不是 `127.0.0.1`），意思是**任何网卡都能接进来**。同时已经为所有响应加上 CORS 头：

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: *
```

所以跨域 fetch / AJAX 不会被浏览器拦。

### 访问 URL

把 `localhost` 换成**服务器所在机器的局域网 IP**。例如服务器 IP 是 `192.168.1.50`，那同一局域网下任意机器：

```
http://192.168.1.50:8000/meters
http://192.168.1.50:8000/meter/1/realtime
…
```

服务器 IP 查法（Windows）：`ipconfig` 看 IPv4 地址。

### Windows 防火墙

第一次访问如果连不上，多半是防火墙拦了。开一条入站规则：

```
netsh advfirewall firewall add rule name="serial-server-api" ^
  dir=in action=allow protocol=TCP localport=8000
```

或者控制面板 → Windows Defender 防火墙 → 高级设置 → 入站规则 → 新建规则 → 端口 → TCP 8000 → 允许。

---

## 1. 系统状态

### GET /status

串口/端口状态。

```json
{
  "ports": {
    "COM31": { "is_open": true, "last_error": null, ... },
    "COM32": { ... },
    "COM33": { ... }
  }
}
```

### GET /meters

电表列表（配置中的所有电表）。

```json
[
  { "address": 1,  "name": "电网侧电表",   "model": "ADL400",        "type": "AC", "location": "01柜", "note": null },
  { "address": 2,  "name": "逆变侧电表",   "model": "ADL400",        "type": "AC", "location": "05柜" },
  ...
  { "address": 10, "name": "光伏1",        "model": "DJSF1352-RN",   "type": "DC", "location": "03柜" }
]
```

---

## 2. 电表数据

电表地址：1=电网、2=逆变、3=交流桩、4=用户负载、5=整流侧、6=电池柜、8=直流桩1、9=直流桩2、10=光伏1、11=光伏2。
> 注意：没有 7。

### GET /meter/{addr}/realtime

实时数据。**经过 MeterCache，<1ms 返回**。

ADL400（addr 1-4）字段：

```json
{
  "address": 1, "name": "电网侧电表", "model": "ADL400",
  "data": {
    "voltage_a":   { "value": 220.5, "unit": "V" },
    "voltage_b":   { "value": 220.3, "unit": "V" },
    "voltage_c":   { "value": 220.8, "unit": "V" },
    "current_a":   { "value": 5.12,  "unit": "A" },
    "current_b":   { "value": 5.34,  "unit": "A" },
    "current_c":   { "value": 5.21,  "unit": "A" },
    "power_a":     { "value": 1.12,  "unit": "kW" },
    "power_b":     { "value": 1.17,  "unit": "kW" },
    "power_c":     { "value": 1.15,  "unit": "kW" },
    "power_total": { "value": 3.44,  "unit": "kW" },
    "reactive_power_total": { "value": 0.22, "unit": "kvar" },
    "apparent_power_total": { "value": 3.45, "unit": "kVA" },
    "energy_forward_total": { "value": 12345.6, "unit": "kWh" },
    "energy_reverse_total": { "value": 0.0,     "unit": "kWh" }
  },
  "cache_age_s": 1.2,
  "last_error": null
}
```

DJSF1352-RN(-6)（addr 5,6,8,9,10,11）字段：

```json
{
  "address": 6, "name": "电池柜电表", "model": "DJSF1352-RN",
  "data": {
    "voltage": { "value": 240.5, "unit": "V" },
    "current": { "value": 12.3,  "unit": "A" },
    "power":   { "value": 2.95,  "unit": "kW" },
    "temperature": { "value": 35.2, "unit": "°C" },
    "energy_forward_total": { "value": 1234.5, "unit": "kWh" },
    "energy_reverse_total": { "value": 567.8,  "unit": "kWh" }
  },
  "current_month": {
    "energy_forward_kwh": 12.3,
    "energy_reverse_kwh": 4.5
  },
  "cache_age_s": 0.8,
  "last_error": null
}
```

字段说明：
- `value`：null 表示读取失败
- `power` 的正负代表方向（正=流入，负=流出）
- `cache_age_s`：缓存数据年龄秒
- `last_error`：上次缓存刷新出错的信息（成功则为 null）

### GET /meter/{addr}/daily?days_ago=N

冻结的日电量数据。`days_ago` 范围 1-90。

### GET /meter/{addr}/monthly?months_ago=N

冻结的月电量数据。
- ADL400: `months_ago` 1-48
- DJSF: `months_ago` 1-12

### GET /meter/{addr}/current_month

当月累计电量（不是冻结，实时累加）。仅 DJSF 支持，ADL400 调会返回 400。

```json
{
  "address": 6, "name": "电池柜电表",
  "current_month": {
    "energy_forward_kwh": 12.345,
    "energy_reverse_kwh": 4.567
  }
}
```

### GET /meter/{addr}/yearly

年电量汇总。**经过 YearlyCache，每小时刷新一次**。

```json
{
  "address": 8, "name": "直流充电桩1",
  "months": [
    { "month": 1, "is_this_year": true, "energy_forward_kwh": 123.4, "energy_reverse_kwh": 0.0 },
    { "month": 2, "is_this_year": true, "energy_forward_kwh": 234.5, "energy_reverse_kwh": 0.0 },
    ...
  ],
  "total_forward_kwh": 1234.5,
  "total_reverse_kwh": 0.0,
  "cache_age_s": 320.5,
  "last_error": null
}
```

`is_this_year`: 该月数据是不是本年的（避免去年同月数据混入）。

---

## 3. 电池 SOC（BMS）

### GET /battery/soc

读 BMS 电池荷电状态。Modbus TCP，缓存 5 秒。

```json
{ "ok": true, "soc_pct": 78 }
```

错误：
- 503 `BMS 未配置`：config.yaml 里没有 `bms` 段
- 503 `BMS 不可达`：网络/设备问题

---

## 4. 充电桩（代理 Odoo）

### GET /charging/piles

充电桩列表。直接返回 Odoo 原始 list（5 秒 TTL 缓存）。

```json
{
  "result": [
    {
      "id": 2312,
      "name": "1号桩",
      "pile_code": "P001",
      "pile_type": "01",      // "00"=直流 "01"=交流
      "gun_count": 2,
      "status": "01",
      "gun_ids": [...],
      "description": "..."
    },
    ...
  ]
}
```

### GET /charging/guns

充电枪列表（含实时状态）。5 秒 TTL 缓存。

```json
{
  "result": [
    {
      "id": 12345,
      "gun_code": "G001A",
      "gun_number": "01",          // "01"=A枪 "02"=B枪
      "gun_type": "AC",
      "status": "02",              // "00"=离线 "01"=故障 "02"=空闲 "03"=充电
      "pile_id": [2312, "1号桩"],
      "output_voltage": 220,
      "output_current": 15,
      "total_charge_time": 30,     // 分钟
      "charge_degree": 5.2         // 度
    },
    ...
  ]
}
```

---

## 5. 停车位

54 个车位：1-27 在 A 区（COM31），28-54 在 B 区（COM32）。

### GET /parking/spaces

车位静态信息列表。

```json
[
  { "space_id": 1, "com_port": "COM31", "slave_addr": 1, "zone": "A" },
  ...
]
```

### GET /parking/status[?zone=A|B]

实时状态。**ParkingCache，<1ms**。

```json
{
  "total": 54, "online": 52, "occupied": 23, "empty": 29,
  "spaces": [
    { "space_id": 1,  "zone": "A", "status": 0, "label": "empty" },
    { "space_id": 2,  "zone": "A", "status": 1, "label": "occupied" },
    { "space_id": 28, "zone": "B", "status": null, "label": "offline" },
    ...
  ]
}
```

`status`: `0`=空 `1`=有车 `null`=离线/无响应。

### GET /parking/summary

按区汇总。

```json
{
  "A": { "total": 27, "occupied": 11, "empty": 14, "offline": 2 },
  "B": { "total": 27, "occupied": 12, "empty": 15, "offline": 0 }
}
```

### GET /parking/space/{space_id}

某个车位的全部 8 个寄存器（不只是状态，还包括 LED 颜色、显示模式等）。

```json
{
  "space_id": 5, "zone": "A", "com_port": "COM31", "slave_addr": 5,
  "data": {
    "status": 1,
    "display_mode": 0,
    "color": 2,
    ...
  }
}
```

### POST /parking/space/{space_id}/display_mode

设置显示模式。Body JSON：

```json
{ "mode": 0 }
```

`mode` 取值 0-5。返回：

```json
{ "success": true, "mode": 0, "label": "..." }
```

### POST /parking/space/{space_id}/color

设置 LED 颜色。Body JSON：

```json
{ "color": 2 }
```

`color` 取值 0-7。

---

## 6. 错误返回

所有错误统一格式：

```json
{ "error": "错误描述" }
```

常见 HTTP 状态码：

| 状态 | 含义 |
|---|---|
| 400 | 参数错误（如 `days_ago` 超范围） |
| 404 | 资源不存在（电表地址或车位 ID 没注册） |
| 500 | 服务端内部错误（串口未初始化等） |
| 502 | 设备响应解析失败（CRC / 帧错误） |
| 503 | 服务不可用（串口断开 / BMS 不可达） |
| 504 | 设备无响应（超时） |

---

## 7. 调用示例

### curl

```bash
# 列出所有电表
curl http://192.168.1.50:8000/meters

# 读电表 1 的实时数据
curl http://192.168.1.50:8000/meter/1/realtime

# 设置车位 5 的 LED 颜色为 2
curl -X POST -H "Content-Type: application/json" \
     -d '{"color": 2}' \
     http://192.168.1.50:8000/parking/space/5/color
```

### Python (requests)

```python
import requests
r = requests.get("http://192.168.1.50:8000/meter/6/realtime")
data = r.json()
print(data["data"]["power"]["value"])
```

### JavaScript (fetch)

```js
const r = await fetch("http://192.168.1.50:8000/parking/status");
const data = await r.json();
console.log(`占用: ${data.occupied}, 空闲: ${data.empty}`);
```

---

## 8. 性能特性

| 接口 | 缓存 | 响应时间 |
|---|---|---|
| `/meter/{addr}/realtime` | MeterCache 2 秒扫描 | <1 ms |
| `/meter/{addr}/yearly` | YearlyCache 1 小时扫描 | <1 ms |
| `/parking/status` | ParkingCache 2 秒扫描 | <1 ms |
| `/charging/piles` `/charging/guns` | OdooCache 5 秒 TTL | ~50 ms（缓存命中）/ ~500 ms（穿透 Odoo） |
| `/battery/soc` | BMS 5 秒 TTL | <1 ms（缓存）/ ~100 ms（实读） |
| `/meter/{addr}/daily` `/monthly` `/current_month` | **无缓存**，直读串口 | ~200-2000 ms |
| `/parking/space/{id}/...` | **无缓存**，直读串口 | ~200-500 ms |

带缓存的接口可以高频调（毫秒级），不带缓存的避免在前端 setInterval 里频繁调，会把串口锁死。
