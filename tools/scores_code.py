#!/usr/bin/env python3
"""sgdk-scores : format de référence des codes de score (la console les calcule dans
scores/scores_code.c ; un site les vérifie avec la même clé).

    python tools/scores_code.py decode <code ou adresse> --key secrets/scores.key
    python tools/scores_code.py encode <pseudo> <score> [numéro] --key secrets/scores.key

Contenu (128 bits) : version (4 bits) | pseudo (2 x 32 bits) | score (20 bits) | numéro de
partie (12 bits) | signature (28 bits). Le pseudo fait 12 caractères (espace, A-Z, 0-9), écrits
en base 37 par moitiés de 6 (37^6 < 2^32). La signature est un CBC-MAC XTEA des 100 premiers
bits (clé de signature = clé XOR A5A5A5A5) ; les 128 bits sont ensuite chiffrés en XTEA (CBC,
vecteur nul). Le code est écrit en base 32 de Crockford (sans I, L, O, U) : 26 caractères,
lisibles sans ambiguïté, et tous acceptés par le mode alphanumérique des QR codes.

Adresse du QR code : <site>/<JEU>/<CODE>. Le site garde une clé par jeu : le nom du jeu dans
l'adresse dit quelle clé utiliser, et un code présenté sous le nom d'un autre jeu est refusé.

La clé est dans la ROM : quelqu'un qui la désassemble peut fabriquer des codes pour ce jeu. Le
chiffrement empêche de modifier un code à la main ou d'en inventer un, pas une triche déterminée.
"""
from __future__ import annotations

import sys
from pathlib import Path

VERSION = 1
PSEUDO_LENGTH = 12
PSEUDO_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
SCORE_MAX = (1 << 20) - 1
BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 26
MASK32 = 0xFFFFFFFF
DELTA = 0x9E3779B9
MAC_KEY_XOR = 0xA5A5A5A5


class InvalidCode(ValueError):
    pass


def load_key(path: Path) -> list[int]:
    text = path.read_text(encoding="ascii").strip()
    if len(text) != 32:
        raise SystemExit(f"{path} : 32 chiffres hexadécimaux attendus")
    return [int(text[i:i + 8], 16) for i in range(0, 32, 8)]


def xtea_encrypt(v0: int, v1: int, key: list[int]) -> tuple[int, int]:
    s = 0
    for _ in range(32):
        v0 = (v0 + ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (s + key[s & 3]))) & MASK32
        s = (s + DELTA) & MASK32
        v1 = (v1 + ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (s + key[(s >> 11) & 3]))) & MASK32
    return v0, v1


def xtea_decrypt(v0: int, v1: int, key: list[int]) -> tuple[int, int]:
    s = (DELTA * 32) & MASK32
    for _ in range(32):
        v1 = (v1 - ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (s + key[(s >> 11) & 3]))) & MASK32
        s = (s - DELTA) & MASK32
        v0 = (v0 - ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (s + key[s & 3]))) & MASK32
    return v0, v1


def normalize_pseudo(pseudo: str) -> str:
    pseudo = pseudo.upper()
    if len(pseudo) > PSEUDO_LENGTH or any(c not in PSEUDO_CHARS for c in pseudo):
        raise ValueError(f"pseudo invalide : {pseudo!r} (12 caractères A-Z, 0-9)")
    return pseudo.ljust(PSEUDO_LENGTH)


def pseudo_halves(pseudo: str) -> tuple[int, int]:
    p = normalize_pseudo(pseudo)
    halves = []
    for part in (p[:6], p[6:]):
        value = 0
        for c in part:
            value = value * 37 + PSEUDO_CHARS.index(c)
        halves.append(value)
    return halves[0], halves[1]


def pseudo_from_halves(h1: int, h2: int) -> str:
    chars = []
    for value in (h1, h2):
        part = []
        for _ in range(6):
            value, digit = divmod(value, 37)
            part.append(PSEUDO_CHARS[digit])
        if value:
            raise InvalidCode("pseudo hors limites")
        chars += reversed(part)
    return "".join(chars).rstrip()


