#!/usr/bin/env python3
"""Pilote sans fenêtre d'un cœur libretro Mega Drive (Genesis Plus GX) via ctypes.

Sert aux tests automatiques de la ROM : exécution image par image, rejeu d'appuis de boutons,
lecture de la RAM 68000, états sauvegardés, captures PNG. Genesis Plus GX lit aussi les ROM
Master System, ce qui servira à observer les jeux de référence.

Le cœur n'est pas versionné. Emplacement par défaut : work/emu/genesis_plus_gx_libretro.dll
(variable d'environnement GPGX_CORE pour un autre chemin). Téléchargement :
https://buildbot.libretro.com/nightly/windows/x86_64/latest/genesis_plus_gx_libretro.dll.zip
"""
from __future__ import annotations

import ctypes as C
import os
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORE = Path(os.environ.get("GPGX_CORE", ROOT / "work" / "emu" / "genesis_plus_gx_libretro.dll"))

# --- Constantes libretro -------------------------------------------------------
ENV_GET_CAN_DUPE = 3
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_VARIABLE = 15
ENV_GET_SAVE_DIRECTORY = 31
MEMORY_SYSTEM_RAM = 2
DEVICE_JOYPAD = 1

# Boutons Mega Drive → identifiants RetroPad (correspondance par défaut de Genesis Plus GX).
PAD = {
    "B": 0, "A": 1, "MODE": 2, "START": 3, "UP": 4, "DOWN": 5,
    "LEFT": 6, "RIGHT": 7, "C": 8, "Y": 9, "X": 10, "Z": 11,
}


class GameGeometry(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float)]


