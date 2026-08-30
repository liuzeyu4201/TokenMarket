# Research

**Decision**: Coordinator + Backend 接口；默认 Memory 互斥锁实现原子 Incr/Occupy/Epoch。  
**Rationale**: 不引入新微服务；先证明语义。Redis 适配器可实现同一接口。  
**Alternatives**: 直接加 go-redis — 可后续插拔，不阻塞语义验收。
