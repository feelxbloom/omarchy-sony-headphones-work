# Helper map: `bin/sony-headphones`

A symbol index of the single stdlib-only helper (~4,100 lines). The file is deliberately
one piece, so no module split tells you where anything lives; this map does.

**How to use this.** Grep for the symbol name (`rg -n 'def apply_setting' bin/sony-headphones`)
and read only that region, plus maybe one caller. The names are the stable part; line
numbers are not. If a line range here looks wrong, re-grep by symbol name before
editing. Full-line security rationale lives in `docs/adr/` and `docs/architecture.md`.

## Module constants and limits

| Symbol | Role |
| --- | --- |
| `HEADER` / `TRAILER` / `ESCAPE` / `ESCAPE_MASK` | Frame marker bytes |
| `MSG_ACK` / `MSG_COMMAND_1` / `MSG_COMMAND_2` | Message-table selectors |
| `MAX_MESSAGE_SIZE` | Largest acceptable frame |
| `SERVICE_UUID` / `SERVICE_UUID_V2` | v1 / v2 SPP service UUIDs |
| `SDP_PSM` … `SDP_MAX_DEPTH` | SDP constants and parse bounds |
| `CACHE_DIR` | Channel-cache directory under `XDG_CACHE_HOME` |
| `MAC_RE` | Strict Bluetooth address pattern |
| `DISCOVERY_TTL` | How long a device scan is trusted (2 s) |
| `INFO_MAX_LINES` | Cap on `bluetoothctl info` lines scanned by `service_protocol` |
| `LOG_FILE_NAME` / `LOG_MAX_BYTES` / `LOG_BACKUPS` / `LOG_DEFAULT` / `LOG_OFF` / `LOG_LEVELS` | Log-file bounds and level map |
| `SETTLE_TIMEOUT` | Read-back window after a write (2 s) |
| `SOCKET_NAME` / `LOCK_NAME` | Control socket and lock file names |
| `SESSION_POLICIES` / `SESSION_POLICY_DEFAULT` / `SESSION_IDLE_DEFAULT` / `SESSION_IDLE_MIN` / `SESSION_IDLE_MAX` | Control-session policy values and idle-delay bounds |
| `MAX_LINE_BYTES` | Cap on one JSON line over the socket |

## Binary framing

| Symbol | Role |
| --- | --- |
| `ProtocolError` | A malformed frame; recoverable, drop and read on |
| `escape` / `unescape` | Byte-stuff and unstuff marker bytes |
| `checksum` | Plain byte sum from type through the last payload byte |
| `encode_message` | `(type, seq, payload)` to a framed message |
| `decode_message` | A framed message to `(type, seq, payload)` |

## Wire opcodes and option tables

| Symbol | Role |
| --- | --- |
| v1 opcode block (`INIT_REQUEST` … `VOICE_NOTIFICATIONS_NOTIFY`) | v1 ("MDR") opcodes |
| v2 opcode block (`V2_INIT_REQUEST` … `V2_PERI_SUB_SOURCE_SWITCH`) | v2 opcodes and subtype selectors |
| `AUDIO_CODECS` | Codec byte to name |
| `BATTERY_SINGLE` / `BATTERY_CASE` | Battery subtypes |
| `NC_MODES` / `ASC_MODE_CODE` / `ASC_MODE_FROM_CODE` | Noise-control modes, with and without wind |
| `EQ_PRESETS` / `EQ_PRESET_FROM_CODE` | v1 equalizer table |
| `V2_EQ_PRESETS` / `V2_EQ_PRESET_FROM_CODE` / `V2_EQ_BAND_*` | v2 equalizer table and band limits |
| `AUTO_POWER_OFF` / `V2_AUTO_POWER_OFF` (+ `_FROM_CODE`) | Auto power off values per generation |
| `STC_SENSITIVITY` / `STC_TIMEOUT` (+ `_FROM_CODE`) | Speak-to-chat options |
| `V2_BGM_ROOM` / `V2_BGM_ROOM_FROM_CODE` | Background-music room sizes |
| `BGM_WRITE_KEYS` / `BGM_RESET_REASON` | BGM keys whose lost link is explained as a digital assistant |
| `V2_CONNECTION_QUALITY_*` | Connection-quality values |
| `MAX_AMBIENT_LEVEL` | Ambient slider ceiling |
| `V2_ASC_SUBTYPES` / `V2_ASC_PROBE_ORDER` | v2 ambient dialect probe order |

