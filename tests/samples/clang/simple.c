#define DECLARE_C(name) int name(int x) { if (x) return 1; return 0; }
DECLARE_C(c_macro)
static int c_state;
int c_loop(int x) {
    switch (x) { case 1: x++; break; default: x--; }
    if (x && c_state || x) x = x ? 1 : 2;
    return x;
}
