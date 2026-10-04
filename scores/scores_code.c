#include "scores_code.h"

#define VERSION      1
#define DELTA        0x9E3779B9
#define MAC_KEY_XOR  0xA5A5A5A5

static const char BASE32[] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

static void xteaEncrypt(u32* v0, u32* v1, const u32* key)
{
    u32 a = *v0, b = *v1, sum = 0;
    for (u16 i = 0; i < 32; i++)
    {
        a += (((b << 4) ^ (b >> 5)) + b) ^ (sum + key[sum & 3]);
        sum += DELTA;
        b += (((a << 4) ^ (a >> 5)) + a) ^ (sum + key[(sum >> 11) & 3]);
    }
    *v0 = a;
    *v1 = b;
}

static u16 pseudoIndex(char c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A' + 1;
    if (c >= '0' && c <= '9') return c - '0' + 27;
    return 0;                   // espace, fin de chaîne ou caractère non accepté
}

// 6 caractères en base 37 : tient dans 32 bits (37^6 < 2^32). Après la fin de la chaîne : espaces.
static u32 pseudoHalf(const char* p, u16 from, u16 length)
{
    u32 value = 0;
    for (u16 i = from; i < from + 6; i++) value = value * 37 + (i < length ? pseudoIndex(p[i]) : 0);
    return value;
}

void scores_makeCode(const u32 key[4], const char* pseudo, u32 score, u16 nonce, char* out)
{
    u16 length = 0;
    while (length < SCORES_PSEUDO_LENGTH && pseudo[length]) length++;
    const u32 h1 = pseudoHalf(pseudo, 0, length), h2 = pseudoHalf(pseudo, 6, length);
    if (score > SCORES_SCORE_MAX) score = SCORES_SCORE_MAX;
    u32 w[4] = {
        ((u32) VERSION << 28) | (h1 >> 4),
        ((h1 & 0xF) << 28) | (h2 >> 4),
        ((h2 & 0xF) << 28) | (score << 8) | ((nonce >> 4) & 0xFF),
        (u32) (nonce & 0xF) << 28,
    };

    // Signature : CBC-MAC des 100 premiers bits, avec une clé dérivée.
    u32 macKey[4];
    for (u16 i = 0; i < 4; i++) macKey[i] = key[i] ^ MAC_KEY_XOR;
    u32 a = w[0], b = w[1];
    xteaEncrypt(&a, &b, macKey);
    a ^= w[2];
    b ^= w[3];
    xteaEncrypt(&a, &b, macKey);
    w[3] |= a >> 4;

    // Chiffrement CBC (vecteur nul) des 128 bits.
    xteaEncrypt(&w[0], &w[1], key);
    w[2] ^= w[0];
    w[3] ^= w[1];
    xteaEncrypt(&w[2], &w[3], key);

    // Base 32 : 26 caractères de 5 bits pour 128 bits (les 2 bits de tête sont nuls).
    for (s16 i = SCORES_CODE_LENGTH - 1; i >= 0; i--)
    {
        out[i] = BASE32[w[3] & 31];
        w[3] = (w[3] >> 5) | (w[2] << 27);
        w[2] = (w[2] >> 5) | (w[1] << 27);
        w[1] = (w[1] >> 5) | (w[0] << 27);
        w[0] >>= 5;
    }
    out[SCORES_CODE_LENGTH] = 0;
}

bool scores_makeUrl(const char* base, const char* code, char* out, u16 size)
{
    if (strlen(base) + strlen(code) + 1 > size) return FALSE;
    strcpy(out, base);
    strcat(out, code);
    return TRUE;
}
