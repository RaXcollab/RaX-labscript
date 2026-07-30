# Flowchart — Motor-Queue Command Execution System

**Purpose:** Serialize motor commands with priority queue, execute in dedicated worker thread, deliver results via signals and reply queues

```mermaid
flowchart TD
    A["request_move_target<br/>raster_controller.py:366"] -->|creates MotorCommand| B["MotorCommand<br/>raster_controller.py:130-142"]
    B -->|cmd_id, priority, tag, payload| C["_enqueue<br/>raster_controller.py:1045-1049"]
    C -->|priority,seq,cmd tuple| D["PriorityQueue<br/>raster_controller.py:332"]
    D -->|get with timeout| E["_motor_worker_loop<br/>raster_controller.py:1068-1096"]
    E -->|CommandType check| F{Command Type?}
    F -->|MOVE_TARGET/MOVE_X/MOVE_Y| G["_execute<br/>raster_controller.py:1119-1370"]
    F -->|MOVE_MOTOR/JOG_MOTOR| G
    F -->|READ_POS| G
    F -->|STOP| H["_execute_stop<br/>raster_controller.py:1098-1110"]
    H -->|drain queue, call motor.stop| I["motor.stop<br/>hardware.py:353-367"]
    G -->|resolve calibration| J["AffineCalibration<br/>raster_controller.py:145-173"]
    J -->|target_to_motor| K["MotorXY coords"]
    G -->|bounds check target| L{Within Bounds?}
    L -->|no| M["MotorResult<br/>ok=False<br/>raster_controller.py:114-126"]
    L -->|yes| N["read_motor_xy<br/>raster_controller.py:1121-1124"]
    N -->|get_position X&Y| O["motor_x.get_position<br/>hardware.py:303-312"]
    O -->|KCube reads Position<br/>or fallback| P["KCube._device.Position<br/>hardware.py:308"]
    N -->|get_position Y| Q["motor_y.get_position<br/>hardware.py:303-312"]
    G -->|execute move| R["motor_x.move_to<br/>hardware.py:314-351"]
    G -->|execute move| S["motor_y.move_to<br/>hardware.py:314-351"]
    R -->|check deadband| T["_device.MoveTo<br/>with callback<br/>hardware.py:334"]
    S -->|check deadband| U["_device.MoveTo<br/>with callback<br/>hardware.py:334"]
    T -->|poll until complete| V["_task_complete_callback<br/>hardware.py:295-301"]
    U -->|poll until complete| V
    V -->|signal task done| W["move_to returns<br/>final position"]
    W -->|post-move readback| X["read_motor_xy<br/>again"]
    X -->|cache positions| Y["_last_motor_xy<br/>_last_target_xy<br/>raster_controller.py:1354-1356"]
    G -->|build result| M
    G -->|build result| Z["MotorResult<br/>ok=True<br/>motor_xy, target_xy<br/>raster_controller.py:1228-1232"]
    H -->|build result| M
    Z -->|_deliver_result| AA["_deliver_result<br/>raster_controller.py:1401-1429"]
    M -->|_deliver_result| AA
    AA -->|reply_q not None| AB["reply_q.put_nowait<br/>raster_controller.py:1405"]
    AA -->|emit signals| AC["command_done_signal<br/>raster_controller.py:1410"]
    AA -->|motor_xy result| AD["motor_position_signal<br/>raster_controller.py:1413"]
    AA -->|target_xy result| AE["target_position_signal<br/>raster_controller.py:1415"]
    AA -->|backlash result| AF["backlash_reading_signal<br/>raster_controller.py:1424"]
    AC -->|Qt cross-thread| AG["UI receives<br/>command_done_signal"]
    AD -->|Qt cross-thread| AH["UI Motor Position<br/>display updated"]
    AE -->|Qt cross-thread| AI["UI Target Position<br/>display updated"]
```

## Side effects
- Calls motor.move_to() which blocks motor worker thread until move complete
- Calls motor.get_position() for pre/post move readback
- Emits PyQt5 signals cross-thread (motor_position_signal, target_position_signal, command_done_signal, backlash_reading_signal)
- Updates internal caches (_last_motor_xy, _last_target_xy)
- Drains queue on STOP command
- Writes to Thorlabs Kinesis DLL (MoveTo, Position reads) via pythonnet
- Logs raster steps to _raster_log if tag='raster_step'

## External deps
- Thorlabs Kinesis .NET DLL (KCubeDCServo)
- AffineCalibration (target <-> motor space mapping)
- SimulatedMotor/KCube motor device classes from hardware.py
- PyQt5 signals/slots for cross-thread communication
- itertools.count() for seq tiebreaker in PriorityQueue
- threading.Lock for state synchronization

## Sources read
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:85-110 (CommandType enum)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:113-126 (MotorResult dataclass)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:129-142 (MotorCommand dataclass)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:323-336 (PriorityQueue init, worker thread spawn)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:366-378 (request_move_target entry point)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:1045-1049 (_enqueue with priority/seq tiebreaker)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:1068-1096 (_motor_worker_loop: dequeue, dispatch, error wrap, deliver)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:1098-1110 (_execute_stop: drain, call motor.stop)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:1119-1370 (_execute: command dispatch, bounds check, cal xform, move, readback)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:1121-1124 (read_motor_xy helper inside _execute)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:1282-1350 (MOVE_TARGET path: cal xform, bounds check, move sequence)
- C:/Users/radmo/labscript-suite/GUIs/rastering/raster_controller.py:1401-1429 (_deliver_result: reply_q, signals, status emits)
- C:/Users/radmo/labscript-suite/GUIs/rastering/hardware.py:156-201 (Motor base class interface)
- C:/Users/radmo/labscript-suite/GUIs/rastering/hardware.py:215-434 (KCube: move_to, get_position, stop)
- C:/Users/radmo/labscript-suite/GUIs/rastering/hardware.py:303-312 (KCube.get_position: reads Position or fallback)
- C:/Users/radmo/labscript-suite/GUIs/rastering/hardware.py:314-351 (KCube.move_to: deadband, MoveTo, poll loop, timeout)
- C:/Users/radmo/labscript-suite/GUIs/rastering/hardware.py:353-367 (KCube.stop: StopImmediate or Stop)
- C:/Users/radmo/labscript-suite/GUIs/rastering/hardware.py:437-472 (SimulatedMotor for testing)

## Confidence
High (95%). All primary code paths read end-to-end: request_move_target -> _enqueue -> PriorityQueue -> _motor_worker_loop -> _execute -> motor DLL -> readback -> _deliver_result -> signals. Calibration mapping, bounds checking, STOP handling, and error wrapping all traced. Hardware layer (KCube move_to, get_position) fully understood.

## Gaps
- Exact Kinesis callback mechanism timing (how quickly _task_complete_callback fires after MoveTo completes)
- Potential race conditions between telemetry thread READ_POS commands and user-initiated moves (serialized by queue but timing details unclear)
- Error handling in move_to timeout fallback (stop() best-effort, but actual Kinesis exception propagation not fully traced)
- Raster loop integration (_enqueue_next_raster_point callback chain not detailed here)
- ZMQ server integration (request_move_target source='zmq' path and network protocol not traced)
