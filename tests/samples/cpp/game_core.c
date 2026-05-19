#include <stdio.h>
#include "render.h"

/* 게임 루프 모듈 — Phase 2 분석기 검증용 합성 샘플 */

static int tick_counter = 0;
static int frame_index = 0;
extern int player_count;

void IncCounter(void) {
    tick_counter++;
}

int Tick(void) {
    if (tick_counter > 1000) {
        return -1;
    }
    if (player_count <= 0) {
        return 0;
    }
    IncCounter();
    return tick_counter;
}

void RenderFrame(int who) {
    for (int i = 0; i < who; i++) {
        if (i > 10 && frame_index < 100) {
            DrawSprite(i, frame_index);
        } else if (i == 0 || frame_index > 50) {
            DrawSprite(0, 0);
        }
    }
    frame_index++;
}

void MainLoop(void) {
    int rc = 0;
    while (rc >= 0) {
        rc = Tick();
        RenderFrame(player_count);
    }
}
