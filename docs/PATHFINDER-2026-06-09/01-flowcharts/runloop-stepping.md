# Flowchart — Raster run-loop with continuous and single-step modes

**Purpose:** Enable automatic scanning of a target-space path with configurable continuous or manual stepping, logging each move and synchronized via Qt signal chaining

```mermaid
flowchart TD
    UI_START["User clicks<br/>start_button<br/>ui.py:744"]
    BUILD_SPEC["_start_raster<br/>ui.py:1003-1037<br/>Build RasterSpec"]
    INIT_STATE["start_raster<br/>raster_controller.py:878-916<br/>Set _raster_iter, _active, mode"]
    
    DECISION{"Continuous?<br/>raster_controller.py:898"}
    
    CONTINUOUS["Continuous Mode<br/>raster_controller.py:898"]
    STEP_MODE["Step Mode<br/>raster_controller.py:898"]
    
    ENQUEUE_INIT["_enqueue_next_raster_point<br/>raster_controller.py:1527-1551"]
    
    STEP_ARM["Raster armed<br/>No motion yet"]
    
    USER_STEP["User clicks<br/>raster_step_button<br/>ui.py:637"]
    
    RASTER_STEP["raster_step<br/>raster_controller.py:919-959<br/>next(it) inside lock<br/>Enqueue MOVE_TARGET<br/>tag=raster_step"]
    
    MOTOR_QUEUE["Motor FIFO<br/>_motor_worker_loop<br/>raster_controller.py:1068-1096"]
    
    EXECUTE["_execute<br/>raster_controller.py:1119-1369<br/>Call motor_x/y.move_to<br/>Cache positions<br/>Log to _raster_log:1359-1367"]
    
    DELIVER["_deliver_result<br/>raster_controller.py:1401-1429<br/>Emit command_done_signal:1410<br/>Motor/target pos signals:1412-1415"]
    
    CMD_DONE["_on_command_done<br/>raster_controller.py:1500-1523<br/>Check tag==raster_step<br/>Increment _raster_step_count:1507"]
    
    CHECK_CONT{"Continuous &<br/>ok result?<br/>line:1512-1514"}
    
    DELAY{"Delay > 0?<br/>line:1520"}
    
    TIMER["QTimer.singleShot<br/>_raster_delay_s ms<br/>raster_controller.py:1521"]
    
    ENQUEUE_NEXT["_enqueue_next_raster_point<br/>raster_controller.py:1527-1551<br/>next(it) with lock<br/>OR StopIteration"]
    
    STOP_ITER{"StopIteration?<br/>line:1538"}
    
    FINISH["_finish_raster<br/>raster_controller.py:1553-1561<br/>Set _raster_active=False<br/>Emit raster_state_signal<br/>raster_finished_signal"]
    
    FLUSH["_flush_raster_log<br/>raster_controller.py:1563-1575<br/>Write JSON log"]
    
    UI_STATE["_on_raster_state<br/>ui.py:1539-1576<br/>Update button states<br/>Update UI"]
    
    UI_STEP_RE["_on_command_done<br/>ui.py:700-703<br/>Re-enable Step button"]
    
    UI_ERROR{"ok result?<br/>line:702"}
    
    ERROR_HALT["Status: Raster halted<br/>Stop raster<br/>line:1516-1517"]
    
    UI_START --> BUILD_SPEC
    BUILD_SPEC --> INIT_STATE
    INIT_STATE --> DECISION
    
    DECISION -->|continuous=True| CONTINUOUS
    DECISION -->|continuous=False| STEP_MODE
    
    CONTINUOUS --> ENQUEUE_INIT
    STEP_MODE --> STEP_ARM
    
    ENQUEUE_INIT --> MOTOR_QUEUE
    
    STEP_ARM --> USER_STEP
    USER_STEP --> RASTER_STEP
    RASTER_STEP --> MOTOR_QUEUE
    
    MOTOR_QUEUE --> EXECUTE
    EXECUTE --> DELIVER
    DELIVER --> CMD_DONE
    
    CMD_DONE --> CHECK_CONT
    CMD_DONE --> UI_STEP_RE
    
    UI_STEP_RE --> UI_ERROR
    UI_ERROR -->|False| ERROR_HALT
    UI_ERROR -->|True| UI_STEP_RE
    
    CHECK_CONT -->|Not continuous or error| STEP_ARM
    CHECK_CONT -->|Continuous & ok| DELAY
    
    DELAY -->|Yes| TIMER
    DELAY -->|No| ENQUEUE_NEXT
    
    TIMER --> ENQUEUE_NEXT
    
    ENQUEUE_NEXT --> STOP_ITER
    STOP_ITER -->|No| MOTOR_QUEUE
    STOP_ITER -->|Yes| FINISH
    
    FINISH --> FLUSH
    FLUSH --> UI_STATE
    
    ERROR_HALT --> UI_STATE
```

## Side effects
- Motor move_to() calls (motor_x, motor_y DLL access via dedicated worker thread)
- Command queue operations (PriorityQueue enqueue/dequeue)
- Position caching (_last_motor_xy, _last_target_xy)
- Raster logging to _raster_log list and JSON file write on finish
- Qt signals emitted (command_done_signal, motor_position_signal, target_position_signal, raster_state_signal, raster_finished_signal)
- QTimer.singleShot for continuous-mode delay between points
- Threading: motor_worker_loop thread dequeues commands, GUI thread chains via _on_command_done
- State mutations under _state_lock (_raster_active, _raster_continuous, _raster_step_count, _raster_iter)

## External deps
- raster_paths.RasterSpec, iter_path_from_spec, collect_points (path generation)
- PyQt5 signals/slots (command_done_signal, raster_state_signal, status_signal)
- QTimer for async delays
- Motor hardware interface (motor_x.move_to, motor_y.move_to)
- numpy (position transforms)
- json (log serialization)
- threading (locks, worker thread coordination)

## Sources read
- raster_controller.py:878-916 (start_raster init)
- raster_controller.py:919-959 (raster_step)
- raster_controller.py:1068-1096 (_motor_worker_loop)
- raster_controller.py:1119-1369 (_execute)
- raster_controller.py:1359-1367 (raster logging)
- raster_controller.py:1401-1429 (_deliver_result)
- raster_controller.py:1500-1523 (_on_command_done)
- raster_controller.py:1527-1551 (_enqueue_next_raster_point)
- raster_controller.py:1553-1561 (_finish_raster)
- raster_controller.py:1563-1575 (_flush_raster_log)
- ui.py:676-698 (_step_raster)
- ui.py:700-704 (_on_command_done)
- ui.py:1003-1037 (_start_raster)
- ui.py:1539-1576 (_on_raster_state)

## Confidence
High — traced all primary paths (continuous loop, step mode, termination, command chaining, logging) through controller and UI. Read exact line ranges for all methods. One-shot generator constraint confirmed as critical architectural decision.

## Gaps
- Error handling in raster_step() only checks StopIteration; bounds checks happen in _execute() but no early termination in raster_step() itself
- No explicit timeout or watchdog on individual raster steps; relies on motor DLL timeout
- ZMQ move_to_next path (line 1757) is synchronous wait=True; contrast with UI path (wait=False)
- _display_bounds comment at ui.py:933 suggests set_target_bounds() is unimplemented
- One-shot generator constraint (_raster_iter) means start_raster() cannot be re-armed without reconstructing the iterator
