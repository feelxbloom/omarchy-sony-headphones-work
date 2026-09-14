#!/usr/bin/env python3
"""Protocol tests that need no headphones.

Everything here is byte-level: framing, the shape of each request, and folding
replies into state. The parts that need a real device (channel discovery, the
daemon, reconnects) are covered by `sony-headphones probe`.

Run with: python3 tests/test_protocol.py
"""

import importlib.util
import os
import shutil
import socket
import stat
import sys
import tempfile
import unittest
from unittest import mock

HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "sony-headphones")
spec = importlib.util.spec_from_loader("sonyhp", importlib.machinery.SourceFileLoader("sonyhp", HELPER))
sonyhp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sonyhp)


class TestFraming(unittest.TestCase):
    def test_escapes_marker_bytes(self):
        self.assertEqual(sonyhp.escape(bytes([0x3E, 0x3C, 0x3D])), bytes([0x3D, 0x2E, 0x3D, 0x2C, 0x3D, 0x2D]))

    def test_unescape_reverses_escape(self):
        for raw in (bytes(range(0x30, 0x50)), bytes([0x3D] * 4), b"", bytes([0x3C, 0x3C])):
            self.assertEqual(sonyhp.unescape(sonyhp.escape(raw)), raw)

    def test_known_frame_matches_the_wire(self):
        # Ambient sound control set, sequence 0, captured shape from the docs:
        # header, type, seq, 4-byte length, payload, checksum, trailer.
        frame = sonyhp.encode_message(sonyhp.MSG_COMMAND_1, 0, bytes([0x68, 0x02, 0x11, 0x02, 0x02, 0x01, 0x00, 0x00]))
        self.assertEqual(frame.hex(), "3e0c0000000008680211020201000094" + "3c")

    def test_round_trip(self):
        payload = bytes([0x68, 0x3E, 0x3C, 0x3D])
        msg_type, seq, decoded = sonyhp.decode_message(sonyhp.encode_message(sonyhp.MSG_COMMAND_1, 1, payload))
        self.assertEqual((msg_type, seq, decoded), (sonyhp.MSG_COMMAND_1, 1, payload))

    def test_ack_is_an_empty_payload(self):
        self.assertEqual(sonyhp.decode_message(sonyhp.encode_message(sonyhp.MSG_ACK, 1, b"")), (sonyhp.MSG_ACK, 1, b""))

    def test_rejects_bad_checksum(self):
        frame = bytearray(sonyhp.encode_message(sonyhp.MSG_COMMAND_1, 0, bytes([0x10, 0x00])))
        frame[-2] ^= 0xFF
        with self.assertRaises(sonyhp.ProtocolError):
            sonyhp.decode_message(bytes(frame))

    def test_rejects_missing_markers(self):
        with self.assertRaises(sonyhp.ProtocolError):
            sonyhp.decode_message(b"\x0c\x00")

    def test_rejects_length_mismatch(self):
        body = bytes([sonyhp.MSG_COMMAND_1, 0]) + (9).to_bytes(4, "big") + bytes([0x10, 0x00])
        frame = bytes([sonyhp.HEADER]) + sonyhp.escape(body + bytes([sonyhp.checksum(body)])) + bytes([sonyhp.TRAILER])
        with self.assertRaises(sonyhp.ProtocolError):
            sonyhp.decode_message(frame)


