#pragma once

#include <genesis.h>

// QR code (norme ISO 18004) en mode alphanumérique : 0-9, A-Z (majuscules), espace et
// $ % * + - . / :. Correction d'erreurs niveau M (15 %), versions 1 à 4 (21 à 33 modules de
// côté), soit 90 caractères au plus. Pas d'allocation : tableaux statiques (environ 1,4 Ko).
// Coût : environ 0,7 s de 68000 pour une adresse de 61 caractères (version 3) ; à calculer une
// fois, sur un écran fixe.
#define SCORES_QR_MAX_VERSION 4
#define SCORES_QR_MAX_SIZE    (17 + 4 * SCORES_QR_MAX_VERSION)

typedef struct
{
    u8 size;                                            // modules de côté (0 : pas de QR code)
    u8 dark[SCORES_QR_MAX_SIZE][SCORES_QR_MAX_SIZE];    // 1 : module foncé
} ScoresQr;

// Renvoie FALSE si le texte contient un caractère non accepté ou dépasse 90 caractères.
bool scores_qrEncode(const char* text, ScoresQr* out);
