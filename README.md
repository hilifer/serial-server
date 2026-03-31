# MQTT WebSocket Serial Transparent Transmission Server

通过 MQTT WebSocket 协议实现串口透明传输的服务器。将物理串口（COM31、COM32、COM33）桥接到 MQTT 主题，支持双向数据透传。

## 架构

```
┌──────────┐    MQTT WS     ┌─────────────────┐    Serial     ┌──────────┐
│  Client  │ ◄────────────► │  Serial Server  │ ◄───────────► │  COM31   │
│ (Browser │    topic:      │                 │               ├──────────┤
│  / App)  │  serial/comXX  │   server.py     │ ◄───────────► │  COM32   │
│          │   /up | /down  │                 │               ├──────────┤
└──────────┘                │                 │ ◄───────────► │  COM33   │
                            └─────────────────┘               └──────────┘
```

## MQTT 主题说明

每个串口对应两个 MQTT 主题：

| 串口   | 上行主题（串口→MQTT）   | 下行主题（MQTT→串口）     |
|--------|------------------------|--------------------------|
| COM31  | `serial/com31/up`      | `serial/com31/down`      |
| COM32  | `serial/com32/up`      | `serial/com32/down`      |
| COM33  | `serial/com33/up`      | `serial/com33/down`      |

- **上行 (up)**：服务器从串口读取数据，发布到 `serial/comXX/up`
- **下行 (down)**：客户端发布数据到 `serial/comXX/down`，服务器写入对应串口

数据以原始字节透传，不做任何编码转换。

## 环境要求

- Python 3.10+（已测试 Python 3.15.0a7）
- MQTT Broker 需启用 WebSocket 监听（默认端口 9001）
- 推荐 Broker：[Mosquitto](https://mosquitto.org/)、[EMQX](https://www.emqx.io/)

### Mosquitto WebSocket 配置示例

在 `mosquitto.conf` 中添加：

```
listener 1883
protocol mqtt

listener 9001
protocol websockets
allow_anonymous true
```

重启 Mosquitto：

```bash
# Windows
net stop mosquitto && net start mosquitto

# Linux
sudo systemctl restart mosquitto
```

## 快速开始

### 一键启动（推荐）

**Windows：**
```
双击 start.bat
```

**Linux / macOS：**
```bash
chmod +x start.sh
./start.sh
```

一键脚本会自动完成：`git pull` → 创建虚拟环境 → 安装依赖 → 启动服务。

### 手动启动

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

# 4. 启动服务
python server.py
```

## 配置说明

编辑 `config.yaml`：

```yaml
mqtt:
  broker: "localhost"       # MQTT Broker 地址
  port: 1883                # MQTT TCP 端口（备用）
  ws_port: 9001             # MQTT WebSocket 端口
  username: ""              # 认证用户名（留空则不认证）
  password: ""              # 认证密码
  client_id_prefix: "serial-server"
  keepalive: 60

serial_ports:
  - name: "COM31"
    port: "COM31"           # Windows: COM31, Linux: /dev/ttyUSB0
    baudrate: 9600          # 波特率: 9600/19200/38400/57600/115200
    bytesize: 8             # 数据位: 5/6/7/8
    parity: "N"             # 校验位: N=无, E=偶, O=奇
    stopbits: 1             # 停止位: 1/1.5/2
    timeout: 0.1            # 读超时（秒）
    mqtt_topic_prefix: "serial/com31"

logging:
  level: "INFO"             # 日志级别: DEBUG/INFO/WARNING/ERROR
  file: "serial_server.log" # 日志文件路径（留空不写文件）
```

### Linux 串口映射

Linux 下需将 `port` 改为实际设备路径：

```yaml
serial_ports:
  - name: "COM31"
    port: "/dev/ttyUSB0"
    # ...
  - name: "COM32"
    port: "/dev/ttyUSB1"
    # ...
```

并确保用户有串口权限：

```bash
sudo usermod -a -G dialout $USER
# 重新登录生效
```

## 客户端测试

### 使用 mosquitto_sub / mosquitto_pub 测试

```bash
# 终端1：订阅 COM31 上行数据
mosquitto_sub -h localhost -p 9001 --ws -t "serial/com31/up" -v

# 终端2：向 COM31 发送数据
mosquitto_pub -h localhost -p 9001 --ws -t "serial/com31/down" -m "Hello COM31"
```

### 使用 Python 客户端测试

```python
import paho.mqtt.client as mqtt
import time

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")

def on_message(client, userdata, msg):
    print(f"[{msg.topic}] {msg.payload}")

client.on_message = on_message
client.connect("localhost", 9001)
client.subscribe("serial/com31/up")

# 发送数据到 COM31
client.publish("serial/com31/down", b"\x01\x02\x03")

client.loop_forever()
```

### 使用 JavaScript (浏览器) 测试

```html
<script src="https://unpkg.com/mqtt/dist/mqtt.min.js"></script>
<script>
const client = mqtt.connect('ws://localhost:9001');

client.on('connect', () => {
  console.log('Connected');
  client.subscribe('serial/com31/up');
  // 向 COM31 发送数据
  client.publish('serial/com31/down', 'Hello from browser');
});

client.on('message', (topic, message) => {
  console.log(`${topic}: ${message}`);
});
</script>
```

## 运行测试

```bash
# 激活虚拟环境后
pip install -r requirements.txt

# 运行所有测试
python -m pytest tests/ -v

# 运行并查看覆盖率
python -m pytest tests/ -v --tb=short
```

## 项目结构

```
serial-server/
├── server.py          # 主服务程序
├── config.yaml        # 配置文件
├── requirements.txt   # Python 依赖
├── start.bat          # Windows 一键启动
├── start.sh           # Linux 一键启动
├── tests/             # 单元测试
│   ├── __init__.py
│   └── test_server.py
└── README.md          # 本文档
```

## 常见问题

**Q: 连接 MQTT Broker 失败？**
- 确认 Broker 已启动并监听 WebSocket 端口 (默认 9001)
- 检查防火墙是否放行端口
- 如果 Broker 需要认证，在 `config.yaml` 中配置 `username` 和 `password`

**Q: 串口打开失败？**
- 确认串口设备存在：Windows 在设备管理器查看，Linux 执行 `ls /dev/ttyUSB*`
- 确认无其他程序占用串口
- Linux 确认当前用户在 `dialout` 组中

**Q: 数据收发不正常？**
- 将日志级别改为 `DEBUG` 查看原始收发数据
- 确认双方波特率、数据位、校验位、停止位设置一致