class TestRequests(unittest.TestCase):
    def test_noise_cancelling(self):
        _, payload = sonyhp.asc_request("noise-cancelling", 12, False, True)
        self.assertEqual(list(payload), [0x68, 0x02, 0x11, 0x02, 0x02, 0x01, 0x00, 0x00])

    def test_ambient_carries_level_and_voice_focus(self):
        _, payload = sonyhp.asc_request("ambient-sound", 15, True, True)
        self.assertEqual(list(payload), [0x68, 0x02, 0x11, 0x02, 0x00, 0x01, 0x01, 15])

    def test_off(self):
        _, payload = sonyhp.asc_request("off", 5, False, True)
        self.assertEqual(list(payload), [0x68, 0x02, 0x00, 0x02, 0x00, 0x01, 0x00, 5])

    def test_wind_noise_reduction(self):
        _, payload = sonyhp.asc_request("wind-noise-reduction", 0, False, True)
        self.assertEqual(payload[4], 0x01)

    def test_device_without_wind_support_uses_the_short_mode_table(self):
        _, payload = sonyhp.asc_request("noise-cancelling", 0, False, False)
        self.assertEqual(list(payload[3:5]), [0x00, 0x01])

    def test_wind_is_refused_when_unsupported(self):
        with self.assertRaises(ValueError):
            sonyhp.asc_request("wind-noise-reduction", 0, False, False)

    def test_level_is_clamped(self):
        _, payload = sonyhp.asc_request("ambient-sound", 99, False, True)
        self.assertEqual(payload[7], sonyhp.MAX_AMBIENT_LEVEL)

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            sonyhp.asc_request("quiet-please", 0, False, True)

    def test_equalizer_preset(self):
        _, payload = sonyhp.eq_preset_request("bass-boost")
        self.assertEqual(list(payload), [0x58, 0x01, 0x16, 0x00])

    def test_equalizer_custom_bands_are_offset_by_ten(self):
        _, payload = sonyhp.eq_bands_request(-10, [0, 10, -5, 5, 1])
        self.assertEqual(list(payload), [0x58, 0x01, 0xFF, 0x06, 0, 10, 20, 5, 15, 11])

    def test_equalizer_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            sonyhp.eq_bands_request(0, [0, 0, 0, 0, 11])

    def test_auto_power_off(self):
        _, payload = sonyhp.auto_power_off_request("when-taken-off")
        self.assertEqual(list(payload), [0xF8, 0x04, 0x01, 0x10, 0x00])

    def test_speak_to_chat_config(self):
        _, payload = sonyhp.stc_config_request("high", True, "long")
        self.assertEqual(list(payload), [0xFC, 0x05, 0x00, 0x01, 0x01, 0x02])

    def test_refresh_asks_for_everything_once(self):
        requests = sonyhp.refresh_requests()
        opcodes = [payload[0] for _, payload in requests]
        self.assertEqual(len(opcodes), len(set(opcodes)) + 2)  # the 0xf6 family repeats, with different sub-types
        self.assertIn(sonyhp.ASC_GET, opcodes)
        self.assertIn(sonyhp.BATTERY_GET, opcodes)


