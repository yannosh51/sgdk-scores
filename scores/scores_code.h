#pragma once

#include <genesis.h>

// Code de score : pseudo, score et numéro de partie, signés et chiffrés (XTEA, clé de 128 bits
// propre à chaque jeu), écrits en 26 caractères (base 32 de Crockford : 0-9 A-Z sans I L O U).
// Format de référence et décodage : tools/scores_code.py.
#define SCORES_CODE_LENGTH   26
#define SCORES_PSEUDO_LENGTH 12         // espace, A-Z, 0-9
#define SCORES_SCORE_MAX     0xFFFFF    // 1 048 575

// `pseudo` : jusqu'à 12 caractères (espace, A-Z, 0-9 ; un autre caractère compte comme un
// espace), terminé par 0 s'il est plus court. `nonce` : 12 bits qui distinguent deux parties
// (par exemple vtimer). `out` : SCORES_CODE_LENGTH + 1 octets.
void scores_makeCode(const u32 key[4], const char* pseudo, u32 score, u16 nonce, char* out);

// `out` = `base` (adresse du site et du jeu, par exemple SCORES_URL) suivi du code.
// `size` : taille de `out` ; FALSE si l'adresse ne tient pas.
bool scores_makeUrl(const char* base, const char* code, char* out, u16 size);
