// C++ namespace 추적 테스트용 합성 샘플.

namespace OpenRA {

class Actor {
public:
    int health;
    void Tick() {
        if (health > 0) {
            health--;
        }
    }
};

namespace Network {

class Server {
public:
    void StartListening() {
        for (int i = 0; i < 10; i++) {
            if (i % 2 == 0) {
                // listen
            }
        }
    }
};

}  // namespace Network

}  // namespace OpenRA

// C++17 nested namespace
namespace Game::Physics {

class Collider {
public:
    void Update() {
        // physics tick
    }

    struct Bounds {
        int x, y, w, h;
    };
};

}  // namespace Game::Physics
