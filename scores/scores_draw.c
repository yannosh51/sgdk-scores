#include "scores_draw.h"

#define QUIET       4       // marge claire imposée par la norme, en modules
#define DARK_COLOR  1
#define LIGHT_COLOR 2

u16 scores_qrTiles(const ScoresQr* qr)
{
    return (qr->size + 2 * QUIET + 1) / 2;
}

static bool dark(const ScoresQr* qr, s16 x, s16 y)
{
    x -= QUIET;
    y -= QUIET;
    return x >= 0 && y >= 0 && x < qr->size && y < qr->size && qr->dark[y][x];
}

// Motif p (4 bits : haut gauche 1, haut droit 2, bas gauche 4, bas droit 8) -> tuile p.
static void loadTiles(u16 palette, u16 tileIndex)
{
    u32 tiles[SCORES_QR_TILES][8];
    for (u16 p = 0; p < SCORES_QR_TILES; p++)
        for (u16 row = 0; row < 8; row++)
        {
            const u16 bitLeft = row < 4 ? 1 : 4, bitRight = row < 4 ? 2 : 8;
            const u32 left = (p & bitLeft) ? DARK_COLOR : LIGHT_COLOR;
            const u32 right = (p & bitRight) ? DARK_COLOR : LIGHT_COLOR;
            tiles[p][row] = left * 0x11110000 + right * 0x00001111;
        }
    VDP_loadTileData((const u32*) tiles, tileIndex, SCORES_QR_TILES, CPU);
    PAL_setColor(palette * 16 + DARK_COLOR, RGB24_TO_VDPCOLOR(0x000000));
    PAL_setColor(palette * 16 + LIGHT_COLOR, RGB24_TO_VDPCOLOR(0xFFFFFF));
}

void scores_drawQr(const ScoresQr* qr, VDPPlane plane, u16 x, u16 y, u16 palette, u16 tileIndex)
{
    if (!qr->size) return;
    loadTiles(palette, tileIndex);
    const u16 tiles = scores_qrTiles(qr);
    for (u16 ty = 0; ty < tiles; ty++)
        for (u16 tx = 0; tx < tiles; tx++)
        {
            const s16 mx = tx * 2, my = ty * 2;
            const u16 p = dark(qr, mx, my) | (dark(qr, mx + 1, my) << 1) | (dark(qr, mx, my + 1) << 2)
                        | (dark(qr, mx + 1, my + 1) << 3);
            VDP_setTileMapXY(plane, TILE_ATTR_FULL(palette, TRUE, FALSE, FALSE, tileIndex + p), x + tx, y + ty);
        }
}
