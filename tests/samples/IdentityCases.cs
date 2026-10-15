namespace IdentityCases;

public class Box { }
public class Box<T> { }
public class Worker
{
    public void Work(int value) { }
    public void Work(string value) { }
}
public class OtherWorker { public void Work(int value) { } }
public class Loop
{
    public void Update() { new Worker().Work(1); }
}
public class Factory { public object Make() { return new Box<int>(); } }
public class LocalLoop
{
    public void Update() { void Work() { } Work(); }
    public void Work() { }
}