class AvInfo(C.Structure):
    _fields_ = [("geometry", GameGeometry), ("fps", C.c_double), ("sample_rate", C.c_double)]


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p),
                ("size", C.c_size_t), ("meta", C.c_char_p)]


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Emulator:
    """Une instance par processus (les cœurs libretro ont un état global)."""

    def __init__(self, rom_path: str | Path, core: str | Path = DEFAULT_CORE,
                 options: dict[str, str] | None = None, system_dir: str | Path | None = None):
        self.options = {k.encode(): v.encode() for k, v in (options or {}).items()}
        # Dossier système (BIOS, données annexes) : par défaut celui du cœur.
        self._dir = C.c_char_p(str(Path(system_dir or Path(core).parent).resolve()).encode())
        self.buttons: list[set[str]] = [set(), set()]
        self.frame = 0
        self.pixel_format = 0
        self.video: tuple[bytes, int, int, int] | None = None
        # Son : échantillons stéréo 16 bits entrelacés, accumulés si `record_audio` est vrai.
        self.record_audio = False
        self.audio = bytearray()

        lib = C.CDLL(str(core))
        self.lib = lib
        # Garder des références aux callbacks (sinon le GC les libère).
        self._cbs = [ENV_CB(self._env), VIDEO_CB(self._video), AUDIO_CB(self._sample),
                     AUDIO_BATCH_CB(self._samples), POLL_CB(lambda: None), STATE_CB(self._state)]
        lib.retro_set_environment(self._cbs[0])
        lib.retro_set_video_refresh(self._cbs[1])
        lib.retro_set_audio_sample(self._cbs[2])
        lib.retro_set_audio_sample_batch(self._cbs[3])
        lib.retro_set_input_poll(self._cbs[4])
        lib.retro_set_input_state(self._cbs[5])
        lib.retro_init()

        self._rom = Path(rom_path).read_bytes()
        self._rom_buf = C.create_string_buffer(self._rom, len(self._rom))
        info = GameInfo(str(rom_path).encode(), C.cast(self._rom_buf, C.c_void_p), len(self._rom), None)
        lib.retro_load_game.restype = C.c_bool
        if not lib.retro_load_game(C.byref(info)):
            raise RuntimeError("retro_load_game a échoué")
        lib.retro_set_controller_port_device(0, DEVICE_JOYPAD)
        lib.retro_set_controller_port_device(1, DEVICE_JOYPAD)

        lib.retro_get_memory_data.restype = C.c_void_p
        lib.retro_get_memory_size.restype = C.c_size_t
        lib.retro_serialize_size.restype = C.c_size_t
        lib.retro_serialize.restype = C.c_bool
        lib.retro_unserialize.restype = C.c_bool
        ptr = lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        size = lib.retro_get_memory_size(MEMORY_SYSTEM_RAM)
        self._ram = (C.c_uint8 * size).from_address(ptr)
        # Genesis Plus GX range la RAM en mots 16 bits natifs : octets permutés sur x86.
        self.byteswapped = True

    # --- callbacks libretro ----------------------------------------------------
    def _sample(self, left, right):
        if self.record_audio:
            self.audio += struct.pack("<hh", left, right)

    def _samples(self, data, frames):
        if self.record_audio and data:
            self.audio += C.string_at(data, frames * 4)
        return frames

    def audio_rate(self) -> float:
        """Fréquence d'échantillonnage annoncée par le cœur."""
        info = AvInfo()
        self.lib.retro_get_system_av_info(C.byref(info))
        return info.sample_rate

    def save_wav(self, path: str | Path) -> None:
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(round(self.audio_rate()))
            w.writeframes(bytes(self.audio))

    def _env(self, cmd, data):
        if cmd in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY):
            C.cast(data, C.POINTER(C.c_char_p))[0] = self._dir.value
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            self.pixel_format = C.cast(data, C.POINTER(C.c_int))[0]
            return True
        if cmd == ENV_GET_CAN_DUPE:
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        if cmd == ENV_GET_VARIABLE:
            var = C.cast(data, C.POINTER(Variable))[0]
            if var.key in self.options:
                var.value = self.options[var.key]
                C.cast(data, C.POINTER(Variable))[0] = var
                return True
            return False
        return False

    def _video(self, data, width, height, pitch):
        if data:
            self.video = (C.string_at(data, pitch * height), width, height, pitch)

    def _state(self, port, device, index, button_id):
        if port > 1 or device != DEVICE_JOYPAD:
            return 0
        return int(any(PAD[b] == button_id for b in self.buttons[port]))

    # --- exécution -------------------------------------------------------------
    def run(self, frames: int = 1, press: tuple[str, ...] | set[str] = (), port: int = 0) -> None:
        self.buttons[port] = set(press)
        for _ in range(frames):
            self.lib.retro_run()
            self.frame += 1
        self.buttons[port] = set()

    def tap(self, button: str, hold: int = 4, release: int = 4, port: int = 0) -> None:
        self.run(hold, (button,), port)
        self.run(release, (), port)

    # --- mémoire 68000 (adresses $FF0000-$FFFFFF) -----------------------------
    def _idx(self, addr: int) -> int:
        i = addr & 0xFFFF
        return i ^ 1 if self.byteswapped else i

    def ram(self) -> bytes:
        """Copie de la RAM en ordre 68000 (big-endian), index 0 = $FF0000."""
        raw = bytes(self._ram)
        if not self.byteswapped:
            return raw
        out = bytearray(len(raw))
        out[0::2] = raw[1::2]
        out[1::2] = raw[0::2]
        return bytes(out)

    def u8(self, addr: int) -> int:
        return self._ram[self._idx(addr)]

    def u16(self, addr: int) -> int:
        return (self.u8(addr) << 8) | self.u8(addr + 1)

    def s16(self, addr: int) -> int:
        v = self.u16(addr)
        return v - 0x10000 if v & 0x8000 else v

    def u32(self, addr: int) -> int:
        return (self.u16(addr) << 16) | self.u16(addr + 2)

    def write8(self, addr: int, value: int) -> None:
        self._ram[self._idx(addr)] = value & 0xFF

    def write16(self, addr: int, value: int) -> None:
        self.write8(addr, value >> 8)
        self.write8(addr + 1, value)

    # --- états -----------------------------------------------------------------
    def save_state(self) -> bytes:
        size = self.lib.retro_serialize_size()
        buf = C.create_string_buffer(size)
        if not self.lib.retro_serialize(buf, size):
            raise RuntimeError("retro_serialize a échoué")
        return (self.frame.to_bytes(8, "little")) + buf.raw

    def load_state(self, state: bytes) -> None:
        self.frame = int.from_bytes(state[:8], "little")
        body = state[8:]
        buf = C.create_string_buffer(body, len(body))
        if not self.lib.retro_unserialize(buf, len(body)):
            raise RuntimeError("retro_unserialize a échoué")

    # --- capture ---------------------------------------------------------------
    def screenshot(self, path: str | Path) -> None:
        if not self.video:
            raise RuntimeError("aucune image reçue")
        data, w, h, pitch = self.video
        rows = []
        for y in range(h):
            line = bytearray(b"\x00")
            row = data[y * pitch:y * pitch + w * (4 if self.pixel_format == 1 else 2)]
            if self.pixel_format == 1:          # XRGB8888
                for x in range(w):
                    b, g, r, _ = row[x * 4:x * 4 + 4]
                    line += bytes((r, g, b))
            else:                               # RGB565 (2) ou 0RGB1555 (0)
                for (px,) in struct.iter_unpack("<H", row):
                    if self.pixel_format == 2:
                        r, g, b = (px >> 11) << 3, ((px >> 5) & 0x3F) << 2, (px & 0x1F) << 3
                    else:
                        r, g, b = ((px >> 10) & 0x1F) << 3, ((px >> 5) & 0x1F) << 3, (px & 0x1F) << 3
                    line += bytes((r, g, b))
            rows.append(bytes(line))

        def chunk(tag, body):
            return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))

        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))
        Path(path).write_bytes(png)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("rom")
    p.add_argument("--frames", type=int, default=300)
    p.add_argument("--png", default=str(ROOT / "work" / "shot.png"))
    p.add_argument("--region", choices=["auto", "ntsc-u", "pal", "ntsc-j"], default="auto")
    a = p.parse_args()
    emu = Emulator(a.rom, options={"genesis_plus_gx_region_detect": a.region})
    emu.run(a.frames)
    emu.screenshot(a.png)
    print(f"image {emu.frame}, capture : {a.png}")