class TestReplies(unittest.TestCase):
    def setUp(self):
        self.state = sonyhp.initial_state()

    def apply(self, payload, msg_type=None):
        return sonyhp.apply_payload(self.state, msg_type or sonyhp.MSG_COMMAND_1, bytes(payload))

    def test_ambient_sound_control(self):
        self.assertTrue(self.apply([0x67, 0x02, 0x01, 0x02, 0x00, 0x01, 0x01, 0x11]))
        self.assertEqual(self.state["nc_mode"], "ambient-sound")
        self.assertEqual(self.state["ambient_level"], 17)
        self.assertIs(self.state["focus_on_voice"], True)
        self.assertIs(self.state["supports_wind"], True)

    def test_ambient_sound_control_noise_cancelling(self):
        self.apply([0x67, 0x02, 0x01, 0x02, 0x02, 0x01, 0x00, 0x00])
        self.assertEqual(self.state["nc_mode"], "noise-cancelling")

    def test_ambient_sound_control_off(self):
        self.apply([0x67, 0x02, 0x00, 0x02, 0x00, 0x01, 0x00, 0x00])
        self.assertEqual(self.state["nc_mode"], "off")

    def test_ambient_sound_control_without_wind_support(self):
        self.apply([0x67, 0x02, 0x01, 0x00, 0x01, 0x01, 0x00, 0x00])
        self.assertEqual(self.state["nc_mode"], "noise-cancelling")
        self.assertIs(self.state["supports_wind"], False)

    def test_notification_is_parsed_like_a_reply(self):
        self.apply([0x69, 0x02, 0x01, 0x02, 0x02, 0x01, 0x00, 0x00])
        self.assertEqual(self.state["nc_mode"], "noise-cancelling")

    def test_battery(self):
        self.apply([0x11, 0x00, 0x5A, 0x01])
        self.assertEqual(self.state["battery"], 90)
        self.assertIs(self.state["charging"], True)

    def test_firmware(self):
        self.apply([0x05, 0x02, 0x05] + list(b"2.5.0"))
        self.assertEqual(self.state["firmware"], "2.5.0")

    def test_codec(self):
        self.apply([0x19, 0x00, 0x10])
        self.assertEqual(self.state["codec"], "LDAC")

    def test_equalizer(self):
        self.apply([0x57, 0x01, 0x16, 0x06, 12, 10, 11, 9, 10, 10])
        self.assertEqual(self.state["eq_preset"], "bass-boost")
        self.assertEqual(self.state["eq_bass"], 2)
        self.assertEqual(self.state["eq_bands"], [0, 1, -1, 0, 0])

    def test_dsee(self):
        self.apply([0xE7, 0x02, 0x00, 0x01])
        self.assertIs(self.state["dsee"], True)

    def test_ldac_is_not_mistaken_for_dsee(self):
        self.apply([0xE7, 0x01, 0x00, 0x01])
        self.assertIsNone(self.state["dsee"])

    def test_speak_to_chat_enabled(self):
        self.apply([0xF7, 0x05, 0x01, 0x01])
        self.assertIs(self.state["speak_to_chat"], True)

    def test_pause_when_taken_off(self):
        self.apply([0xF7, 0x03, 0x00, 0x01])
        self.assertIs(self.state["pause_when_taken_off"], True)

    def test_auto_power_off(self):
        self.apply([0xF7, 0x04, 0x01, 0x10, 0x00])
        self.assertEqual(self.state["auto_power_off"], "when-taken-off")

    def test_speak_to_chat_config(self):
        self.apply([0xFB, 0x05, 0x00, 0x02, 0x01, 0x03])
        self.assertEqual(self.state["stc_sensitivity"], "low")
        self.assertEqual(self.state["stc_timeout"], "off")
        self.assertIs(self.state["stc_focus_on_voice"], True)

    def test_touch_sensor(self):
        self.apply([0xD7, 0xD2, 0x01, 0x00])
        self.assertIs(self.state["touch_sensor"], False)

    def test_voice_notifications_live_on_the_second_command_family(self):
        self.apply([0x47, 0x01, 0x01, 0x01], sonyhp.MSG_COMMAND_2)
        self.assertIs(self.state["voice_notifications"], True)

    def test_same_payload_twice_reports_no_change(self):
        payload = [0x11, 0x00, 0x5A, 0x00]
        self.assertTrue(self.apply(payload))
        self.assertFalse(self.apply(payload))

    def test_garbage_is_ignored(self):
        self.assertFalse(self.apply([0x99, 0x01, 0x02]))
        self.assertFalse(self.apply([]))

    def test_out_of_range_ambient_level_is_rejected(self):
        self.assertFalse(self.apply([0x67, 0x02, 0x01, 0x02, 0x00, 0x01, 0x00, 99]))
        self.assertIsNone(self.state["nc_mode"])


