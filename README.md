# WebSocket Fanout Slow Client Killer

A demonstration project showing how one slow WebSocket client can stall an entire broadcast system, and how to solve it using per-client bounded queues with isolation.

## 🎯 What & Why

In WebSocket fanout architectures, **one slow client can stall the entire broadcast loop**, causing latency spikes for all connected clients. This is a common backpressure problem that affects real-time applications like:

- Live dashboards and monitoring systems
- Real-time chat applications  
- Financial data feeds
- IoT sensor data streaming
- Live gaming leaderboards

This project demonstrates the problem and implements a robust solution using **per-client bounded queues** with drop-oldest and auto-disconnect policies.

## 🏗️ Architecture

```
Publisher → Broadcast Loop → Client Queues → WebSocket Send
   ↓             ↓              ↓             ↓
 50 Hz       Naive: Sequential   Bounded    Individual
Messages    Queue: Concurrent   Queues     Send Tasks
```

**Data Flow:**
1. **Publisher** generates messages at constant rate
2. **Broadcast Loop** distributes to all clients
3. **Client Queues** buffer messages per-client (queue mode only)
4. **Send Tasks** handle individual client transmission

## 🔄 Two Modes

### 🐌 Naive Mode  
- **Sequential** `await ws.send()` to each client
- **One slow client blocks** entire broadcast loop
- **Demonstrates** the backpressure problem

### 🚀 Queue Mode
- **Per-client bounded queues** with drop-oldest policy
- **Concurrent send tasks** isolate slow clients  
- **Auto-disconnect** on excessive drops or timeouts
- **Fast clients unaffected** by slow clients

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/kemalerbakirci/ws-fanout-slow-client-killer
cd ws-fanout-slow-client-killer

# Install dependencies  
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the demo
python3 demo.py
```

### 📊 Expected Demo Results

```
📊 Testing QUEUE MODE (with isolation)
✅ Fast client: 234 messages at 46.8 msg/s with 0.8ms average latency
✅ Slow client: 40 messages at 2.8 msg/s with 1555.3ms average latency
```

**Key Insight:** Fast client maintains **sub-millisecond latency** even when slow client has **1.5+ second delays**!

## 📋 Usage

### 🖥️ Server (`server.py`)

```bash
# Basic usage
python3 server.py [options]

# Examples
python3 server.py --mode queue --rate 50 --port 8765
python3 server.py --mode naive --rate 100 --log-json
```

**Options:**
```
--mode {naive,queue}     Broadcast mode (default: queue)
--host HOST             Listen address (default: 0.0.0.0)  
--port PORT             Listen port (default: 8765)
--rate RATE             Messages per second (default: 100)
--payload-bytes N       Random payload size (default: 64)
--maxsize N             Queue size per client (default: 100)
--drop-limit N          Auto-disconnect threshold (default: 50)
--full-timeout SECS     Max queue full time (default: 5)
--ping-interval SECS    WebSocket ping interval (default: 20)
--ping-timeout SECS     WebSocket ping timeout (default: 20)
--log-json              Output JSON logs (recommended for automation)
--config FILE           YAML config file
```

### 👥 Client Simulator (`clientsim.py`)

```bash
# Basic usage
python3 clientsim.py [options]