## Request builders

| Symbol | Role |
| --- | --- |
| `req` | Wrap a payload as a `(msg_type, payload)` request |
| `refresh_requests` | Full post-connect v1 query list |
| `finite_int` | Parse a bounded integer setting |
| `asc_request` | v1 noise-control / ambient request |
| `eq_preset_request` / `eq_bands_request` | v1 equalizer writes |
| `bool_request` | Generic v1 on/off write |
| `auto_power_off_request` | v1 auto power off |
| `stc_config_request` | v1 speak-to-chat config |
| `v2_audio_codec_get` / `v2_dsee_get` / `v2_dsee_request` / `v2_connection_quality_get` / `v2_connection_quality_request` / `v2_cinema_get` / `v2_cinema_request` / `v2_bgm_get` / `v2_bgm_request` | v2 audio-family builders |
| `v2_asc_request` / `v2_asc_get` | v2 noise-control / ambient |
| `v2_eq_get` / `v2_eq_preset_request` / `v2_eq_bands_request` | v2 equalizer |
| `v2_system_get` / `v2_stc_enabled_request` / `v2_bool_request` / `v2_stc_config_request` / `v2_auto_power_off_request` / `v2_stc_get` / `v2_apo_get` | v2 system / speak-to-chat |
| `v2_device_list_get` / `v2_source_switch_request` | v2 multipoint |
| `v2_refresh_requests` | Full post-connect v2 query list |

## Reply parsers and state

| Symbol | Role |
| --- | --- |
| `initial_state` | The complete empty state dict (the JSON contract), with empty `pending: []` and `refused: {}` |
| `apply_payload` | Fold one v1 reply/notification into state |
| `apply_payload_v2` | Fold one v2 reply/notification into state |
| `_apply_firmware` / `_apply_codec` / `_apply_battery` | Small shared field parsers |
| `parse_v2_device_list` | Decode the v2 multipoint peer list |
| `derive_listening_mode` | BGM/cinema flags to one listening mode |
| `_bool` | Byte to `True`/`False`/`None` |

## SDP discovery

| Symbol | Role |
| --- | --- |
| `SdpError` | Malformed, oversized or unfinished SDP answer |
| `_de_sequence` / `_de_uuid128` / `_de_uint32` | SDP data-element encoders |
| `_parse_element` | Recursive SDP data-element decoder, depth-capped |
| `_find_rfcomm_channel` | First valid RFCOMM channel in a record |
| `sdp_query` | Bounded service-search loop on an SDP socket |
| `parse_sdp_record` | Top-level record decode |
| `sdp_channel` | Address + UUID to RFCOMM channel, or `None` |

## Channel cache (on disk)

| Symbol | Role |
| --- | --- |
| `_channel_cache_path` | Per-MAC cache file path |
| `cached_channel` | Read the remembered channel (`O_NOFOLLOW`) |
| `private_cache_dir` | Create/tighten the 0700 cache directory, or `None` |
| `remember_channel` | Write the last working channel at 0600 |
| `forget_channel` | Drop a stale channel after a failed connect |

## Bluetooth discovery (`bluetoothctl`)

| Symbol | Role |
| --- | --- |
| `_clean_name` | Strip controls, squeeze whitespace, bound length, fall back to address |
| `find_bluetoothctl` / `BLUETOOTHCTL` / `BLUETOOTHCTL_CANDIDATES` / `BLUETOOTHCTL_ENV` | Resolve `bluetoothctl` once, run it in a minimal environment |
| `bluetoothctl` | Run a `bluetoothctl` subcommand, return stdout |
| `service_protocol` | Read v1/v2 from the `info` UUID list |
| `_normalize_mac` | Case/separator-insensitive cache key |
| `_DiscoveryCache` / `_DISCOVERY` | In-memory device-snapshot and protocol-hint cache |
| `connected_devices` | Connected Sony devices, briefly cached |
| `find_device` | Pick the preferred or first connected device |