def mac(words: list[int], key: list[int]) -> int:
    mk = [k ^ MAC_KEY_XOR for k in key]
    a, b = xtea_encrypt(words[0], words[1], mk)
    a, b = xtea_encrypt(a ^ words[2], b ^ (words[3] & 0xF0000000), mk)
    return a >> 4


def to_base32(words: list[int]) -> str:
    value = 0
    for w in words:
        value = (value << 32) | w
    return "".join(BASE32[(value >> (5 * i)) & 31] for i in reversed(range(CODE_LENGTH)))


def from_base32(code: str) -> list[int]:
    code = code.upper().replace("-", "").replace(" ", "")
    code = code.replace("O", "0").replace("I", "1").replace("L", "1")   # règles de Crockford
    if len(code) != CODE_LENGTH or any(c not in BASE32 for c in code):
        raise InvalidCode("code mal formé")
    value = 0
    for c in code:
        value = (value << 5) | BASE32.index(c)
    if value >> 128:
        raise InvalidCode("code hors limites")
    return [(value >> (32 * i)) & MASK32 for i in reversed(range(4))]


def encode(pseudo: str, score: int, nonce: int, key: list[int]) -> str:
    h1, h2 = pseudo_halves(pseudo)
    score = min(score, SCORE_MAX)
    w = [(VERSION << 28) | (h1 >> 4),
         ((h1 & 0xF) << 28) | (h2 >> 4),
         ((h2 & 0xF) << 28) | (score << 8) | ((nonce >> 4) & 0xFF),
         (nonce & 0xF) << 28]
    w[3] |= mac(w, key)
    c0 = xtea_encrypt(w[0], w[1], key)
    c1 = xtea_encrypt(w[2] ^ c0[0], w[3] ^ c0[1], key)
    return to_base32([c0[0], c0[1], c1[0], c1[1]])


def decode(code: str, key: list[int]) -> dict:
    c = from_base32(code)
    p0 = xtea_decrypt(c[0], c[1], key)
    p1 = xtea_decrypt(c[2], c[3], key)
    w = [p0[0], p0[1], p1[0] ^ c[0], p1[1] ^ c[1]]
    if w[3] & 0x0FFFFFFF != mac(w, key) or w[0] >> 28 != VERSION:
        raise InvalidCode("signature invalide : code modifié ou faux")
    h1 = ((w[0] & 0x0FFFFFFF) << 4) | (w[1] >> 28)
    h2 = ((w[1] & 0x0FFFFFFF) << 4) | (w[2] >> 28)
    return {"pseudo": pseudo_from_halves(h1, h2),
            "score": (w[2] >> 8) & 0xFFFFF,
            "nonce": ((w[2] & 0xFF) << 4) | (w[3] >> 28)}


def parse_url(url: str) -> tuple[str, str]:
    """(jeu, code) d'une adresse de QR code : .../<JEU>/<CODE>."""
    parts = [p for p in url.strip().split("/") if p]
    if len(parts) < 2:
        raise InvalidCode("adresse sans jeu ni code")
    return parts[-2].upper(), parts[-1].upper()


def pretty(code: str) -> str:
    """Code affiché : groupes de 5, 5, 5, 5 et 6 caractères."""
    return "-".join(code[i:j] for i, j in ((0, 5), (5, 10), (10, 15), (15, 20), (20, 26)))


def main() -> int:
    args = sys.argv[1:]
    key_path = Path("secrets/scores.key")
    if "--key" in args:
        k = args.index("--key")
        key_path = Path(args[k + 1])
        del args[k:k + 2]
    key = load_key(key_path)
    if len(args) >= 2 and args[0] == "decode":
        text = args[1]
        try:
            if "/" in text:
                game, text = parse_url(text)
                print(f"jeu : {game}")
            print(decode(text, key))
        except InvalidCode as e:
            print(f"refusé : {e}")
            return 1
        return 0
    if len(args) >= 3 and args[0] == "encode":
        nonce = int(args[3]) if len(args) > 3 else 0
        print(pretty(encode(args[1], int(args[2]), nonce, key)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
