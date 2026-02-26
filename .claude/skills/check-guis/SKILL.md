---
name: check-guis
description: Ping all external GUI ZMQ ports to verify they are running before starting BLACS
disable-model-invocation: true
---

Check which external GUIs are currently running by pinging their ZMQ REQ-REP ports.

## External GUI Registry

From CLAUDE.md:
| Name | REQ-REP Port | PUB-SUB Port |
|------|-------------|-------------|
| Laser Lock | 3796 | 3797 |
| Rastering GUI | 55535 | 55536 |
| BigSky YAG Hub | 55540 | 55541 |

## Health Check

Run the following to ping each GUI:

```bash
source ~/miniconda/etc/profile.d/conda.sh && conda activate labscript && python -c "
import zmq, json, time

guis = [
    ('Laser Lock', 3796),
    ('Rastering GUI', 55535),
    ('BigSky YAG Hub', 55540),
]

ctx = zmq.Context()
for name, port in guis:
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.RCVTIMEO, 2000)  # 2s timeout
    sock.setsockopt(zmq.LINGER, 0)
    try:
        sock.connect(f'tcp://localhost:{port}')
        sock.send_json({'action': 'HELLO'})
        reply = sock.recv_json()
        status = reply.get('status', 'UNKNOWN')
        print(f'  {name} (:{port}): UP — {status}')
    except zmq.Again:
        print(f'  {name} (:{port}): DOWN — no response (timeout)')
    except Exception as e:
        print(f'  {name} (:{port}): ERROR — {e}')
    finally:
        sock.close()
ctx.term()
"
```

## Report
Summarize which GUIs are up and which are down. If any required GUIs are down, warn the user to start them before launching BLACS.
