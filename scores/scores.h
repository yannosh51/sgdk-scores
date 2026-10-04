#pragma once

// sgdk-scores : codes de score signés et QR code pour les jeux SGDK (Mega Drive).
// Voir README.md. Utilisation type, sur l'écran de fin de partie :
//
//     #include "scores/scores.h"
//     #include "scores_config.h"          // généré par tools/scores_setup.py : SCORES_URL, SCORES_KEY
//
//     static ScoresQr qr;
//     char code[SCORES_CODE_LENGTH + 1], url[100];
//     scores_makeCode(SCORES_KEY, pseudo, score, vtimer, code);
//     scores_makeUrl(SCORES_URL, code, url, sizeof(url));
//     if (scores_qrEncode(url, &qr))
//         scores_drawQr(&qr, WINDOW, 1, 4, PAL0, TILE_USER_INDEX);

#include "scores_code.h"
#include "scores_draw.h"
#include "scores_qr.h"

#define SCORES_VERSION "1.0.0"