class TestSettings(unittest.TestCase):
    def test_cycle_order(self):
        self.assertEqual(sonyhp.next_nc_mode("noise-cancelling"), "ambient-sound")
        self.assertEqual(sonyhp.next_nc_mode("ambient-sound"), "off")
        self.assertEqual(sonyhp.next_nc_mode("off"), "noise-cancelling")
        self.assertEqual(sonyhp.next_nc_mode(None), "noise-cancelling")

    def test_setting_the_level_switches_out_of_noise_cancelling(self):
        state = sonyhp.initial_state()
        state.update(nc_mode="noise-cancelling", ambient_level=0, supports_wind=True)
        (_, payload), = sonyhp.setting_requests(state, "ambient-level", 8)
        self.assertEqual(payload[4], sonyhp.ASC_MODE_CODE["ambient-sound"])
        self.assertEqual(payload[7], 8)

    def test_voice_focus_keeps_the_current_mode_and_level(self):
        state = sonyhp.initial_state()
        state.update(nc_mode="ambient-sound", ambient_level=13, supports_wind=True)
        (_, payload), = sonyhp.setting_requests(state, "focus-on-voice", "true")
        self.assertEqual(list(payload[4:8]), [0x00, 0x01, 0x01, 13])

    def test_toggle_reads_the_current_value(self):
        state = sonyhp.initial_state()
        state["dsee"] = True
        (_, payload), = sonyhp.setting_requests(state, "dsee", "toggle")
        self.assertEqual(payload[3], 0x00)

    def test_bool_settings_accept_common_spellings(self):
        for text in ("on", "yes", "1", "true", "enabled"):
            self.assertIs(sonyhp.parse_bool(text), True)
        for text in ("off", "no", "0", "false", "disabled"):
            self.assertIs(sonyhp.parse_bool(text), False)

    def test_eq_bands_setting_parses_a_list(self):
        (_, payload), = sonyhp.setting_requests(sonyhp.initial_state(), "eq-bands", "0, 1, 2, 3, 4, 5")
        self.assertEqual(list(payload[4:]), [10, 11, 12, 13, 14, 15])

    def test_eq_bands_needs_six_values(self):
        with self.assertRaises(ValueError):
            sonyhp.setting_requests(sonyhp.initial_state(), "eq-bands", "1,2,3")

    def test_unknown_setting(self):
        with self.assertRaises(ValueError):
            sonyhp.setting_requests(sonyhp.initial_state(), "loudness", "on")

    def test_every_advertised_key_can_build_a_request(self):
        state = sonyhp.initial_state()
        state.update(nc_mode="ambient-sound", ambient_level=10, supports_wind=True)
        values = {
            "nc": "noise-cancelling", "ambient-level": "5", "focus-on-voice": "on",
            "eq": "vocal", "eq-bands": "0,0,0,0,0,0", "auto-power-off": "off",
            "stc-sensitivity": "auto", "stc-timeout": "short", "stc-focus-on-voice": "on",
            "voice-notifications": "on", "dsee": "on", "speak-to-chat": "on",
            "pause-when-taken-off": "on", "touch-sensor": "on",
        }
        self.assertEqual(sorted(values), sonyhp.SETTING_KEYS)
        for key, value in values.items():
            requests = sonyhp.setting_requests(state, key, value)
            self.assertTrue(requests, key)


