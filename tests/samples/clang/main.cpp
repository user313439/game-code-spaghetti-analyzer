#include "context.hpp"
#define MAKE_ALPHA(name) int name() { return N::over(1); }
#define MAKE_BETA(name) int name() { return N::over(1.0); }
MAKE_ALPHA(alpha)
MAKE_BETA(beta)
static int global_state;
int N::Node::counter = 0;
N::Node::Node() {}
N::Node::~Node() {}
int N::Node::Update(int value) {
    auto nested = [] { if (true) return 1; return 0; };
    if (value && global_state) value++;
    for (int i = 0; i < 1; ++i) value++;
    while (value < 2) value++;
    do { value++; } while (value < 3);
    switch (value) { case 1: value++; break; default: value--; }
    value = value ? value : global_state;
    try { value++; } catch (...) { value--; }
    value = value || global_state;
    counter++;
    int local = value;
    int (*pointer)(int) = N::over;
    return N::over(local) + N::over(1.0) + nested() + pointer(local);
}
#if FEATURE
int active() { return global_state; }
#else
int inactive() { return 0; }
#endif