## Transport classes

| Symbol | Role |
| --- | --- |
| `Transport` | Abstract byte-mover: `open`/`send`/`recv`/`close`/`connected` |
| `RfcommTransport` | Real radio: SDP candidates, RFCOMM sockets, cached fallback |
| `RfcommTransport._candidates` | Yield control channels in priority order |
| `RfcommTransport._open_channel` | Build one blocking RFCOMM socket |
| `DemoTransport` | Loopback transport speaking the real wire format to a stand-in |

## Protocol adapters

| Symbol | Role |
| --- | --- |
| `Protocol` | The adapter interface Link talks to |
| `V1Protocol` | v1 adapter: delegates to the v1 builders/parsers |
| `V2Protocol` | v2 adapter: delegates to the v2 builders/parsers |

## Link (the conversation)

| Symbol | Role |
| --- | --- |
| `NotConnected` | The peer is gone; the failure signal throughout |
| `Link` | One lock-step conversation over a transport |
| `Link.interrupted_key` | A BGM key whose write raised, for `Daemon.lose_link` to explain |
| `Link.connect` | Open the transport, establish, keep the channel |
| `Link._establish` | Handshake, features and dialect negotiation for one candidate |
| `Link._handshake` | INIT exchange; length decides v1 (4) vs v2 (8) |
| `Link._set_protocol` | Adopt the confirmed adapter |
| `Link.close` | Close the transport and mark disconnected |
| `Link._read_frame` / `Link._trim_buffer` | Framing reads and buffer bounding |
| `Link.write` / `Link.wait_for_ack` / `Link._ack` | Lock-step writes and ACKs |
| `Link.dispatch` / `Link.pump` | Fold frames into state; pump for a window |
| `Link.notify_change` | Fan a state change made outside dispatch out to the owner via `on_change` |
| `Link.request` / `Link.refresh` | Send a request list and settle |
| `Link._select_subtype` / `select_asc_subtype` / `select_eq_subtype` / `select_bgm_subtype` | v2 dialect probes |
| `Link.poll_requests` / `Link.power_off` | Periodic liveness ask; power off via the adapter |
| `configure_link` | Stamp device identity, then `Link.connect` |

## Settings builders

| Symbol | Role |
| --- | --- |
| `BOOL_SETTINGS` / `SETTING_KEYS` | Toggle setting map; the CLI's accepted keys |
| `parse_bool` | Boolean parser incl. `toggle` |
| `next_nc_mode` | NC / ambient / off cycle |
| `SETTING_FEATURES` | Setting key to required feature |
| `V1_ONLY_SETTINGS` / `V2_ONLY_SETTINGS` | Keys each builder refuses across generations |
| `SettingContext` | Named tuple of the shared preamble fields |
| `_setting_context` | Shared gate: exclusivity, features, ambient and v2 discovery fields |
| `setting_requests` | v1: key + value to requests |
| `setting_requests_v2` | v2: key + value to requests |
| `apply_setting` | Mark the key pending (clearing a prior refusal), write then pump until the read-back moves or `SETTLE_TIMEOUT`, recording a refusal on a no-move settle; a BGM key that raises is remembered in `Link.interrupted_key` |
| `_mark_pending` / `_settle_pending` | Publish/clear the `pending` key and record a `refused` entry |

## Feature tables and ceilings

| Symbol | Role |
| --- | --- |
| `V1_FEATURES` / `V2_FEATURES` | Per-generation command-set ceilings |
| `FEATURE_CEILINGS` | Protocol to ceiling |
| `FEATURE_SETS` | Per-model refinements, checked against the ceiling at import |
| `ALL_FEATURES` | Union, only for a device with no known protocol |
| `features_for` | The controls a named device should be offered |

## Demo mode

| Symbol | Role |
| --- | --- |
| `DemoDevice` / `DemoLink` | v1 stand-in device and link |
| `DemoDeviceV2` / `DemoLinkV2` | v2 stand-in device and link |
| `DemoDevice.stubborn` / `DemoDeviceV2.stubborn` | Opt-in flag (off by default) that acknowledges a write without changing the value |
| `demo_mode` | Read `SONY_HEADPHONES_DEMO`; `v1`, `v2` or off |
| `demo_link` | Build the stand-in Link for the selected demo |

