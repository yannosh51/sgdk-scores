#pragma once

#include <genesis.h>

#include "scores_qr.h"

// Dessin d'un QR code sur un plan (BG_A, BG_B ou WINDOW), avec sa marge claire de 4 modules.
// Chaque tuile 8 x 8 montre 2 x 2 modules de 4 x 4 pixels : 16 tuiles suffisent, chargées en
// `tileIndex`. Couleurs : indices 1 (foncé) et 2 (clair) de `palette`, mis en noir et blanc.
// Taille à l'écran : (côté + 8) / 2 tuiles, soit 19 tuiles (152 px) en version 3 et 21 tuiles
// (168 px) en version 4.
#define SCORES_QR_TILES 16

// Renvoie la largeur (et hauteur) du dessin en tuiles.
u16 scores_qrTiles(const ScoresQr* qr);

void scores_drawQr(const ScoresQr* qr, VDPPlane plane, u16 x, u16 y, u16 palette, u16 tileIndex);