# Examples  
python3 clientsim.py --concurrency 5 --duration 30
python3 clientsim.py --slow-ms 200 --jitter-ms 50
```

**Options:**
```
--url URL               WebSocket URL (default: ws://localhost:8765)
--concurrency N         Number of connections (default: 1)
--slow-ms MS            Processing delay per message (default: 0)
--jitter-ms MS          Random latency jitter (default: 0)
--duration SECS         Test duration (default: 30)
--print-every N         Stats frequency (default: 100)
--id-prefix PREFIX      Connection label prefix (default: "cli")
```

## 🎬 Demo Scenarios

### 🎯 Quick Demo (Recommended)

```bash
# Run the automated demo
python3 demo.py
```

This runs a complete test showing fast vs slow client performance in queue mode.

### 🐌 Manual Demo: Naive Mode Stall

```bash
# Terminal 1: Start naive server
python3 server.py --mode naive --rate 50

# Terminal 2: Start fast clients  
python3 clientsim.py --concurrency 3 --duration 60 --id-prefix fast

# Terminal 3: Add slow client - watch latency spike!
python3 clientsim.py --slow-ms 200 --duration 30 --id-prefix slow
```

**Expected Result:** All clients experience high latency when slow client connects.

### 🚀 Manual Demo: Queue Mode Isolation

```bash
# Terminal 1: Start queue server
python3 server.py --mode queue --rate 50 --maxsize 100

# Terminal 2: Start fast clients
python3 clientsim.py --concurrency 3 --duration 60 --id-prefix fast

# Terminal 3: Add slow client - fast clients unaffected!
python3 clientsim.py --slow-ms 200 --duration 30 --id-prefix slow
```

**Expected Result:** Fast clients maintain low latency; slow client gets auto-disconnected.

### 📹 Recording Demos

```bash
# Record terminal session
asciinema rec examples/asciinema/queue-demo.cast

# Convert to GIF (requires Docker)
docker run --rm -v $PWD:/data asciinema/asciicast2gif \
  examples/asciinema/queue-demo.cast examples/gifs/queue-demo.gif
```

## 📊 Metrics & Monitoring

### 📈 Server Metrics

The server logs comprehensive metrics every 5 seconds:

**JSON Format** (`--log-json`):
```json
{
  "type": "summary",
  "clients": 3,
  "pub_rate": 50.0,
  "e2e_latency": {"p50": 1.2, "p95": 15.6},
  "disconnects_total": 1
}
```

**Human-Readable Format**:
```
Clients: 3 | Rate: 50.0/s | E2E p50/p95: 1.2/15.6ms | Disconnects: 1
```

### 📋 Per-Client Metrics
- **`queue_len`**: Current queue depth
- **`drops_total`**: Messages dropped (lifetime)  
- **`send_latency_ms`**: Average WebSocket send time
- **`e2e_latency_ms`**: End-to-end latency from client ACKs

### 🔧 Client Statistics
```
Client          Messages   Rate/s   Min     Avg     P95     Drops
fast-0          234        46.8     0.3     0.8     1.2     0
slow-0          40         2.8      0.3     1555.3  3024.5  0
```

## 🛠️ Make Targets

```bash
make venv           # Create virtual environment
make run-naive      # Start server in naive mode  
make run-queue      # Start server in queue mode
make fast-clients   # Spawn 3 normal clients
make slow-client    # Spawn 1 slow client
make demo-naive     # Instructions for naive demo
make demo-queue     # Instructions for queue demo  
make test           # Run pytest tests
make fmt            # Format code (placeholder)
```

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| **Port Conflicts** | Change `--port` or check `lsof -i :8765` |
| **Connection Refused** | Ensure server is running and firewall allows connections |
| **High Latency** | Use `--log-json` for cleaner output; check network conditions |
| **Import Errors** | Run `pip install -r requirements.txt` in virtual environment |
| **Queue Overflow** | Increase `--maxsize` or tune `--drop-limit` for your use case |
| **Ping Timeouts** | Increase `--ping-timeout` for unstable networks |
| **Rich Formatting Issues** | Use `--log-json` flag for clean, parseable output |

### 🔧 Performance Tips

- **Reduce log frequency**: Metrics log every 5 seconds (can be adjusted in code)
- **JSON logging**: Use `--log-json` for production/automation  
- **Network optimization**: Disable Nagle algorithm in production WebSocket libraries
- **Queue tuning**: Start with `--maxsize 100`, adjust based on memory constraints

## 🧪 Testing

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test
python3 -m pytest tests/test_drop_oldest.py -v

# Run with coverage (if installed)
python3 -m pytest --cov=server tests/
```

**Test Coverage:**
- ✅ Queue drop-oldest functionality
- ✅ Client isolation verification  
- ✅ Server startup/shutdown
- ✅ Auto-disconnect policies

## ⚖️ Trade-offs

| Aspect | Naive Mode | Queue Mode |
|--------|------------|------------|
| **Simplicity** | ✅ Simple | ❌ Complex |
| **Client Isolation** | ❌ None | ✅ Full |
| **Memory Usage** | ✅ Low | ❌ Higher |
| **Latency** | ❌ Spiky | ✅ Consistent |
| **Message Delivery** | ✅ Guaranteed | ❌ May Drop |
| **Scalability** | ❌ Poor | ✅ Good |

## 🏗️ Implementation Details

### 🔧 Core Components

- **`server.py`** (~350 LOC): WebSocket server with dual broadcast modes
- **`clientsim.py`** (~200 LOC): Load testing client with latency simulation  
- **`tests/`**: Comprehensive test suite covering core functionality
- **`scripts/`**: Shell scripts for easy demo execution
- **`demo.py`**: Automated demonstration script

### 🎯 Key Features

- **Type hints** throughout codebase
- **Async/await** for high concurrency
- **Graceful shutdown** with proper cleanup
- **Configurable** via CLI args and YAML  
- **Rich logging** with fallback to standard logging
- **Cross-platform** (Linux, macOS, Windows)

### 📦 Dependencies

- **`websockets`**: WebSocket implementation
- **`rich`**: Beautiful terminal output (optional)
- **`pydantic`**: Data validation (future use)
- **`pytest`**: Testing framework
- **`uvloop`**: High-performance event loop (Unix only)

## 🚀 Production Considerations

This is a **demonstration project**. For production use, consider:

- **Security**: Authentication, authorization, rate limiting
- **Monitoring**: Prometheus metrics, health checks  
- **Reliability**: Message persistence, guaranteed delivery
- **Scale**: Load balancing, horizontal scaling
- **Network**: TLS/SSL, CDN integration

## 🔮 Future Enhancements

- **Prometheus metrics exporter** (`metrics.py`)
- **Docker Compose setup** for easy demos
- **Benchmark suite** with latency-drop curve analysis
- **Web dashboard** for real-time monitoring
- **Message replay** functionality
- **Client authentication** and rate limiting

## 📄 License

MIT License - see [LICENSE](LICENSE) file.

## 🙏 Acknowledgments

This project demonstrates common WebSocket scaling challenges and solutions used in production systems. The techniques shown are applicable to:

- Real-time dashboards (Grafana, DataDog)
- Financial data feeds (trading platforms)  
- IoT sensor networks
- Live gaming systems
- Chat applications



**⚡ Ready to see backpressure isolation in action? Run `python3 demo.py`!**
