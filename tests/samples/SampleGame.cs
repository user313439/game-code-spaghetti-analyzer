// 테스트용 샘플 — 게임 엔진 스타일의 C# 코드.
// CC 계산 검증을 위해 다양한 분기와 패턴을 포함한다.

using System;
using System.Collections.Generic;

namespace SampleGame.Core
{
    public class Actor
    {
        public static int InstanceCount = 0; // GlobalState 검출 대상

        public string Name { get; set; } = "";
        public int Health { get; set; }
        public bool IsActive { get; set; }

        public Actor(string name, int health)
        {
            Name = name;
            Health = health;
            IsActive = true;
            InstanceCount++;
        }

        // CC = 1 (분기 없음)
        public void Reset()
        {
            Health = 100;
            IsActive = true;
        }

        // CC = 1 + 2 (if, if) = 3
        public void TakeDamage(int amount)
        {
            if (amount <= 0) return;
            Health -= amount;
            if (Health <= 0)
            {
                IsActive = false;
            }
        }

        // CC = 1 + 1 (&&) + 1 (if) + 1 (foreach) + 1 (case) + 1 (case) + 1 (?:) = 7
        public string DescribeStatus(List<string> tags, int mode)
        {
            if (!IsActive && Health <= 0) return "dead";

            foreach (var tag in tags)
            {
                Console.WriteLine(tag);
            }

            string result;
            switch (mode)
            {
                case 1: result = "low"; break;
                case 2: result = "high"; break;
                default: result = "normal"; break;
            }

            return Health > 50 ? result + "-healthy" : result + "-injured";
        }
    }

    public static class GameManager
    {
        // GlobalState 검출 대상 (정적 + mutable)
        public static Actor? CurrentPlayer;

        // CC = 1 + 1 (||) = 2
        public static bool CanAct(Actor a)
        {
            return a.IsActive || a.Health > 0;
        }

        // CC = 1 + 1 (for) + 1 (if) = 3
        public static int SumHealth(IEnumerable<Actor> actors)
        {
            int total = 0;
            foreach (var a in actors)
            {
                if (a.IsActive) total += a.Health;
            }
            return total;
        }
    }

    public interface ITickable
    {
        void Tick(float delta);
    }

    public struct Position
    {
        public float X;
        public float Y;

        public Position(float x, float y) { X = x; Y = y; }
    }
}
