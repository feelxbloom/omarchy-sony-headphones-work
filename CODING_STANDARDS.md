# Coding Standards

These are the judgement calls a reviewer enforces. The mechanical checks live in
`make lint` / `make check`; the security and wire-format rules are recorded as ADRs under
`docs/adr/`, and this file points at them rather than restating them.

A change is reviewed on two axes: **Standards** (this file plus the ADRs) and **Spec**
(the acceptance criteria in the originating ticket).

## The helper (`bin/sony-headphones`)

- **One self-contained file, stdlib only.** It is launched as
  `/usr/bin/python3 -I <plugin>/bin/sony-headphones`, so the script directory is not on
  `sys.path`. No local imports, no packaging, no new runtime dependencies (ADR-0001,
  ADR-0002).
- **Wire formats are frozen.** Opcodes, byte layouts, escaping, checksum order and the
  ACK discipline are contracts. A change that alters a wire byte needs captured evidence
  and belongs behind the `Protocol` adapter for its generation; the two adapters share an
  interface, never a layout (ADR-0006).
- **Every parser input is bounded.** Frames, SDP records, continuations, device-list
  entries, request lines and log lines all have caps. A new branch checks its length
  before indexing (ADR-0004 and the daemon bounds).
- **Socket values are typed, whole and in range.** A scalar that arrives over the control
  socket or in JSON is validated for its type and integrality, not just finiteness:
  `True` is an `int` and a float truncates silently, so neither is a valid count. Reject
  the wrong shape at the boundary rather than coercing it (ADR-0004).
- **An acknowledgement is not agreement.** A write the headset ACKs may still be
  discarded; only a read-back from a fresh session proves it. Never present an ACK as
  confirmation.
- **Do not weaken the security invariants.** Isolated interpreter, minimal environment,
  absolute `bluetoothctl`, `O_NOFOLLOW`/0700 private directories, 0600 logging, bounded
  parsing (ADR-0001–0003, 0007).
- **Comments explain why.** Record the reasoning and the approaches that failed; protocol
  rationale and security reasoning are load-bearing and must survive refactors. Do not
  restate what the code already says.

## The panel (`Panel.qml`, `Service.qml`, `Model.js`)

- **Capability decisions are pure and in `Model.js`** (`rowsFor`, `hasRow`, label
  helpers) so the node harness can test them. `Panel.qml` renders; it does not decide
  what a device can do.
- **State-derived text is plain text.** Untrusted strings are sanitized once, at ingest,
  in the helper; the QML never re-trusts them and never uses rich text for them.
- **One action, one helper process.** The widget parses the `--json` reply; it does not
  spawn a follow-up `status` after a successful action.
- **Settings cross five places:** manifest schema, `Panel.qml`, `Service.qml`, the helper,
  and `docs/agents.md` plus tests. Missing one is the usual bug.

## Tests

- **Test external behaviour through the same seam the caller uses:** the daemon control
  socket, the `Protocol`/`Transport` seams, `Model.js`. A test that reaches past the
  interface is the wrong shape.
- **Never touch real hardware.** Demo mode and a throwaway `XDG_RUNTIME_DIR` always; no
  test may open the machine's real daemon socket.
- **Never write the real cache or log either.** A throwaway `XDG_RUNTIME_DIR` is not
  enough: `main()` opens the log under `CACHE_DIR`, and the daemon writes its channel cache
  there. Point `CACHE_DIR` (and any handler built from it) at a temp directory, as
  `tests/test_daemon.py` does, or set a throwaway `XDG_CACHE_HOME`.
- **Wire-byte tests are contracts.** If one fails, the code is wrong, not the test.
- **New parser branch → new fixture; new setting → tests for both protocols where it
  applies.** Shared fakes live in `tests/support.py` (`FakeClock`, `FakeStream`,
  `SourceFileLoader`); reuse them, and the test-helper mixins, instead of re-defining a
  helper such as `run_main` in another class.
- The gate is `make check`: Python suite, JS harness, lint, and plugin validation.

## Changes to the trust boundary

Anything that touches the parser, the control socket, a subprocess call, filesystem paths,
or the environment is a trust-boundary change. Read the threat-model ADR
(`docs/adr/0009-bluetooth-threat-model.md`) first, and apply its
checklist: untrusted input bounded, strings sanitized at ingest, no shell interpolation,
no path built from untrusted input, no secret or MAC logged unredacted.
