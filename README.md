# MQTT WebSocket Serial Server + Meter API

统一服务：MQTT WebSocket 串口透传 + 电表数据 REST API，单进程运行，共享串口锁。

## 架构

```
                         ┌──────────────────────────────┐
  REST API ─────────────>│                              │
  http://localhost:8000  │    server.py (统一进程)        │
  /meters, /meter/...    │                              │
                         │    serial_managers (共享)      │
  MQTT WS ──────────────>│    ┌──────────────────────┐  │
  serial/comXX/up|down   │    │ COM31 SerialMgr [锁] │──┼──── COM31 (透传)
                         │    │ COM32 SerialMgr [锁] │──┼──── COM32 (透传)
                         │    │ COM33 SerialMgr [锁] │──┼──── COM33 (电表+透传)
                         │    └──────────────────────┘  │
                         └──────────────────────────────┘
```

- **MQTT WS 透传**：COM31/COM32/COM33 双向透明传输
- **REST API**：COM33 上 8 块电表的实时/日/月/年数据查询
- **共享锁**：同一串口的所有操作（透传 + API）通过 RLock 互斥，不会冲突

## 电表配置 (COM33)

| 地址 | 名称 | 型号 | 类型 | 位置 | 备注 |
|------|------|------|------|------|------|
| 1 | 电网侧电表 | ADL400 | AC | 01柜 | |
| 2 | 逆变侧电表 | ADL400 | AC | 05柜 | |
| 3 | 交流桩电表 | ADL400 | AC | 05柜 | |
| 4 | 用户负载电表 | ADL400 | AC | 05柜 | |
| 5 | 整流侧电表 | DJSF1352-RN-6 | DC | 03柜 | 1路 |
| 6 | 电池柜电表 | DJSF1352-RN | DC | 03柜 | |
| 7 | 直流桩电表 | DJSF1352-RN | DC | 03柜 | 2路 |
| 8 | 光伏电表 | DJSF1352-RN | DC | 03柜 | 2路 |

## MQTT 主题说明

| 串口 | 上行（串口→MQTT） | 下行（MQTT→串口） |
|------|-------------------|-------------------|
| COM31 | `serial/com31/up` | `serial/com31/down` |
| COM32 | `serial/com32/up` | `serial/com32/down` |
| COM33 | `serial/com33/up` | `serial/com33/down` |

## REST API 接口

| 接口 | 说明 |
|------|------|
| `GET /meters` | 列出所有电表 |
| `GET /meter/{addr}/realtime` | 实时数据（电压/电流/功率/电能） |
| `GET /meter/{addr}/daily?days_ago=1` | 日冻结数据（ADL400，最多90天） |
| `GET /meter/{addr}/monthly?months_ago=1` | 月冻结数据 |
| `GET /meter/{addr}/yearly` | 年汇总（累加12个月） |
| `GET /docs` | Swagger 交互式文档 |

## 环境要求

