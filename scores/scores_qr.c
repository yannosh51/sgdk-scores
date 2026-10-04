#include "scores_qr.h"

// Version 1 à 4, niveau M : octets de données, octets de correction par bloc, blocs.
static const u8 DATA_CODEWORDS[SCORES_QR_MAX_VERSION + 1] = { 0, 16, 28, 44, 64 };
static const u8 EC_PER_BLOCK[SCORES_QR_MAX_VERSION + 1]   = { 0, 10, 16, 26, 18 };
static const u8 BLOCKS[SCORES_QR_MAX_VERSION + 1]         = { 0, 1, 1, 1, 2 };
#define FORMAT_ECC_M  0         // bits de format du niveau M
#define MAX_CODEWORDS 100       // version 4
#define MAX_EC        26

#define FUNCTION 2              // bit 1 de `cell` : module de repère (ni données ni masque)

static u8 cell[SCORES_QR_MAX_SIZE][SCORES_QR_MAX_SIZE];   // bit 0 foncé, bit 1 repère
static u8 size;
static u8 codewords[MAX_CODEWORDS];
static u8 finalBytes[MAX_CODEWORDS];
static u16 bitLength;

static void setFunction(s16 x, s16 y, bool dark)
{
    cell[y][x] = FUNCTION | (dark ? 1 : 0);
}

// --- Données --------------------------------------------------------------------------------
static s16 alnumValue(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'Z') return c - 'A' + 10;
    switch (c)
    {
        case ' ': return 36;
        case '$': return 37;
        case '%': return 38;
        case '*': return 39;
        case '+': return 40;
        case '-': return 41;
        case '.': return 42;
        case '/': return 43;
        case ':': return 44;
    }
    return -1;
}

static void appendBits(u16 value, u16 count)
{
    for (s16 i = count - 1; i >= 0; i--, bitLength++)
        if ((value >> i) & 1) codewords[bitLength >> 3] |= 0x80 >> (bitLength & 7);
}

// --- Reed-Solomon sur GF(256), polynôme 0x11D -----------------------------------------------
// Multiplication par tables de logarithmes (512 octets, remplies au premier appel) : quelques
// instructions au lieu d'une boucle de 8 décalages.
static u8 gfExp[256], gfLog[256];

static void gfInit(void)
{
    u16 x = 1;
    for (u16 i = 0; i < 255; i++)
    {
        gfExp[i] = x;
        gfLog[x] = i;
        x <<= 1;
        if (x & 0x100) x ^= 0x11D;
    }
}

static u8 gfMul(u8 x, u8 y)
{
    if (!x || !y) return 0;
    u16 e = gfLog[x] + gfLog[y];
    if (e >= 255) e -= 255;
    return gfExp[e];
}

static void rsDivisor(u8 degree, u8* result)
{
    memset(result, 0, degree);
    result[degree - 1] = 1;
    u8 root = 1;
    for (u8 i = 0; i < degree; i++)
    {
        for (u8 j = 0; j < degree; j++)
        {
            result[j] = gfMul(result[j], root);
            if (j + 1 < degree) result[j] ^= result[j + 1];
        }
        root = gfMul(root, 0x02);
    }
}

static void rsRemainder(const u8* data, u8 length, const u8* divisor, u8 degree, u8* result)
{
    memset(result, 0, degree);
    for (u8 i = 0; i < length; i++)
    {
        const u8 factor = data[i] ^ result[0];
        for (u8 j = 0; j + 1 < degree; j++) result[j] = result[j + 1];
        result[degree - 1] = 0;
        for (u8 j = 0; j < degree; j++) result[j] ^= gfMul(divisor[j], factor);
    }
}

// --- Repères --------------------------------------------------------------------------------
static void drawFinder(s16 cx, s16 cy)
{
    for (s16 dy = -4; dy <= 4; dy++)
        for (s16 dx = -4; dx <= 4; dx++)
        {
            const s16 x = cx + dx, y = cy + dy;
            if (x < 0 || y < 0 || x >= size || y >= size) continue;
            const s16 d = max(abs(dx), abs(dy));
            setFunction(x, y, d != 2 && d != 4);
        }
}