class TestDemoDevice(unittest.TestCase):
    """Round trips through the stand-in device.

    Every request goes out through the real framing and comes back as a real
    reply payload, so these tests fail if an encoder and its parser ever stop
    agreeing — the failure mode that would otherwise only show up with
    headphones on your head.
    """

    def setUp(self):
        self.link = sonyhp.DemoLink()
        self.link.refresh()

    def test_refresh_fills_in_the_whole_state(self):
        state = self.link.state
        for key in ("firmware", "codec", "battery", "nc_mode", "ambient_level", "eq_preset",
                    "dsee", "speak_to_chat", "stc_sensitivity", "pause_when_taken_off",
                    "auto_power_off", "touch_sensor", "voice_notifications"):
            self.assertIsNotNone(state[key], key)

    def test_mode_changes_come_back_from_the_device(self):
        for mode in ("ambient-sound", "wind-noise-reduction", "off", "noise-cancelling"):
            sonyhp.apply_setting(self.link, "nc", mode)
            self.assertEqual(self.link.state["nc_mode"], mode)

    def test_cycle_walks_the_modes(self):
        sonyhp.apply_setting(self.link, "nc", "noise-cancelling")
        seen = []
        for _ in range(3):
            sonyhp.apply_setting(self.link, "nc", "cycle")
            seen.append(self.link.state["nc_mode"])
        self.assertEqual(seen, ["ambient-sound", "off", "noise-cancelling"])

    def test_ambient_level_survives_the_round_trip(self):
        sonyhp.apply_setting(self.link, "ambient-level", 17)
        self.assertEqual(self.link.state["ambient_level"], 17)
        self.assertEqual(self.link.state["nc_mode"], "ambient-sound")

    def test_focus_on_voice_does_not_disturb_the_level(self):
        sonyhp.apply_setting(self.link, "ambient-level", 6)
        sonyhp.apply_setting(self.link, "focus-on-voice", "on")
        self.assertIs(self.link.state["focus_on_voice"], True)
        self.assertEqual(self.link.state["ambient_level"], 6)

    def test_equalizer_preset(self):
        sonyhp.apply_setting(self.link, "eq", "speech")
        self.assertEqual(self.link.state["eq_preset"], "speech")

    def test_equalizer_custom_bands(self):
        sonyhp.apply_setting(self.link, "eq-bands", "3,-2,0,1,4,-1")
        self.assertEqual(self.link.state["eq_bass"], 3)
        self.assertEqual(self.link.state["eq_bands"], [-2, 0, 1, 4, -1])
        self.assertEqual(self.link.state["eq_preset"], "manual")

    def test_speak_to_chat_config(self):
        sonyhp.apply_setting(self.link, "stc-sensitivity", "low")
        sonyhp.apply_setting(self.link, "stc-timeout", "off")
        self.assertEqual(self.link.state["stc_sensitivity"], "low")
        self.assertEqual(self.link.state["stc_timeout"], "off")

    def test_auto_power_off(self):
        sonyhp.apply_setting(self.link, "auto-power-off", "when-taken-off")
        self.assertEqual(self.link.state["auto_power_off"], "when-taken-off")

    def test_every_toggle_flips_both_ways(self):
        for key, state_key in (("dsee", "dsee"), ("speak-to-chat", "speak_to_chat"),
                               ("pause-when-taken-off", "pause_when_taken_off"),
                               ("voice-notifications", "voice_notifications")):
            for value in (True, False):
                sonyhp.apply_setting(self.link, key, "on" if value else "off")
                self.assertIs(self.link.state[state_key], value, key)

    def test_settings_the_model_ignores_are_refused(self):
        # A WH-1000XM4 answers "still on" to every attempt at disabling its
        # touch panel, and "when taken off" to every timer, so do not ask.
        with self.assertRaises(ValueError):
            sonyhp.apply_setting(self.link, "touch-sensor", "off")
        with self.assertRaises(ValueError):
            sonyhp.apply_setting(self.link, "auto-power-off", "3-hour")
        sonyhp.apply_setting(self.link, "auto-power-off", "off")
        self.assertEqual(self.link.state["auto_power_off"], "off")


class TestFeatures(unittest.TestCase):
    def test_known_models(self):
        self.assertIn("speak-to-chat", sonyhp.features_for("WH-1000XM4"))
        self.assertNotIn("touch-sensor", sonyhp.features_for("WH-1000XM4"))
        self.assertNotIn("auto-power-off-timer", sonyhp.features_for("WH-1000XM4"))
        self.assertIn("touch-sensor", sonyhp.features_for("WH-1000XM3"))
        self.assertIn("auto-power-off-timer", sonyhp.features_for("WH-1000XM3"))
        self.assertNotIn("speak-to-chat", sonyhp.features_for("WH-1000XM3"))
        self.assertNotIn("auto-power-off", sonyhp.features_for("WH-1000XM2"))

    def test_the_name_only_has_to_contain_the_model(self):
        self.assertEqual(sonyhp.features_for("Gabriel's WH-1000XM4"), sonyhp.features_for("WH-1000XM4"))

    def test_an_unknown_device_gets_everything(self):
        self.assertEqual(set(sonyhp.features_for("WH-XB910N")), sonyhp.ALL_FEATURES)
        self.assertEqual(set(sonyhp.features_for(None)), sonyhp.ALL_FEATURES)


