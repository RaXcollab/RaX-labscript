---
name: v2-message-alias-substring-gates
description: v2 did NOT kill message-substring gates in RemoteControl workers — program_value aliases error.message into response["message"], and today's GUI texts still contain the old substrings. Two audits have wrongly called these gates "dead".
metadata:
  type: reference
---

`RemoteCommunication.program_value` / `check_remote_value`
(`userlib/user_devices/RemoteControl/blacs_workers.py:371-395`) catch
`RemoteRequestError` and translate it back to a v1-shaped dict:
`{"status", "value": None, "error", "message": exc.message}` where
`exc.message == error["message"]`. So **`response["message"]` is the v2
`error.message`, always populated on failures** — a substring gate on it
is *not* dead after the v2 cutover.

Today's GUI error texts still contain the legacy substrings verbatim:
- `HugeSkyController.pyw` PROGRAM_VALUE: `"unknown connection '%s'"`, `"laser disconnected"`
- every `BigSkyControllerAmbitious.py` REJECTED site builds `msg = "rejected: ..."`

Consequences:
- Claims that the old BigSky `program_manual` substring gates "went dead
  when v2 moved the reason into error.code" are **false** (2026-08-04 audit
  corrected this; the claim still appears in docstrings until fixed).
- **Load-bearing:** `should_skip_buffered_response`
  (`userlib/user_devices/BigSkyHub/blacs_workers.py:39,62`) relies on
  `_SKIP_ERROR_SUBSTRINGS` to tolerate `laser_disconnected`, because that
  reply is `status=ERROR` and only `{UNKNOWN_CONNECTION, REJECTED}` are in
  `_SKIP_STATUSES`. Deleting the substring tuple as "dead v1 code" makes an
  offline YAG hard-fail every queued shot. Replace it with a typed
  `error.code` check first, never just delete.
- Other surviving substring sites are log-level-only (both branches take the
  same action): `BigSkyHub/blacs_workers.py:189` (`_arm_laser`, on `str(exc)`)
  and `:547` (`_verify_armed_state`).

Prefer typed gates (`response["status"]`, `response["error"]["code"]`) —
`_check_response` raises a *plain* `Exception`, so the typed fields survive
only on the `response` dict, which is why error hooks must receive it.
