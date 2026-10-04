"""Tests de sgdk-scores.

    python -m unittest discover -s tests

- Format des codes et réglages : Python seul.
- Exemple SGDK (si example/out/rom.bin existe, après python example/build.py) : la ROM est lancée
  dans Genesis Plus GX (cœur libretro, variable d'environnement GPGX_CORE), le code calculé par
  la console est décodé, et le QR code affiché est relu (pip install zxing-cpp pillow).
"""
from __future__ import annotations

import os
import random
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "tests")]

import scores_code  # noqa: E402
from scores_setup import game_url  # noqa: E402

EXAMPLE_ROM = REPO / "example" / "out" / "rom.bin"
EXAMPLE_KEY = REPO / "example" / "secrets" / "scores.key"
CORE = Path(os.environ.get("GPGX_CORE", REPO / "work" / "emu" / "genesis_plus_gx_libretro.dll"))
KEY = [0x01234567, 0x89ABCDEF, 0xFEDCBA98, 0x76543210]


class FormatTest(unittest.TestCase):
    def test_round_trip(self):
        rng = random.Random(1)
        for _ in range(100):
            pseudo = "".join(rng.choice(scores_code.PSEUDO_CHARS[1:]) for _ in range(rng.randint(1, 12)))
            score, nonce = rng.randint(0, scores_code.SCORE_MAX), rng.randint(0, 4095)
            code = scores_code.encode(pseudo, score, nonce, KEY)
            self.assertEqual(len(code), 26)
            self.assertEqual(scores_code.decode(code, KEY), {"pseudo": pseudo, "score": score, "nonce": nonce})

    def test_any_changed_character_is_rejected(self):
        code = scores_code.encode("PLAYER1", 4200, 3, KEY)
        for i in range(len(code)):
            for c in "0Z":
                if code[i] != c:
                    with self.assertRaises(scores_code.InvalidCode):
                        scores_code.decode(code[:i] + c + code[i + 1:], KEY)

    def test_another_key_is_rejected(self):
        code = scores_code.encode("PLAYER1", 4200, 3, KEY)
        with self.assertRaises(scores_code.InvalidCode):
            scores_code.decode(code, [k ^ 1 for k in KEY])

    def test_typing_mistakes_are_forgiven(self):
        code = scores_code.encode("PLAYER1", 4200, 3, KEY)
        typed = scores_code.pretty(code).lower().replace("0", "o").replace("1", "l")
        self.assertEqual(scores_code.decode(typed, KEY)["pseudo"], "PLAYER1")

    def test_url_parsing(self):
        self.assertEqual(scores_code.parse_url("https://scores.exemple.net/monjeu/ABC"), ("MONJEU", "ABC"))


class SetupTest(unittest.TestCase):
    def test_game_url(self):
        self.assertEqual(game_url("HTTPS://SCORES.EXEMPLE.NET", "JEU1"), "HTTPS://SCORES.EXEMPLE.NET/JEU1/")
        for site, game in (("https://minuscules.net/", "JEU"), ("HTTPS://X.NET/", "jeu"),
                           ("HTTPS://X.NET/?A=1", "JEU"), ("HTTPS://" + "X" * 60 + ".NET/", "JEU")):
            with self.assertRaises(ValueError):
                game_url(site, game)


@unittest.skipUnless(EXAMPLE_ROM.is_file() and EXAMPLE_KEY.is_file(), "exemple non construit (python example/build.py)")
@unittest.skipUnless(CORE.is_file(), f"cœur Genesis Plus GX absent ({CORE}, variable GPGX_CORE)")
class ExampleRomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from emu import Emulator
        cls.emu = Emulator(EXAMPLE_ROM, core=CORE)
        cls.emu.run(120)                # calcul du QR code compris

    def read_code(self) -> str:
        symbols = REPO / "example" / "out" / "symbol.txt"
        addr = next(int(l.split()[0], 16) for l in symbols.read_text().splitlines() if l.split()[-1] == "g_code")
        return bytes(self.emu.u8(addr + i) for i in range(26)).decode("ascii")

    def test_console_code_decodes(self):
        decoded = scores_code.decode(self.read_code(), scores_code.load_key(EXAMPLE_KEY))
        self.assertEqual((decoded["pseudo"], decoded["score"], decoded["nonce"]), ("EXEMPLE", 123456, 0))

    def test_qr_code_reads_back(self):
        try:
            import zxingcpp
            from PIL import Image
        except ImportError:
            self.skipTest("pip install zxing-cpp pillow")
        shot = REPO / "example" / "out" / "screen.png"
        self.emu.screenshot(shot)
        results = zxingcpp.read_barcodes(Image.open(shot).convert("L"))
        self.assertEqual(len(results), 1, "QR code illisible")
        self.assertEqual(results[0].text, game_url("HTTPS://SCORES.EXEMPLE.NET/", "EXEMPLE") + self.read_code())


if __name__ == "__main__":
    unittest.main()
