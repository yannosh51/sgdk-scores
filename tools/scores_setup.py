#!/usr/bin/env python3
"""sgdk-scores : clé du jeu et fichier de réglage C (scores_config.h).

    python tools/scores_setup.py --site HTTPS://SCORES.EXEMPLE.NET/ --game MONJEU \\
        --key secrets/scores.key --out src/scores_config.h

- La clé (128 bits, 32 chiffres hexadécimaux) est créée au hasard si le fichier n'existe pas.
  À garder, à ne pas versionner, et à donner au site qui reçoit les scores. Ne pas la refaire :
  les codes des ROM déjà distribuées ne seraient plus reconnus.
- scores_config.h définit SCORES_URL (site + jeu + "/") et SCORES_KEY. Il contient la clé : ne
  pas le versionner non plus (le régénérer à chaque compilation).

L'adresse est mise dans un QR code en mode alphanumérique : majuscules, chiffres et
$ % * + - . / : seulement, 64 caractères au plus (le code en ajoute 26).
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path

QR_ALNUM = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:")
QR_CAPACITY = 90            # caractères alphanumériques, version 4, niveau M (scores_qr.c)
CODE_LENGTH = 26


def game_url(site: str, game: str) -> str:
    """Adresse appelée par le QR code, avant le code : site + jeu + "/"."""
    if not re.fullmatch(r"[A-Z0-9]{1,12}", game):
        raise ValueError(f"identifiant de jeu invalide {game!r} (A-Z, 0-9, 12 caractères au plus)")
    url = (site if site.endswith("/") else site + "/") + game + "/"
    bad = sorted(set(url) - QR_ALNUM)
    if bad:
        raise ValueError(f"caractères interdits dans l'adresse {bad} (majuscules, chiffres et "
                         "$ % * + - . / : seulement, mode alphanumérique du QR code)")
    if len(url) + CODE_LENGTH > QR_CAPACITY:
        raise ValueError(f"adresse trop longue ({len(url)} caractères, {QR_CAPACITY - CODE_LENGTH} au plus)")
    return url


def ensure_key(path: Path) -> str:
    """Clé du jeu (32 chiffres hexadécimaux), créée au hasard si absente."""
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(16) + "\n", encoding="ascii")
        print(f"clé créée : {path} (à garder, à donner au site des scores)")
    key = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", key):
        raise ValueError(f"{path} : 32 chiffres hexadécimaux attendus")
    return key.lower()


def write_config(site: str, game: str, key_path: Path, out: Path) -> None:
    url = game_url(site, game)
    key = ensure_key(key_path)
    words = ", ".join(f"0x{key[i:i + 8]}" for i in range(0, 32, 8))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("// Généré par sgdk-scores/tools/scores_setup.py : ne pas modifier, ne pas versionner (clé).\n"
                   "#pragma once\n\n"
                   "#include <genesis.h>\n\n"
                   f'#define SCORES_URL "{url}"\n'
                   f"static const u32 SCORES_KEY[4] = {{ {words} }};\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--site", required=True, help="site des scores, par exemple HTTPS://SCORES.EXEMPLE.NET/")
    p.add_argument("--game", required=True, help="identifiant du jeu sur le site : A-Z, 0-9, 12 au plus")
    p.add_argument("--key", default="secrets/scores.key", type=Path, help="fichier de la clé")
    p.add_argument("--out", default="src/scores_config.h", type=Path, help="fichier C produit")
    a = p.parse_args()
    try:
        write_config(a.site, a.game, a.key, a.out)
    except ValueError as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 1
    print(f"{a.out} : {game_url(a.site, a.game)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
