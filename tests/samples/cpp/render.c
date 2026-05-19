#include "render.h"
#include <stdio.h>

static int draw_calls = 0;

void DrawSprite(int x, int y) {
    if (x < 0 || y < 0) {
        return;
    }
    draw_calls++;
}

void ClearScreen(void) {
    draw_calls = 0;
}