- Python 3.10+（已测试 Python 3.15.0a7）
- MQTT Broker 需启用 WebSocket 监听（默认端口 9001）
- 推荐 Broker：[Mosquitto](https://mosquitto.org/)、[EMQX](https://www.emqx.io/)

### Mosquitto WebSocket 配置

在 `mosquitto.conf` 中添加：

```
listener 1883
protocol mqtt

listener 9001
protocol websockets
allow_anonymous true
```

重启：

```bash
# Windows
net stop mosquitto && net start mosquitto

# Linux
sudo systemctl restart mosquitto
```

## 快速开始

### 首次部署

```bash
# 1. 克隆代码
git clone <仓库地址> serial-server
cd serial-server

# 2. 切换到开发分支
git checkout claude/mqtt-ws-serial-server-PEtRp

# 3. 一键启动（自动创建虚拟环境、安装依赖、启动服务）
# Windows:
start.bat
# Linux:
chmod +x start.sh
./start.sh
```

### 更新代码并重启

```bash
# 方式1：一键启动脚本（自带 git pull）
# Windows:
start.bat
# Linux:
./start.sh

# 方式2：手动更新
git pull origin claude/mqtt-ws-serial-server-PEtRp
source venv/bin/activate          # Linux
# 或: venv\Scripts\activate       # Windows
pip install -r requirements.txt
python server.py
```

### 手动逐步启动

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux:
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动统一服务（MQTT WS + API 同时运行）
python server.py
```

启动后：
- MQTT WS 透传自动连接 Broker 并开始工作
- REST API 在 `http://0.0.0.0:8000` 提供服务
- Swagger 文档在 `http://localhost:8000/docs`

## 配置说明

编辑 `config.yaml`：

```yaml
mqtt:
  broker: "localhost"       # MQTT Broker 地址
  port: 1883                # MQTT TCP 端口
  ws_port: 9001             # MQTT WebSocket 端口
  username: ""              # 认证用户名（留空不认证）
  password: ""              # 认证密码
  client_id_prefix: "serial-server"
  keepalive: 60

serial_ports:
  - name: "COM31"
    port: "COM31"           # Windows: COM31, Linux: /dev/ttyUSB0
    baudrate: 9600          # 波特率
    bytesize: 8             # 数据位
    parity: "N"             # 校验位: N/E/O
    stopbits: 1             # 停止位
    timeout: 0.1            # 读超时（秒）
    mqtt_topic_prefix: "serial/com31"

logging:
  level: "INFO"             # DEBUG/INFO/WARNING/ERROR
  file: "serial_server.log"
```

### Linux 串口映射

```yaml
serial_ports:
  - name: "COM31"
    port: "/dev/ttyUSB0"
  - name: "COM32"
    port: "/dev/ttyUSB1"
  - name: "COM33"
    port: "/dev/ttyUSB2"
```

串口权限：

```bash
sudo usermod -a -G dialout $USER
# 重新登录生效
```

## 测试

### 一键运行所有测试

```bash
# Windows:
run_test.bat

# Linux:
./run_test.sh
```

包含：单元测试（120个） + 电表硬件通信测试。

### 仅运行单元测试

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

### 仅运行电表硬件测试

```bash
# 测试全部电表
python test_meter_live.py

# 测试指定电表
python test_meter_live.py --addr 1,5

# 指定串口
python test_meter_live.py --port COM33 --baudrate 9600
```

## 客户端测试

### MQTT CLI 测试

```bash
# 订阅 COM31 上行
mosquitto_sub -h localhost -p 9001 --ws -t "serial/com31/up" -v

# 向 COM31 发送
mosquitto_pub -h localhost -p 9001 --ws -t "serial/com31/down" -m "Hello"
```

### API 测试 (curl)

```bash
# 列出所有电表
curl http://localhost:8000/meters

# 读取地址1电表实时数据
curl http://localhost:8000/meter/1/realtime

# 读取昨天日数据
curl http://localhost:8000/meter/1/daily?days_ago=1

# 读取上月数据
curl http://localhost:8000/meter/1/monthly?months_ago=1

# 读取年汇总
curl http://localhost:8000/meter/1/yearly
```

### JavaScript (浏览器) 测试

```html
<script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
<script>
const client = mqtt.connect('ws://localhost:9001');
client.on('connect', () => {
  client.subscribe('serial/com31/up');
  client.publish('serial/com31/down', 'Hello from browser');
});
client.on('message', (topic, msg) => console.log(`${topic}: ${msg}`));
</script>
```

## 项目结构

```
serial-server/
├── server.py              # 统一入口（MQTT WS + API）
├── serial_manager.py      # 共享串口管理器（RLock 保护）
├── meter.py               # 电表 Modbus RTU 协议
├── meter_api.py           # REST API 路由 (FastAPI)
├── config.yaml            # 配置文件
├── requirements.txt       # Python 依赖
├── start.bat / start.sh   # 一键启动（含 git pull）
├── run_test.bat / .sh     # 一键测试
├── test_meter_live.py     # 电表硬件测试脚本
├── docs/                  # 电表协议文档
│   ├── ADL400_*.pdf
│   ├── DJSF1352-RN_*.pdf
│   ├── 537_DJSF1352-RN-6_*.pdf
│   └── mmexport*.webp     # 电表地址表图片
└── tests/                 # 单元测试 (120个)
    ├── test_server.py
    ├── test_meter.py
    └── test_serial_manager.py
```

## 常见问题

**Q: MQTT Broker 连接失败？**
- 确认 Broker 已启动并监听 WS 端口 9001
- 检查防火墙是否放行
- 如需认证，在 `config.yaml` 配置 `username`/`password`
- 即使 MQTT 连接失败，API 服务仍会正常运行

**Q: 串口打开失败？**
- 确认串口设备存在：Windows 设备管理器，Linux `ls /dev/ttyUSB*`
- 确认无其他程序占用
- Linux 确认用户在 `dialout` 组

**Q: API 和 MQTT 透传会冲突吗？**
- 不会。每个串口有独立的 RLock，所有操作（API 读写 + MQTT 透传）排队执行
- 批量操作（如 yearly 读 12 个月）会持锁整个过程，保证原子性

**Q: 数据收发异常？**
- `config.yaml` 中设置 `level: "DEBUG"` 查看原始收发帧
- 确认波特率、数据位、校验位、停止位设置一致