## Logging and the trace file

| Symbol | Role |
| --- | --- |
| `_open_trace_file` / `_TRACE_FILE` / `trace` | Hardened frame trace, off unless `SONY_HEADPHONES_TRACE` |
| `LOG` | The one module-level named logger |
| `_LogFormatter` | Log line shape |
| `_PrivateLogFile` | Rotating 0600 handler |
| `_open_log_handler` | Build the handler, or `None` |
| `_log_level_name` / `log_level` | Resolve the level name |
| `configure_logging` | Configure once, then only move the handler's level |

## Runtime directory and socket

| Symbol | Role |
| --- | --- |
| `is_private_dir` | Real 0700 directory owned by this user |
| `runtime_dir` | Validated `XDG_RUNTIME_DIR`, or a private fallback |
| `socket_path` | The control socket path |

## The daemon

| Symbol | Role |
| --- | --- |
| `Daemon` | Holds the link open and lends it over a unix socket |
| `Daemon.POLL_INTERVAL` / `RETRY_MIN` / `RETRY_MAX` / `REQUEST_TIMEOUT` / `MAX_SUBSCRIBERS` / `SUBSCRIBER_TIMEOUT` | Timing and subscriber bounds |
| `_env_session_policy` / `_env_session_idle` | Read the boot policy from the environment, with safe defaults |
| `Daemon.state` | Link state, or a disconnected state, with the daemon fields stamped |
| `Daemon._stamp` | Overlay logging + session policy onto a state dict, plus any `reset_refusal` |
| `Daemon.publish` | Fan one state line out to subscribers |
| `Daemon.drop` | Remove and close one subscriber |
| `Daemon.try_connect` | Find a device and open the link, with backoff |
| `Daemon.lose_link` | Close, clear and publish a disconnected state; a link lost on a BGM write records `Daemon.reset_refusal` |
| `Daemon.release` | Hand the control session back deliberately, keeping last values |
| `Daemon.reclaim` | Take the control session back and refresh it |
| `Daemon.release_if_idle` | Release an on-demand session after its quiet spell |
| `Daemon.poll_link` | Periodic liveness request, kept out of the run loop |
| `Daemon.set_session` | Validate and apply a runtime policy/idle change |
| `Daemon.with_link` | Run an action, reconnecting or reclaiming first if needed |
| `Daemon.handle_command` | Dispatch one request dict to a response dict |
| `Daemon.accept` | Read one client request, subscribe or answer |
| `Daemon._reply` | Send one JSON response and hang up |
| `Daemon.listen` | Claim the daemon role via lock and socket |
| `Daemon.claim_lock` | Take the exclusive lock, or refuse to start |
| `Daemon.bind_socket` | Bind the 0600 socket through the directory fd |
| `Daemon.remove_stale_socket` | Unlink a dead daemon's socket, and only that |
| `Daemon.run` | The select loop: accepts, pumps, polls, backoff |

## Talking to the daemon

| Symbol | Role |
| --- | --- |
| `daemon_socket` | Connect to the control socket, or `None` |
| `ask_daemon` | Send one request, read one response, or `None` |
| `emit` | Write one JSON line to stdout and return it |
| `_command_summary` | One log-sized description of a request |
| `apply_command` | Run one request directly on a link |
| `direct` | Do it ourselves when no daemon is running |
| `run_request` | Daemon if present, else `direct` |

## CLI subcommands

| Symbol | Role |
| --- | --- |
| `describe` | Human-readable state block |
| `cmd_watch` | Subscribe to a daemon, or become one |
| `cmd_status` | `status` (`--json` or human) |
| `cmd_set` / `cmd_cycle` / `cmd_power_off` | Device-write subcommands |
| `cmd_release` / `cmd_reclaim` / `cmd_session` | Control-session subcommands |
| `_json_state` | Merge a response's refusal reason into emitted state |
| `cmd_logging` | Show or change the daemon's log level |
| `_report` | Shared JSON/stderr reporting for write subcommands |
| `cmd_probe` | Connection diagnostics |
| `build_parser` | argparse wiring; the subcommand list |
| `main` | Entry point |
