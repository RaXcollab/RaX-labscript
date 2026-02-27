---
paths:
  - "userlib/user_devices/**"
  - "blacs/**"
---

# BLACS Device Conventions

## Qt Thread Safety

- `@define_state` methods resume after `yield` in the mainloop BACKGROUND thread, not the Qt GUI thread
- **USE `inmain()`** for Qt widget calls (setValue, setText, show, hide, setEnabled, etc.)
- **DO NOT USE `with qtlock:`** — it doesn't marshal to the GUI thread; causes Windows access violations
- PUB-SUB daemon threads → use `pyqtSignal` to bridge to the GUI thread

## Worker Paths

- Custom devices: `"user_devices.RemoteControl.blacs_workers.RemoteControlWorker"`
- NOT `"labscript_devices.RemoteControl..."` — wrong module