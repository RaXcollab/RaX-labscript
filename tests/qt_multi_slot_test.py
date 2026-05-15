"""Test A6: Qt pyqtSignal multi-slot semantics.

Validates:
  T3.1: A signal with two connected slots fires BOTH slots on emit.
  T3.2: Existing slot behavior is unchanged after a second slot is connected.
  T3.3: Cross-thread emit (background thread emit -> GUI thread slot fire)
        works for BOTH slots when both are GUI-thread methods.
  T3.4: Calling .connect() twice with the SAME slot (defensive guard) DOES
        produce duplicate firings — confirming we MUST guard with hasattr
        in our design (already in spec).
  T3.5: Disconnecting one slot leaves the other intact.

Run:
    python tests/qt_multi_slot_test.py
"""
import sys
import threading
import time

from qtutils.qt import QtCore, QtWidgets
from qtutils.qt.QtCore import QObject, pyqtSignal, QTimer


class Bridge(QObject):
    monitor_value_received = pyqtSignal(str, str)


class Slot1Receiver(QObject):
    """Simulates the existing _on_monitor_value_received."""
    def __init__(self):
        super().__init__()
        self.calls = []
        self.thread_ids = []

    def slot(self, connection, value_str):
        self.calls.append((connection, value_str))
        self.thread_ids.append(threading.get_ident())


class Slot2Receiver(QObject):
    """Simulates the new _post_to_internal_broker."""
    def __init__(self):
        super().__init__()
        self.calls = []
        self.thread_ids = []

    def slot(self, connection, value_str):
        self.calls.append((connection, value_str))
        self.thread_ids.append(threading.get_ident())


def main():
    app = QtWidgets.QApplication(sys.argv)
    main_thread_id = threading.get_ident()

    bridge = Bridge()
    s1 = Slot1Receiver()
    s2 = Slot2Receiver()

    # Connect first slot only - existing behavior baseline.
    bridge.monitor_value_received.connect(s1.slot)

    # T3.2: emit baseline; only s1 should fire.
    bridge.monitor_value_received.emit('baseline', '1.0')
    QtCore.QCoreApplication.processEvents()
    baseline_s1 = list(s1.calls)
    baseline_s2 = list(s2.calls)

    # Now add the second slot (mimicking lazy connect_to_pubsub).
    bridge.monitor_value_received.connect(s2.slot)

    # T3.1 + T3.3: emit from a BACKGROUND thread.
    def bg_emit():
        for i in range(5):
            bridge.monitor_value_received.emit(f'chan_{i}', f'{i*1.5}')
            time.sleep(0.005)

    t = threading.Thread(target=bg_emit, daemon=True)
    t.start()

    # Pump the GUI thread's event loop until queued slot calls drain.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        QtCore.QCoreApplication.processEvents()
        if len(s1.calls) >= 6 and len(s2.calls) >= 5:
            break
        time.sleep(0.01)
    t.join(timeout=1)

    # CAPTURE state right after bg phase, before T3.4/T3.5 mutate it.
    s1_after_bg_total = len(s1.calls)
    s2_after_bg_total = len(s2.calls)
    s1_thread_ids_after_bg = set(s1.thread_ids)
    s2_thread_ids_after_bg = set(s2.thread_ids)

    # T3.4: Connect s1 a SECOND time (duplicate slot — should fire twice).
    bridge.monitor_value_received.connect(s1.slot)
    s1_calls_before_dup = len(s1.calls)
    s2_calls_before_dup = len(s2.calls)
    bridge.monitor_value_received.emit('dup', '0')
    QtCore.QCoreApplication.processEvents()
    s1_added = len(s1.calls) - s1_calls_before_dup
    s2_added = len(s2.calls) - s2_calls_before_dup

    # T3.5: Disconnect s2 only; emit again; s1 still fires, s2 doesn't.
    bridge.monitor_value_received.disconnect(s2.slot)
    s1_pre = len(s1.calls)
    s2_pre = len(s2.calls)
    bridge.monitor_value_received.emit('after_disconnect', '99')
    QtCore.QCoreApplication.processEvents()
    s1_after = len(s1.calls) - s1_pre
    s2_after = len(s2.calls) - s2_pre

    # ---- Report ----
    print('=' * 60)
    print('Qt MULTI-SLOT TEST RESULTS (A6)')
    print('=' * 60)
    print(f'Main thread id: {main_thread_id}')
    print('')
    print(f'T3.2 baseline: only s1 fires before s2 connected:')
    print(f'   s1.calls={baseline_s1} s2.calls={baseline_s2}')
    print(f'   {"PASS" if baseline_s1 == [("baseline", "1.0")] and baseline_s2 == [] else "FAIL"}')
    print('')
    s1_count_from_bg = s1_after_bg_total - 1  # subtract baseline call
    s2_count_from_bg = s2_after_bg_total
    print(f'T3.1+T3.3 after bg emit, both slots fire (5 emits):')
    print(f'   s1 received {s1_count_from_bg} bg msgs after baseline (expect 5)')
    print(f'   s2 received {s2_count_from_bg} bg msgs (expect 5)')
    print(f'   s1 thread_ids match main: {s1_thread_ids_after_bg == {main_thread_id}}')
    print(f'   s2 thread_ids match main: {s2_thread_ids_after_bg == {main_thread_id}}')
    multi_slot_pass = (s1_count_from_bg == 5 and s2_count_from_bg == 5
                      and s1_thread_ids_after_bg == {main_thread_id}
                      and s2_thread_ids_after_bg == {main_thread_id})
    print(f'   {"PASS" if multi_slot_pass else "FAIL"}')
    print('')
    print(f'T3.4 connecting same slot twice causes duplicate fire:')
    print(f'   s1 added {s1_added} (expect 2 - duplicate fire), s2 added {s2_added} (expect 1)')
    print(f'   {"PASS (confirms hasattr guard is needed)" if s1_added == 2 and s2_added == 1 else "UNEXPECTED"}')
    print('')
    print(f'T3.5 disconnect s2; s1 still fires:')
    print(f'   s1 added {s1_after} (expect 2 since s1 is double-connected), s2 added {s2_after} (expect 0)')
    print(f'   {"PASS" if s2_after == 0 and s1_after == 2 else "FAIL"}')
    print('=' * 60)

    # Don't enter the QApplication event loop — we already pumped events.


if __name__ == '__main__':
    main()