static void drawFormat(u8 mask)
{
    const u16 data = (FORMAT_ECC_M << 3) | mask;
    u16 rem = data;
    for (u16 i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >> 9) * 0x537);
    const u16 bits = ((data << 10) | rem) ^ 0x5412;
#define BIT(i) ((bits >> (i)) & 1)
    for (u16 i = 0; i <= 5; i++) setFunction(8, i, BIT(i));
    setFunction(8, 7, BIT(6));
    setFunction(8, 8, BIT(7));
    setFunction(7, 8, BIT(8));
    for (u16 i = 9; i < 15; i++) setFunction(14 - i, 8, BIT(i));
    for (u16 i = 0; i < 8; i++) setFunction(size - 1 - i, 8, BIT(i));
    for (u16 i = 8; i < 15; i++) setFunction(8, size - 15 + i, BIT(i));
#undef BIT
    setFunction(8, size - 8, TRUE);     // module toujours foncé
}

static void drawFunctionPatterns(u8 version)
{
    for (u16 i = 0; i < size; i++)
    {
        setFunction(6, i, (i & 1) == 0);
        setFunction(i, 6, (i & 1) == 0);
    }
    drawFinder(3, 3);
    drawFinder(size - 4, 3);
    drawFinder(3, size - 4);
    if (version >= 2)           // un seul motif d'alignement jusqu'à la version 6
    {
        const s16 c = size - 7;
        for (s16 dy = -2; dy <= 2; dy++)
            for (s16 dx = -2; dx <= 2; dx++)
                setFunction(c + dx, c + dy, max(abs(dx), abs(dy)) != 1);
    }
    drawFormat(0);              // réserve la place des bits de format
}

// Données en zigzag, par colonnes de 2 modules en partant du coin bas droit.
static void placeData(u16 count)
{
    u16 i = 0;
    const u16 bits = count * 8;
    for (s16 right = size - 1; right >= 1; right -= 2)
    {
        if (right == 6) right = 5;
        const bool upward = ((right + 1) & 2) == 0;
        for (u16 vert = 0; vert < size; vert++)
            for (u16 j = 0; j < 2; j++)
            {
                const u16 x = right - j;
                const u16 y = upward ? size - 1 - vert : vert;
                if (cell[y][x] & FUNCTION) continue;
                if (i < bits && ((finalBytes[i >> 3] >> (7 - (i & 7))) & 1)) cell[y][x] = 1;
                i++;
            }
    }
}

// Les 8 masques de la norme, sans division (lente sur 68000) : x % 3, y % 3 et (x / 3) % 2
// sont tenus par des compteurs, et x * y % 3 vient d'une table.
static const u8 MUL3[3][3] = { { 0, 0, 0 }, { 0, 1, 2 }, { 0, 2, 1 } };

static void applyMask(u8 mask)
{
    u8 y3 = 0;
    for (u16 y = 0; y < size; y++)
    {
        u8 x3 = 0, xDiv3 = 0;
        for (u16 x = 0; x < size; x++)
        {
            if (!(cell[y][x] & FUNCTION))
            {
                const u8 xy2 = x & y & 1, xy3 = MUL3[x3][y3];
                bool flip;
                switch (mask)
                {
                    case 0: flip = ((x + y) & 1) == 0; break;
                    case 1: flip = (y & 1) == 0; break;
                    case 2: flip = x3 == 0; break;
                    case 3: flip = x3 + y3 == 0 || x3 + y3 == 3; break;
                    case 4: flip = ((xDiv3 + (y >> 1)) & 1) == 0; break;
                    case 5: flip = xy2 + xy3 == 0; break;
                    case 6: flip = ((xy2 + xy3) & 1) == 0; break;
                    default: flip = ((((x + y) & 1) + xy3) & 1) == 0; break;
                }
                if (flip) cell[y][x] ^= 1;
            }
            if (++x3 == 3)
            {
                x3 = 0;
                xDiv3 ^= 1;
            }
        }
        if (++y3 == 3) y3 = 0;
    }
}

