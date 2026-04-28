# MIDS
Modular Intrusion Detective Software or MIDS for short!
[![C++20](https://img.shields.io/badge/C%2B%2B-20-blue.svg)](https://en.cppreference.com/w/cpp/20)
[![CMake](https://img.shields.io/badge/build-CMake%203.16%2B-064F8C.svg)](https://cmake.org/)
[![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)](#build)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](#license)

A real, compilable, modular network intrusion detection system written from
scratch in modern C++20. Live `libpcap`/Npcap capture (or offline `.pcap`
replay) → SPSC ring buffer → packet parser → eight pluggable detectors →
structured JSON events streamed over TCP and logged to disk, plus a small
embedded HTTP API for stats and recent alerts.

**This is not a Snort/Suricata replacement.** It is a clean, honest, ~3,500-line
engine where every layer is decoupled, every detector is a plugin, every
threshold is configurable, and there is nothing magic. Read any file
top-to-bottom and the design intent is right there in the comments.

## Highlights

- **8 detectors out of the box** covering L2 → L7: port scan, brute force,
  traffic spike, statistical anomaly, DNS tunneling, ICMP tunneling, ARP
  spoofing, and a Snort-style content-signature engine
- **Lock-free SPSC ring** between capture and detection threads, ~380k pps on
  a single core in offline replay benchmarks
- **Plugin-style detector model** — adding a new detector is one new file and
  one `engine.add_detector()` call
- **Hot-reload** of configuration via `SIGHUP` (POSIX) — atomic config swap,
  in-flight detections finish against the old snapshot
- **Cross-platform** — Linux, macOS, and Windows (via Npcap)
- **No black-box dependencies** — only `libpcap` and `nlohmann/json` (the
  latter fetched at configure time)

## Quick look

```sh
$ ./build/ids --config config/ids_config.json --pcap traffic.pcap
{"ts":"2026-04-25T16:42:08.341Z","level":"info","msg":"pcap file opened","path":"traffic.pcap"}
{"ts":"2026-04-25T16:42:09.012Z","level":"info","msg":"ids stopped","packets_captured":686489,"packets_parsed":686144,"events_emitted":4}

$ cat events.jsonl
{"detector":"port_scan_detector","threat_type":"port_scan","severity":"high","score":78,"src_ip":"10.0.0.5","dst_ip":"10.0.0.2","explanation":"source 10.0.0.5 contacted 27 distinct (host,port) pairs in 5000ms (threshold 20)","ts":"2026-04-25T16:42:08.341Z","proto":"tcp"}
{"detector":"signature_detector","threat_type":"signature","severity":"critical","score":95,"src_ip":"10.0.0.5","dst_ip":"10.0.0.2","explanation":"rule \"http_user_agent_sqlmap\" matched: sqlmap default User-Agent","ts":"2026-04-25T16:42:08.510Z","proto":"tcp","dst_port":80}
{"detector":"icmp_tunnel_detector","threat_type":"icmp_tunnel","severity":"high","score":100,"src_ip":"10.0.0.5","dst_ip":"10.0.0.2","explanation":"icmp echo from 10.0.0.5 to 10.0.0.2 carries 800B payload at 7.74 bits/byte entropy (limits: 96B, 6.5 bits)","ts":"2026-04-25T16:42:08.612Z","proto":"icmp"}
{"detector":"arp_spoof_detector","threat_type":"arp_spoof","severity":"critical","score":95,"src_ip":"10.0.0.10","explanation":"ip 10.0.0.10 moved from MAC aa:aa:aa:aa:aa:aa to bb:bb:bb:bb:bb:bb (arp reply)"}
```

## Architecture

```
   ┌────────────┐   raw_frame   ┌──────────┐   parsed_packet   ┌────────────┐
   │  capture   │ ────────────▶ │ ring buf │ ────────────────▶ │ detection  │
   │  (libpcap) │  (SPSC, lock- │  2k POD  │   (parser)        │   engine   │
   └────────────┘   free)       └──────────┘                   └─────┬──────┘
                                                                     │ ids_event
                                                                     ▼
                                                              ┌──────────────┐
                                                              │  dispatcher  │
                                                              └──┬────────┬──┘
                                                                 │        │
                                                            file sink   tcp sink
                                                            (jsonl)     (broadcast)

                            ┌────────────┐
                            │ http api   │   GET /healthz  /stats  /events
                            └────────────┘
```

| Layer        | Files                                                                                                                                                            |
|--------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Capture      | `capture/pcap_source.{hpp,cpp}`, `capture/raw_frame.hpp`                                                                                                          |
| Preprocess   | `preprocess/parser.{hpp,cpp}`, `preprocess/parsed_packet.hpp`                                                                                                     |
| Detection    | `detect/detection_engine.*`, `detect/detector.hpp`, `detect/{port_scan,brute_force,traffic_spike,anomaly,dns_tunnel,icmp_tunnel,arp_spoof,signature}_detector.*`  |
| Events       | `event/event_dispatcher.*`, `event/file_sink.*`, `event/tcp_stream_sink.*`                                                                                        |
| API          | `api/http_server.{hpp,cpp}`                                                                                                                                       |
| Core         | `core/{config,logger,event,types,portable_time,entropy}.{hpp,cpp}`, `core/{ring_buffer,stats,platform}.hpp`                                                       |

**Threading model:** one thread for `pcap_loop`, one for parse + detect, one
worker in the event dispatcher, one accept thread per network sink, plus
thread-per-connection inside the HTTP server. The hot path between capture
and detection is lock-free; everything else uses standard `std::mutex`.

## Detectors

| Detector          | What it catches                                                                                                                          | Score range |
|-------------------|-------------------------------------------------------------------------------------------------------------------------------------------|-------------|
| `port_scan`       | Many distinct (dst_ip, dst_port) tuples from one source in a sliding window. TCP SYN-without-ACK or any UDP                              | 50 – 100    |
| `brute_force`     | Repeated SYN to a watched port (22/21/23/3389/...) per (src,dst,port)                                                                    | 60 – 100    |
| `traffic_spike`   | Per-destination packets/sec exceeds a configurable threshold over a rolling window                                                       | 40 – 95     |
| `anomaly`         | Global packet rate has a \|z-score\| above threshold vs a rolling baseline                                                               | 20 – 100    |
| `dns_tunnel`      | DNS queries with unusually long labels, long total qname, or high Shannon entropy — rate-thresholded per source. Catches dnscat2/iodine  | 50 – 100    |
| `icmp_tunnel`     | ICMP echo payloads above a size threshold AND with high entropy. Catches ICMP-based C2 channels                                          | 50 – 100    |
| `arp_spoof`       | Same IP suddenly advertising a different MAC within the binding TTL — classic MITM pivot                                                 | 95          |
| `signature`       | Content matches against JSON-loaded rules (proto/port filter + payload substring, case-sensitive or not). HTTP/SQLi patterns, tool UAs   | per rule    |

The score is a function of how badly the observation overshoots the
threshold — a detector firing right at threshold sits at the low end of its
band, an extreme observation saturates near 100. The `signature` detector
uses the score declared by each rule.

### Signature rules

The signature engine loads rules from a JSON file pointed to by
`detection.signatures.rules_path`. Each rule is an object:

```json
{
  "name": "http_etc_passwd",
  "description": "Path traversal attempting to read /etc/passwd over HTTP",
  "proto": "tcp",
  "dst_port": 80,
  "content": "/etc/passwd",
  "case_sensitive": false,
  "score": 90,
  "severity": "high"
}
```

`name` and `content` are required. Everything else is optional. Multiple
rules are evaluated independently per packet; an alert is emitted for each
match (with per-(rule, source) throttling). See `config/signatures.json` for
a starter ruleset covering HTTP path traversal, SQLi patterns, sqlmap UA
detection, EternalBlue markers, and more.

## Build

### Linux / macOS

Dependencies: `libpcap` headers, CMake ≥ 3.16, a C++20 compiler (GCC ≥ 11,
Clang ≥ 13). `nlohmann/json` is fetched automatically.

```sh
# Debian / Ubuntu
sudo apt-get install -y build-essential cmake libpcap-dev

# Fedora / RHEL
sudo dnf install -y gcc-c++ cmake libpcap-devel

# macOS
brew install cmake libpcap
```

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
ctest --test-dir build --output-on-failure
```

### Windows (MSVC + Npcap)

Windows is supported via the [Npcap](https://npcap.com/) driver.

1. **Visual Studio 2022 Build Tools** with the *Desktop development with C++*
   workload, CMake ≥ 3.16
2. **Npcap runtime** — installer at <https://npcap.com/>
3. **Npcap SDK** — <https://npcap.com/dist/npcap-sdk-1.13.zip>, extract somewhere

From a Developer PowerShell:

```powershell
cmake -S . -B build -DNPCAP_SDK_DIR="C:\path\to\npcap-sdk-1.13"
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

`NPCAP_SDK_DIR` (or `WPCAP_DIR`) also works as an environment variable.
Live capture on Windows requires Administrator. Offline pcap replay does not.

## Run

### Live capture

```sh
# Linux: grant the capability once instead of running as root
sudo setcap cap_net_raw,cap_net_admin=eip ./build/ids
./build/ids --config config/ids_config.json

# Override interface / filter without editing the config
./build/ids --config config/ids_config.json --iface eth0 --bpf 'tcp or udp'
```

### Offline pcap replay

```sh
./build/ids --config config/ids_config.json --pcap traffic.pcap
```

The replay path uses the same parser and detectors as the live path, so you
can generate fixtures with `tcpdump -w traffic.pcap` (or `dumpcap` on
Windows) and replay them without elevated privileges.

### Hot reload (POSIX)

```sh
kill -HUP $(pidof ids)
```

Atomic config swap via `std::shared_ptr` — in-flight detection calls finish
against the old snapshot, the next call sees the new one. Windows lacks
`SIGHUP`; restart the process for now.

## Event format

Every alert is one JSON object per line. Written to `events.jsonl` and
broadcast over TCP. Subscribe to the live stream with `netcat`:

```sh
nc localhost 9999
```

Sample event:

```json
{"detector":"port_scan_detector","threat_type":"port_scan","severity":"high","score":78,"src_ip":"10.0.0.5","dst_ip":"10.0.0.2","explanation":"source 10.0.0.5 contacted 27 distinct (host,port) pairs in 5000ms (threshold 20)","ts":"2026-04-25T16:42:08.341Z","proto":"tcp"}
```

## HTTP API

Bound to `127.0.0.1` only by design.

| Route                  | Returns                                                                              |
|------------------------|---------------------------------------------------------------------------------------|
| `GET /healthz`         | `200 ok`                                                                              |
| `GET /stats`           | JSON counters: packets captured/parsed/dropped, events emitted/dropped, uptime, pps  |
| `GET /events?limit=N`  | Last `N` events (default 100, capped at 1000)                                         |

```sh
curl localhost:8080/stats
curl 'localhost:8080/events?limit=20'
```

## Adding a detector

Detectors are plugins. Subclass `ids::detector`, implement the callbacks,
register it with the engine:

```cpp
class my_detector final : public ids::detector {
public:
    std::string_view name() const noexcept override { return "my_detector"; }

    void on_packet(const ids::parsed_packet& pkt,
                   ids::event_sink_fn& emit) override {
        if (looks_bad(pkt)) {
            ids::ids_event ev;
            ev.threat_type = "weird_thing";
            ev.detector_name = std::string(name());
            ev.sev = ids::severity::medium;
            ev.score = 65;
            ev.src_ip = pkt.src_ip;
            ev.dst_ip = pkt.dst_ip;
            ev.explanation = "saw something weird";
            emit(std::move(ev));
        }
    }
    void on_tick(ids::steady_tp, ids::event_sink_fn&) override {}
    void reconfigure(const ids::config&) override {}
};

engine.add_detector(std::make_unique<my_detector>());
```

No central registry, no plugin loader, no rebuild of unrelated translation
units — one new file under `detect/`, one `add_detector` call.

## Project layout

```
ids/
├── CMakeLists.txt
├── README.md
├── config/
│   ├── ids_config.json        # main runtime config
│   └── signatures.json        # signature ruleset
├── include/ids/               # public headers, declarations only
│   ├── api/    capture/    core/    detect/    event/    preprocess/
├── src/                       # implementation
│   ├── api/    capture/    core/    detect/    event/    preprocess/
│   └── main.cpp
└── tests/                     # unit tests (CTest)
```

## Tests

5 unit tests covering the SPSC ring buffer (single-thread + multi-thread
stress with 1M items), the Ethernet/IPv4/TCP/UDP/ARP parser, Shannon
entropy math, signature loading + matching with all options, and the ARP
binding tracker. Run with `ctest --test-dir build --output-on-failure`.

## Limitations & non-goals

- **IPv4 only.** IPv6 frames are cleanly rejected; adding v6 is parser-local.
- **No fragment reassembly.** L3 is parsed, L4 of fragmented packets is skipped.
- **Single-threaded detection.** ~380k pps on one core in benchmarks. A
  flow-hash-sharded design is the path to multi-core throughput.
- **The HTTP server is intentionally tiny.** GET-only, no keep-alive, no
  auth, bound to loopback. Don't expose it to the internet.
- **No packet logging.** Detected events are logged; full packet captures
  are not. Use `tcpdump` if you need PCAP-of-everything.

## Roadmap

Short list, ranked by value:

1. libFuzzer harness for the parser + a small pcap corpus
2. `/reload` HTTP endpoint (replaces SIGHUP, works on Windows)
3. Bounded per-source state in DNS tunnel / port scan / brute force detectors
4. `/metrics` Prometheus endpoint
5. Schema versioning on emitted events
6. Detector-driven BPF filter (engine builds the filter from enabled detectors)
7. Flow-hash-sharded multi-worker detection

## License

MIT — see [LICENSE](LICENSE) for details.