class TestRuntimeDirectory(unittest.TestCase):
    """The socket's parent has to be a directory only we can write.

    Anything that can reach the socket can drive the headphones, so these
    check the gate rather than the protocol.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def make(self, name, mode):
        path = os.path.join(self.tmp, name)
        os.mkdir(path, mode)
        os.chmod(path, mode)  # mkdir's mode is filtered through the umask
        return path

    def test_accepts_a_private_directory(self):
        self.assertTrue(sonyhp.is_private_dir(self.make("good", 0o700)))

    def test_rejects_group_or_world_access(self):
        for mode in (0o750, 0o770, 0o755, 0o777, 0o701):
            with self.subTest(mode=oct(mode)):
                self.assertFalse(sonyhp.is_private_dir(self.make(f"m{mode:o}", mode)))

    def test_rejects_a_symlink_even_to_a_private_directory(self):
        target = self.make("target", 0o700)
        link = os.path.join(self.tmp, "link")
        os.symlink(target, link)
        self.assertFalse(sonyhp.is_private_dir(link))

    def test_rejects_a_file_and_a_missing_path(self):
        regular = os.path.join(self.tmp, "file")
        open(regular, "w").close()
        self.assertFalse(sonyhp.is_private_dir(regular))
        self.assertFalse(sonyhp.is_private_dir(os.path.join(self.tmp, "nope")))

    def test_uses_a_valid_xdg_runtime_dir(self):
        good = self.make("xdg", 0o700)
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": good}):
            self.assertEqual(sonyhp.runtime_dir(), good)

    def temp_root(self):
        """Point the fallback at our sandbox.

        gettempdir() caches its answer on first use, so setting TMPDIR in the
        environment would steer nothing; the lookup itself is what has to move.
        """
        return mock.patch.object(sonyhp.tempfile, "gettempdir", return_value=self.tmp)

    def test_falls_back_when_xdg_runtime_dir_is_not_private(self):
        loose = self.make("loose", 0o777)
        with self.temp_root(), mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": loose}):
            fallback = sonyhp.runtime_dir()
        self.assertEqual(os.path.dirname(fallback), self.tmp)
        self.assertNotEqual(fallback, loose)
        self.assertTrue(sonyhp.is_private_dir(fallback))
        self.assertEqual(stat.S_IMODE(os.lstat(fallback).st_mode), 0o700)

    def test_the_fallback_is_private_even_under_a_loose_umask(self):
        previous = os.umask(0o000)
        self.addCleanup(os.umask, previous)
        with self.temp_root(), mock.patch.dict(os.environ, {}, clear=True):
            fallback = sonyhp.runtime_dir()
        self.assertEqual(stat.S_IMODE(os.lstat(fallback).st_mode), 0o700)

    def test_the_fallback_is_reused_once_made(self):
        with self.temp_root(), mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(sonyhp.runtime_dir(), sonyhp.runtime_dir())

    def test_refuses_a_fallback_someone_else_left_loose(self):
        # The old code would have used this directory exactly as it found it.
        squatted = os.path.join(self.tmp, f"omarchy-sony-headphones-{os.getuid()}")
        os.mkdir(squatted, 0o777)
        os.chmod(squatted, 0o777)
        with self.temp_root(), mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                sonyhp.runtime_dir()

    def test_refuses_a_fallback_that_is_a_symlink(self):
        target = self.make("target", 0o700)
        os.symlink(target, os.path.join(self.tmp, f"omarchy-sony-headphones-{os.getuid()}"))
        with self.temp_root(), mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                sonyhp.runtime_dir()


class TestDaemonFiles(unittest.TestCase):
    """The lock and the socket, opened inside a directory we trust."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.chmod(self.tmp, 0o700)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dir_fd = os.open(self.tmp, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.dir_fd)
        self.daemon = sonyhp.Daemon()

    def test_claims_and_then_refuses_a_second_claim(self):
        lock = self.daemon.claim_lock(self.dir_fd)
        self.addCleanup(lock.close)
        with self.assertRaises(SystemExit):
            sonyhp.Daemon().claim_lock(self.dir_fd)

    def test_the_lock_is_not_truncated_on_open(self):
        path = os.path.join(self.tmp, sonyhp.LOCK_NAME)
        with open(path, "w") as handle:
            handle.write("kept")
        lock = self.daemon.claim_lock(self.dir_fd)
        self.addCleanup(lock.close)
        with open(path) as handle:
            self.assertEqual(handle.read(), "kept")

    def test_refuses_a_lock_that_is_a_symlink(self):
        elsewhere = os.path.join(self.tmp, "elsewhere")
        open(elsewhere, "w").close()
        os.symlink(elsewhere, os.path.join(self.tmp, sonyhp.LOCK_NAME))
        with self.assertRaises(OSError):  # O_NOFOLLOW
            self.daemon.claim_lock(self.dir_fd)

    def test_removes_a_socket_we_own(self):
        path = os.path.join(self.tmp, sonyhp.SOCKET_NAME)
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(stale.close)
        stale.bind(path)
        self.daemon.remove_stale_socket(self.dir_fd)
        self.assertFalse(os.path.lexists(path))

    def test_a_missing_socket_is_not_an_error(self):
        self.daemon.remove_stale_socket(self.dir_fd)

    def test_refuses_to_remove_anything_that_is_not_a_socket(self):
        path = os.path.join(self.tmp, sonyhp.SOCKET_NAME)
        open(path, "w").close()
        with self.assertRaises(SystemExit):
            self.daemon.remove_stale_socket(self.dir_fd)
        self.assertTrue(os.path.lexists(path))

    def test_refuses_to_remove_a_symlink_standing_in_for_the_socket(self):
        victim = os.path.join(self.tmp, "victim")
        open(victim, "w").close()
        os.symlink(victim, os.path.join(self.tmp, sonyhp.SOCKET_NAME))
        with self.assertRaises(SystemExit):
            self.daemon.remove_stale_socket(self.dir_fd)
        self.assertTrue(os.path.exists(victim))


