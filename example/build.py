#!/usr/bin/env python3
"""Construit l'exemple : example/out/rom.bin.

    python example/build.py [--site HTTPS://SCORES.EXEMPLE.NET/] [--game EXEMPLE]

SGDK est cherché dans la variable d'environnement GDK (sinon ../../sgdk à côté du dépôt).
Le module (scores/) est copié dans example/src/scores, comme dans un vrai projet, et
scores_config.h est généré avec la clé example/secrets/scores.key (créée si absente).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent
REPO = EXAMPLE.parent
sys.path.insert(0, str(REPO / "tools"))

from scores_setup import write_config  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="HTTPS://SCORES.EXEMPLE.NET/")
    p.add_argument("--game", default="EXEMPLE")
    a = p.parse_args()

    shutil.rmtree(EXAMPLE / "src" / "scores", ignore_errors=True)
    shutil.copytree(REPO / "scores", EXAMPLE / "src" / "scores")
    write_config(a.site, a.game, EXAMPLE / "secrets" / "scores.key", EXAMPLE / "src" / "scores_config.h")

    gdk = Path(os.environ.get("GDK", REPO.parent / "sgdk"))
    if not (gdk / "makefile.gen").is_file():
        print(f"SGDK introuvable dans {gdk} : définir la variable GDK", file=sys.stderr)
        return 1
    make = gdk / "bin" / ("make.exe" if os.name == "nt" else "make")
    env = dict(os.environ, GDK=gdk.as_posix())
    r = subprocess.run([str(make), "-f", (gdk / "makefile.gen").as_posix()], cwd=EXAMPLE, env=env)
    if r.returncode:
        return r.returncode
    print(f"ROM : {EXAMPLE / 'out' / 'rom.bin'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
