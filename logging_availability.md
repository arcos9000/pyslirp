# Log Stack Summary (TrueNAS SCALE)

This document summarizes the **syslog-ng → Vector → Loki + Grafana** stack deployed at `/mnt/hdd-pool/userdata/log`.

---

## Stack Overview

**Purpose:** Accept legacy syslog from any host, persist per-host files, forward to a modern log database (Loki), and visualize/search in Grafana.

**Services (Docker Compose):**
| Service   | Image                         | Ports (host→container) | Key Mounts                                           | Notes |
|-----------|-------------------------------|-------------------------|------------------------------------------------------|------|
| syslogng  | `balabit/syslog-ng:latest`    | `514/udp`, `514/tcp`    | `./syslog-ng/syslog-ng.conf:/etc/syslog-ng/syslog-ng.conf:ro`<br>`./logs:/var/log/remote` | Receives syslog; writes per-host daily files under `logs/` |
| vector    | `timberio/vector:0.42.0`      | *(none)*                | `./vector/vector.toml:/etc/vector/vector.toml:ro`<br>`./logs:/var/log/remote:ro` | Tails syslog-ng files and ships to Loki |
| loki      | `grafana/loki:3.0.0`          | `3100→3100`             | `./loki-config.yml:/etc/loki/config.yml:ro`<br>`./loki-data:/loki` | Single-node TSDB w/ memberlist ring; filesystem storage |
| grafana   | `grafana/grafana:latest`      | `3000→3000`             | `./grafana-data:/var/lib/grafana`<br>`./grafana-provisioning:/etc/grafana/provisioning` | Grafana pre-provisioned with a Loki datasource |

**On-disk structure:**
```
/mnt/hdd-pool/userdata/log
├─ docker-compose.yml
├─ syslog-ng/
│  └─ syslog-ng.conf
├─ vector/
│  └─ vector.toml
├─ loki-config.yml
├─ logs/                # per-host syslog files (created by syslog-ng)
├─ loki-data/           # Loki storage (chunks, rules, compactor)
└─ grafana-data/        # Grafana state
```

---

## Endpoints

- **Grafana UI:** `http://<NAS-IP>:3000`  
  - Login: `admin / <your GF_SECURITY_ADMIN_PASSWORD>` (default was `changeme` in the setup script)  
  - Data source: **Loki** (pre-provisioned)
- **Loki API:** `http://<NAS-IP>:3100`  
  - Health: `GET /ready`, `GET /metrics`

---

## Health & Ops

**Container status**
```bash
cd /mnt/hdd-pool/userdata/log
docker compose ps
```

**Check logs**
```bash
docker logs syslogng --tail=100
docker logs vector --tail=100
docker logs loki --tail=200
docker logs grafana --tail=100
```

**Loki health check**
```bash
curl -sSf http://127.0.0.1:3100/ready && echo "OK"
```

**Restart a service**
```bash
docker compose restart loki
```

---

## How remote senders can ship logs

### 1) Classic syslog (Linux/Unix)

**One-off test**
```bash
logger -n <NAS-IP> -P 514 -t myhost "hello from syslog"
```

**rsyslog (client) minimal**
```
*.* @@<NAS-IP>:514   # TCP
# or
*.* @<NAS-IP>:514    # UDP
```
- Put into `/etc/rsyslog.d/90-central.conf` and restart: `systemctl restart rsyslog`.

**syslog-ng (client) minimal**
```conf
destination d_central { tcp("<NAS-IP>" port(514)); };
log { source(s_src); destination(d_central); };
```

### 2) Windows

**NXLog (to syslog TCP)**
```conf
<Input in>
  Module im_msvistalog
</Input>
<Output out>
  Module  om_tcp
  Host    <NAS-IP>
  Port    514
</Output>
<Route 1>
  Path in => out
</Route>
```

**Winlogbeat (Elastic) → syslog-ng**: use an intermediate (e.g., Beats to Logstash) or switch to NXLog; or install Vector/Fluent Bit on Windows and push to Loki (below).

### 3) Python applications

**A) Built-in syslog handler (no extra deps)**
```python
import logging, logging.handlers
log = logging.getLogger("myapp"); log.setLevel(logging.INFO)
h = logging.handlers.SysLogHandler(address=("<NAS-IP>", 514))  # UDP
h.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
log.addHandler(h)
log.warning("hello via syslog")
```

**B) Direct to Loki (HTTP)**
```bash
pip install python-logging-loki
```
```python
import logging
from logging_loki import LokiHandler

log = logging.getLogger("myapp")
log.setLevel(logging.INFO)
log.addHandler(LokiHandler(
    url="http://<NAS-IP>:3100/loki/api/v1/push",
    tags={"app": "myapp", "env": "prod"},
    version="1",
))
log.error("hello to loki via HTTP")
```

### 4) Vector / Fluent Bit agents (any OS)

**Vector (client) → Loki (HTTP)**
```toml
[sources.app]
type = "stdin" # or "file", "journald", etc.

[sinks.loki]
type = "loki"
inputs = ["app"]
endpoint = "http://<NAS-IP>:3100"
labels = { host = "client1", app = "myapp" }
encoding.codec = "text"
```
Run: `vector -c client.toml` and write lines to stdin, or point `sources.file` at your app logs.

---

## Querying in Grafana (LogQL)

**All logs from syslog source**
```
{source="syslog"}
```

**Only warnings and above (message match)**
```
{source="syslog"} |~ "(?i)(warn|error|fatal)"
```

**Count per host over 5m windows**
```
sum by (host) (count_over_time({source="syslog"}[5m]))
```

> Tip: To filter by a structured `level` label instead of message text, parse/attach a `level` label in **Vector** with a Remap transform and add it to `labels` in the Loki sink.

---

## Editing/Extending the pipeline

**Vector → add a second sink (e.g., archive to S3/MinIO)**
```toml
[sinks.archive]
type = "aws_s3"
inputs = ["to_text"]            # from the existing transform
bucket = "logs"
region = "us-east-1"
endpoint = "http://minio:9000"  # if self-hosted
key_prefix = "syslog/"
compression = "gzip"
```

**Loki log level noise**
Reduce Loki’s own verbosity in `docker-compose.yml`:
```yaml
  loki:
    command: -config.file=/etc/loki/config.yml -log.level=warn
```

---

## Troubleshooting Quick Hits

- **Loki port 3100 unreachable**: `docker compose ps`; if restarting, check `docker logs loki`. Ensure `loki-config.yml` is mounted and uses `memberlist` ring; verify with `docker run ... -verify-config`.
- **Permission denied under `/loki`**: ensure on-disk `loki-data/` is owned by UID **10001**:  
  `chown -R 10001:10001 loki-data`
- **No logs in Grafana**: confirm files are appearing in `logs/<host>/...`. Check Vector logs for shipping errors. Make sure your query matches labels: try plain `{source="syslog"}` first.
- **UDP vs TCP**: prefer **TCP 514** for reliability; keep UDP enabled for legacy gear.

---

## Maintenance

- **Update images**
```bash
cd /mnt/hdd-pool/userdata/log
docker compose pull
docker compose up -d
```

- **Backups**: snapshot/replicate the dataset containing `logs/`, `loki-data/`, and `grafana-data/`.
- **Retention**: Loki TSDB uses filesystem storage; manage retention via periodic pruning or by sizing your dataset appropriately.

---

*Prepared for your TrueNAS SCALE deployment.*
