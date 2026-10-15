namespace N {
struct Node {
    static int counter;
    Node();
    ~Node();
    int Update(int value);
    int Inline() { return 9; }
};
int over(int value);
int over(double value);
}