// Pénalités de la norme : suites de 5 modules ou plus, carrés 2x2, équilibre clair/foncé. La
// règle des motifs 1:1:3:1:1 est omise : le masque choisi reste valide, au pire un peu moins bon.
static u16 penalty(void)
{
    u16 result = 0, darkCount = 0;
    for (u16 a = 0; a < size; a++)
    {
        u16 runRow = 1, runCol = 1;
        for (u16 b = 1; b < size; b++)
        {
            if ((cell[a][b] & 1) == (cell[a][b - 1] & 1)) runRow++;
            else runRow = 1;
            if (runRow == 5) result += 3;
            else if (runRow > 5) result++;
            if ((cell[b][a] & 1) == (cell[b - 1][a] & 1)) runCol++;
            else runCol = 1;
            if (runCol == 5) result += 3;
            else if (runCol > 5) result++;
        }
    }
    for (u16 y = 0; y < size; y++)
        for (u16 x = 0; x < size; x++)
        {
            const u8 c = cell[y][x] & 1;
            darkCount += c;
            if (x + 1 < size && y + 1 < size && (cell[y][x + 1] & 1) == c
                && (cell[y + 1][x] & 1) == c && (cell[y + 1][x + 1] & 1) == c)
                result += 3;
        }
    const s16 total = size * size;
    const s16 k = (abs((s16) (darkCount * 20) - total * 10) + total - 1) / total - 1;
    return result + k * 10;
}

bool scores_qrEncode(const char* text, ScoresQr* out)
{
    out->size = 0;
    if (!gfExp[0]) gfInit();
    const u16 length = strlen(text);
    for (u16 i = 0; i < length; i++)
        if (alnumValue(text[i]) < 0) return FALSE;

    const u16 dataBits = 4 + 9 + 11 * (length / 2) + 6 * (length % 2);
    u8 version = 1;
    while (version <= SCORES_QR_MAX_VERSION && dataBits > DATA_CODEWORDS[version] * 8) version++;
    if (version > SCORES_QR_MAX_VERSION) return FALSE;

    // Flux de bits : mode alphanumérique, longueur, paires de caractères, fin et bourrage.
    const u16 capacity = DATA_CODEWORDS[version];
    memset(codewords, 0, sizeof(codewords));
    bitLength = 0;
    appendBits(0x2, 4);
    appendBits(length, 9);
    for (u16 i = 0; i + 1 < length; i += 2)
        appendBits(alnumValue(text[i]) * 45 + alnumValue(text[i + 1]), 11);
    if (length & 1) appendBits(alnumValue(text[length - 1]), 6);
    appendBits(0, min(4, capacity * 8 - bitLength));
    appendBits(0, (8 - (bitLength & 7)) & 7);
    for (u8 pad = 0xEC; bitLength < capacity * 8; pad ^= 0xEC ^ 0x11) appendBits(pad, 8);

    // Correction d'erreurs par bloc, puis entrelacement des blocs (données, puis correction).
    const u8 blocks = BLOCKS[version], ec = EC_PER_BLOCK[version];
    const u8 blockLen = capacity / blocks;
    u8 divisor[MAX_EC], remainder[MAX_EC];
    rsDivisor(ec, divisor);
    u16 n = 0;
    for (u8 i = 0; i < blockLen; i++)
        for (u8 b = 0; b < blocks; b++) finalBytes[n++] = codewords[b * blockLen + i];
    for (u8 b = 0; b < blocks; b++)
    {
        rsRemainder(codewords + b * blockLen, blockLen, divisor, ec, remainder);
        for (u8 i = 0; i < ec; i++) finalBytes[capacity + i * blocks + b] = remainder[i];
    }

    size = 17 + 4 * version;
    memset(cell, 0, sizeof(cell));
    drawFunctionPatterns(version);
    placeData(capacity + ec * blocks);

    u8 best = 0;
    u16 bestPenalty = 0xFFFF;
    for (u8 mask = 0; mask < 8; mask++)
    {
        applyMask(mask);
        drawFormat(mask);
        const u16 p = penalty();
        if (p < bestPenalty)
        {
            bestPenalty = p;
            best = mask;
        }
        applyMask(mask);        // le masque est une inversion : l'appliquer deux fois l'annule
    }
    applyMask(best);
    drawFormat(best);

    out->size = size;
    for (u16 y = 0; y < size; y++)
        for (u16 x = 0; x < size; x++) out->dark[y][x] = cell[y][x] & 1;
    return TRUE;
}
