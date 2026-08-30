# Research

**Decision**: 文件 JSON outbox 作为至少一次缓冲；消费按 event_id 幂等。  
**Alternatives**: 仅内存队列（禁止）；Kafka（SF04 可后续替换 Backend，本 SF 先证明语义）。
