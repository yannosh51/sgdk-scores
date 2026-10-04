// Exemple sgdk-scores : écran de fin de partie avec code de score et QR code.
// Construction : python example/build.py (voir README.md).
#include <genesis.h>

#include "scores/scores.h"
#include "scores_config.h"

// Lu par les tests (out/symbol.txt).
__attribute__((used)) char g_code[SCORES_CODE_LENGTH + 1];

static ScoresQr qr;

int main(bool hardReset)
{
    const char* pseudo = "EXEMPLE";
    const u32 score = 123456;
    char url[100], line[16];

    VDP_setScreenWidth320();
    PAL_setColor(0, RGB24_TO_VDPCOLOR(0x000000));

    // Code d'abord (instantané), QR code ensuite (environ 0,7 s de calcul).
    scores_makeCode(SCORES_KEY, pseudo, score, 0, g_code);
    VDP_drawText("GAME OVER", 26, 3);
    VDP_drawText("PSEUDO", 26, 6);
    VDP_drawText(pseudo, 26, 7);
    VDP_drawText("SCORE", 26, 9);
    sprintf(line, "%lu", score);
    VDP_drawText(line, 26, 10);
    VDP_drawText("CODE", 26, 12);
    for (u16 i = 0; i < 5; i++)         // groupes de 5, 5, 5, 5 et 6 caractères
    {
        const u16 len = i < 4 ? 5 : 6;
        memcpy(line, g_code + i * 5, len);
        line[len] = 0;
        VDP_drawText(line, 26, 13 + i);
    }

    if (scores_makeUrl(SCORES_URL, g_code, url, sizeof(url)) && scores_qrEncode(url, &qr))
    {
        const u16 tiles = scores_qrTiles(&qr);
        scores_drawQr(&qr, BG_A, 2, (28 - tiles) / 2, PAL1, TILE_USER_INDEX);
    }

    while (TRUE) SYS_doVBlankProcess();
    return 0;
}