class TestChannelCache(unittest.TestCase):
    """The cached channel decides where the next connection is dialled."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cache = os.path.join(self.tmp, "cache")
        self.patch = mock.patch.object(sonyhp, "CACHE_DIR", self.cache)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.address = "AA:BB:CC:DD:EE:FF"

    def test_creates_the_cache_private(self):
        self.assertEqual(sonyhp.private_cache_dir(), self.cache)
        self.assertEqual(stat.S_IMODE(os.lstat(self.cache).st_mode), 0o700)

    def test_tightens_a_directory_left_loose(self):
        os.mkdir(self.cache, 0o755)
        os.chmod(self.cache, 0o755)
        self.assertEqual(sonyhp.private_cache_dir(), self.cache)
        self.assertEqual(stat.S_IMODE(os.lstat(self.cache).st_mode), 0o700)

    def test_declines_a_symlink(self):
        target = os.path.join(self.tmp, "target")
        os.mkdir(target, 0o700)
        os.symlink(target, self.cache)
        self.assertIsNone(sonyhp.private_cache_dir())

    def test_declines_a_file(self):
        open(self.cache, "w").close()
        self.assertIsNone(sonyhp.private_cache_dir())

    def test_round_trips_a_channel(self):
        sonyhp.remember_channel(self.address, 9)
        self.assertEqual(sonyhp.cached_channel(self.address), 9)
        path = sonyhp._channel_cache_path(self.address)
        self.assertEqual(stat.S_IMODE(os.lstat(path).st_mode), 0o600)

    def test_forget_removes_it(self):
        sonyhp.remember_channel(self.address, 9)
        sonyhp.forget_channel(self.address)
        self.assertIsNone(sonyhp.cached_channel(self.address))

    def test_does_not_write_through_a_symlink(self):
        os.mkdir(self.cache, 0o700)
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "w") as handle:
            handle.write("untouched")
        os.symlink(victim, sonyhp._channel_cache_path(self.address))
        sonyhp.remember_channel(self.address, 9)  # swallowed, not followed
        with open(victim) as handle:
            self.assertEqual(handle.read(), "untouched")

    def test_does_not_read_through_a_symlink(self):
        os.mkdir(self.cache, 0o700)
        planted = os.path.join(self.tmp, "planted")
        with open(planted, "w") as handle:
            handle.write("7")
        os.symlink(planted, sonyhp._channel_cache_path(self.address))
        self.assertIsNone(sonyhp.cached_channel(self.address))

    def test_rejects_a_channel_outside_the_valid_range(self):
        os.mkdir(self.cache, 0o700)
        for written in ("0", "31", "-1", "nonsense", ""):
            with self.subTest(written=written):
                with open(sonyhp._channel_cache_path(self.address), "w") as handle:
                    handle.write(written)
                self.assertIsNone(sonyhp.cached_channel(self.address))


class TestBluetoothctlInvocation(unittest.TestCase):
    def test_candidates_are_absolute(self):
        for candidate in sonyhp.BLUETOOTHCTL_CANDIDATES:
            self.assertTrue(os.path.isabs(candidate), candidate)

    def test_the_environment_does_not_carry_anything_inherited(self):
        self.assertEqual(set(sonyhp.BLUETOOTHCTL_ENV), {"PATH", "LC_ALL"})
        self.assertEqual(sonyhp.BLUETOOTHCTL_ENV["LC_ALL"], "C")
        for entry in sonyhp.BLUETOOTHCTL_ENV["PATH"].split(":"):
            self.assertTrue(os.path.isabs(entry), entry)

    def test_a_missing_binary_is_not_looked_up_on_path(self):
        with mock.patch.object(sonyhp, "BLUETOOTHCTL", None):
            with mock.patch.object(sonyhp.subprocess, "run") as run:
                self.assertEqual(sonyhp.bluetoothctl("devices"), "")
                run.assert_not_called()

    def test_the_absolute_binary_is_what_runs(self):
        with mock.patch.object(sonyhp, "BLUETOOTHCTL", "/usr/bin/bluetoothctl"):
            with mock.patch.object(sonyhp.subprocess, "run") as run:
                run.return_value = mock.Mock(stdout="")
                sonyhp.bluetoothctl("info", "AA:BB:CC:DD:EE:FF")
        argv, kwargs = run.call_args
        self.assertEqual(argv[0][0], "/usr/bin/bluetoothctl")
        self.assertEqual(kwargs["env"], sonyhp.BLUETOOTHCTL_ENV)

    def test_only_names_bluetoothctl_installs_under(self):
        for candidate in sonyhp.BLUETOOTHCTL_CANDIDATES:
            self.assertEqual(os.path.basename(candidate), "bluetoothctl")


class TestShellLaunch(unittest.TestCase):
    """The QML side is what starts the helper, so it has to hold the same line.

    There is no QML engine here, so these read Service.qml as text: enough to
    catch the interpreter going back to a bare name or a Process losing its
    minimal environment.
    """

    SERVICE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Service.qml")

    def setUp(self):
        with open(self.SERVICE, encoding="utf-8") as handle:
            self.source = handle.read()

    def test_the_interpreter_is_bound_by_absolute_path(self):
        self.assertIn('readonly property string interpreter: "/usr/bin/python3"', self.source)
        self.assertIn('[interpreter, "-I", helperPath]', self.source)
        self.assertNotIn('"python3"', self.source)

    def test_every_process_runs_with_the_minimal_environment(self):
        processes = self.source.count("Process {")
        self.assertEqual(processes, 3)
        self.assertEqual(self.source.count("clearEnvironment: true"), processes)
        self.assertEqual(self.source.count("environment: root.helperEnvironment"), processes)

    def test_the_environment_carries_only_what_the_helper_reads(self):
        self.assertIn('var env = { PATH: "/usr/bin:/bin" }', self.source)
        self.assertIn('["HOME", "XDG_RUNTIME_DIR", "XDG_CACHE_HOME", "SONY_HEADPHONES_DEMO"]', self.source)

    def test_the_helper_itself_names_the_system_interpreter(self):
        with open(HELPER, encoding="utf-8") as handle:
            self.assertEqual(handle.readline().strip(), "#!/usr/bin/python3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
