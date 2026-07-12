# TokenMarket Python 后端与数据库设计规范

> 版本：V0.1-0.2
> 适用范围：api-service / billing-service / admin-service
> 技术栈：FastAPI + SQLAlchemy（async） + PostgreSQL + Redis + Kafka

---

## 1. Python 项目目录结构

以 `api-service` 为例，其他服务（`billing-service`、`admin-service`）采用同构结构：

```
api-service/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口：创建 App、注册路由、挂载事件
│   ├── dependencies.py         # 全局依赖注入（DB Session、Redis、Kafka Producer）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic Settings 配置中心
│   │   ├── exceptions.py       # 自定义异常体系（BizException / ValidationError）
│   │   ├── logging.py          # 统一日志配置（structlog JSON）
│   │   └── middleware.py       # 中间件：请求ID、耗时日志、异常处理、CORS
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py       # 版本路由聚合
│   │   │   ├── users.py        # 用户相关接口
│   │   │   ├── sellers.py      # 卖家相关接口
│   │   │   ├── buyers.py       # 买家相关接口
│   │   │   ├── points.py       # 积分相关接口
│   │   │   └── notifications.py # 通知相关接口
│   │   └── deps.py             # 接口依赖：auth、分页、权限校验
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── base.py             # 基础响应模型、分页模型
│   │   ├── user.py             # 用户请求/响应模型
│   │   ├── seller.py           # 卖家请求/响应模型
│   │   └── buyer.py            # 买家请求/响应模型
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py     # 用户业务逻辑
│   │   ├── seller_service.py   # 卖家业务逻辑
│   │   └── buyer_service.py    # 买家业务逻辑
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py             # 抽象 Repository 接口
│   │   ├── user_repository.py  # 用户数据访问
│   │   └── seller_repository.py # 卖家数据访问
│   ├── models/
│   │   ├── __init__.py
│   │   └── base.py             # SQLAlchemy ORM 基础类 + 通用字段 mixin
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── user.py             # 用户领域模型（纯 dataclass）
│   │   ├── money.py            # Money 值对象
│   │   └── events.py           # 领域事件定义
│   └── tasks/
│       ├── __init__.py
│       ├── celery_app.py       # Celery 配置（billing-service 等需要可靠执行时使用）
│       └── async_tasks.py      # asyncio 后台任务（非关键、可丢失）
├── alembic/                    # 数据库迁移
│   ├── versions/
│   └── env.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # pytest 共享 fixtures
│   ├── unit/                   # 单元测试
│   ├── integration/            # 集成测试
│   └── factories/              # factory_boy 工厂类
├── Dockerfile                  # 多阶段构建
├── pyproject.toml              # 依赖 + 工具配置
└── README.md
```

**目录分层语义：**

| 目录 | 职责 | 依赖规则 |
|---|---|---|
| `api/` | HTTP 协议适配：路由定义、参数校验、响应包装 | 可依赖 `services`、`schemas`、`deps` |
| `schemas/` | 数据序列化/反序列化：Pydantic 模型 | 不依赖任何内部层 |
| `services/` | 业务用例编排：一个用例一个类，封装业务规则 | 可依赖 `repositories`、`domain` |
| `repositories/` | 数据持久化：SQLAlchemy 查询、事务边界 | 可依赖 `models` |
| `models/` | ORM 映射：表结构定义、关系声明 | 不依赖任何内部层 |
| `domain/` | 纯领域逻辑：不可变值对象、实体业务方法、领域事件 | 不依赖任何外部技术框架 |
| `tasks/` | 异步任务执行：Celery / asyncio | 可依赖 `services` |
| `core/` | 横切关注点：配置、日志、异常、中间件 | 可被所有层依赖 |

---

## 2. SOLID 原则在 Python 中的具体实践

### 2.1 S — Single Responsibility（单一职责）

`UserService` 只处理用户业务，计费逻辑委托给 `BillingService`。二者通过**接口**交互，而非直接耦合。

```python
# app/services/interfaces.py
from abc import ABC, abstractmethod
from typing import Optional
from decimal import Decimal
from uuid import UUID


class IBillingService(ABC):
    """计费服务接口：用户服务只依赖此接口，不依赖具体实现。"""

    @abstractmethod
    async def deduct_balance(self, user_id: UUID, amount: Decimal, currency: str) -> bool:
        """从用户余额扣款。"""
        ...

    @abstractmethod
    async def get_available_balance(self, user_id: UUID, currency: str) -> Decimal:
        """获取可用余额。"""
        ...
```

```python
# app/services/user_service.py
from uuid import UUID
from typing import Optional
from app.services.interfaces import IBillingService
from app.repositories.base import IUserRepository
from app.schemas.user import UserUpdateRequest, UserResponse
from app.core.exceptions import BizException


class UserService:
    """
    用户服务：只处理用户生命周期管理（注册、信息更新、查询）。
    计费相关操作通过 IBillingService 接口委托，完全不关心计费内部实现。
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        billing_service: IBillingService,
    ):
        self._user_repo = user_repo
        self._billing_service = billing_service

    async def update_user_profile(
        self, user_id: UUID, req: UserUpdateRequest
    ) -> UserResponse:
        """更新用户资料：纯用户业务，不涉及计费。"""
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise BizException(code="USER_NOT_FOUND", message="用户不存在")
        # ... 更新逻辑
        return UserResponse.from_orm(user)

    async def check_purchase_eligibility(self, user_id: UUID, estimated_cost: float) -> bool:
        """
        检查用户是否有足够余额购买：仅查询余额，不直接操作计费数据。
        通过 IBillingService 接口调用，而非直接操作 balances 表。
        """
        balance = await self._billing_service.get_available_balance(user_id, "CNY")
        return balance >= estimated_cost
```

```python
# app/services/billing_service.py
from decimal import Decimal
from uuid import UUID
from app.services.interfaces import IBillingService
from app.repositories.base import IBalanceRepository


class BillingService(IBillingService):
    """计费服务具体实现：封装余额、结算、Escrow 等逻辑。"""

    def __init__(self, balance_repo: IBalanceRepository):
        self._balance_repo = balance_repo

    async def deduct_balance(self, user_id: UUID, amount: Decimal, currency: str) -> bool:
        return await self._balance_repo.deduct(user_id, amount, currency)

    async def get_available_balance(self, user_id: UUID, currency: str) -> Decimal:
        return await self._balance_repo.get_available(user_id, currency)
```

---

### 2.2 O — Open/Closed（开闭原则）

新增 AI 平台时，只需添加新的 `PlatformPricingStrategy`，不修改 `PricingEngine` 核心代码。

```python
# app/domain/pricing.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Type


@dataclass(frozen=True)
class Usage:
    """用量值对象（不可变）。"""
    prompt_tokens: int
    completion_tokens: int


# ---------------------------------------------------------------------------
# 策略接口
# ---------------------------------------------------------------------------
class PlatformPricingStrategy(ABC):
    """各平台定价策略抽象：每个平台一个实现。"""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        ...

    @abstractmethod
    def calculate_cost(self, usage: Usage) -> Decimal:
        """根据用量计算费用。"""
        ...


# ---------------------------------------------------------------------------
# 具体策略实现
# ---------------------------------------------------------------------------
class ZhipuPricingStrategy(PlatformPricingStrategy):
    """智谱 GLM 定价策略。"""

    @property
    def platform_name(self) -> str:
        return "zhipu"

    def calculate_cost(self, usage: Usage) -> Decimal:
        # 智谱：prompt 0.005元/1K tokens，completion 0.01元/1K tokens
        cost = (
            Decimal(usage.prompt_tokens) * Decimal("0.005") / Decimal("1000")
            + Decimal(usage.completion_tokens) * Decimal("0.01") / Decimal("1000")
        )
        return cost.quantize(Decimal("0.0001"))


class VolcanoPricingStrategy(PlatformPricingStrategy):
    """火山方舟定价策略。"""

    @property
    def platform_name(self) -> str:
        return "volcano"

    def calculate_cost(self, usage: Usage) -> Decimal:
        # 火山：统一 0.008元/1K tokens
        total = usage.prompt_tokens + usage.completion_tokens
        return (Decimal(total) * Decimal("0.008") / Decimal("1000")).quantize(Decimal("0.0001"))


class ClaudePricingStrategy(PlatformPricingStrategy):
    """Claude 定价策略。"""

    @property
    def platform_name(self) -> str:
        return "claude"

    def calculate_cost(self, usage: Usage) -> Decimal:
        # Claude：prompt 0.008$/1K，completion 0.024$/1K（按美元计价，后续汇率转换）
        cost = (
            Decimal(usage.prompt_tokens) * Decimal("0.008") / Decimal("1000")
            + Decimal(usage.completion_tokens) * Decimal("0.024") / Decimal("1000")
        )
        return cost.quantize(Decimal("0.0001"))


# ---------------------------------------------------------------------------
# 定价引擎：核心逻辑不随平台新增而修改
# ---------------------------------------------------------------------------
class PricingEngine:
    """
    定价引擎：注册所有策略，根据平台名称路由。
    新增平台时，只需调用 register_strategy() 注册新策略，无需修改引擎内部逻辑。
    """

    def __init__(self):
        self._strategies: Dict[str, PlatformPricingStrategy] = {}

    def register_strategy(self, strategy: PlatformPricingStrategy) -> None:
        self._strategies[strategy.platform_name] = strategy

    def calculate(self, platform: str, usage: Usage) -> Decimal:
        strategy = self._strategies.get(platform)
        if not strategy:
            raise ValueError(f"不支持的定价平台: {platform}")
        return strategy.calculate_cost(usage)
```

```python
# 初始化示例（在 dependencies.py 或 lifespan 中）
from app.domain.pricing import PricingEngine, ZhipuPricingStrategy, VolcanoPricingStrategy

engine = PricingEngine()
engine.register_strategy(ZhipuPricingStrategy())
engine.register_strategy(VolcanoPricingStrategy())
engine.register_strategy(ClaudePricingStrategy())
# 新增 MiniMax 时：仅新增 MiniMaxPricingStrategy 类并 register，不修改 PricingEngine
```

---

### 2.3 L — Liskov Substitution（里氏替换）

所有 `Repository` 实现可替换：`SQLAlchemyRepo` 与 `MockRepo` 在单元测试中自由切换。

```python
# app/repositories/base.py
from abc import ABC, abstractmethod
from typing import Optional, List, Generic, TypeVar
from uuid import UUID

T = TypeVar("T")


class IReadable(ABC, Generic[T]):
    """可读接口：最小职责拆分。"""

    @abstractmethod
    async def get_by_id(self, entity_id: UUID) -> Optional[T]:
        ...

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        ...


class IWritable(ABC, Generic[T]):
    """可写接口。"""

    @abstractmethod
    async def create(self, entity: T) -> T:
        ...

    @abstractmethod
    async def update(self, entity: T) -> T:
        ...


class IDeletable(ABC, Generic[T]):
    """可删除接口。"""

    @abstractmethod
    async def delete(self, entity_id: UUID) -> bool:
        ...


class IRepository(IReadable[T], IWritable[T], IDeletable[T], ABC):
    """完整 Repository 接口。"""
    pass


class IUserRepository(IRepository["User"], ABC):
    """用户 Repository 接口：增加领域专属查询。"""

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional["User"]:
        ...

    @abstractmethod
    async def get_by_phone(self, phone: str) -> Optional["User"]:
        ...
```

```python
# app/repositories/user_repository.py
from uuid import UUID
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.base import IUserRepository
from app.models.user import User as UserModel
from app.domain.user import User as UserDomain


class SQLAlchemyUserRepository(IUserRepository):
    """SQLAlchemy 实现：生产环境使用。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: UUID) -> Optional[UserDomain]:
        stmt = select(UserModel).where(UserModel.id == user_id, UserModel.is_deleted == False)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return orm.to_domain() if orm else None

    async def get_by_email(self, email: str) -> Optional[UserDomain]:
        stmt = select(UserModel).where(UserModel.email == email, UserModel.is_deleted == False)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return orm.to_domain() if orm else None

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[UserDomain]:
        stmt = select(UserModel).where(UserModel.is_deleted == False).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [orm.to_domain() for orm in result.scalars().all()]

    async def create(self, entity: UserDomain) -> UserDomain:
        orm = UserModel.from_domain(entity)
        self._session.add(orm)
        await self._session.flush()
        return orm.to_domain()

    async def update(self, entity: UserDomain) -> UserDomain:
        orm = await self._session.get(UserModel, entity.id)
        if not orm:
            raise ValueError("User not found")
        orm.update_from_domain(entity)
        await self._session.flush()
        return orm.to_domain()

    async def delete(self, user_id: UUID) -> bool:
        orm = await self._session.get(UserModel, user_id)
        if orm:
            orm.is_deleted = True
            await self._session.flush()
            return True
        return False

    async def get_by_phone(self, phone: str) -> Optional[UserDomain]:
        stmt = select(UserModel).where(UserModel.phone == phone, UserModel.is_deleted == False)
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return orm.to_domain() if orm else None
```

```python
# tests/unit/mocks.py — 单元测试中使用 MockRepo，无需真实数据库
from typing import Optional, List, Dict
from uuid import UUID
from app.repositories.base import IUserRepository
from app.domain.user import User


class MockUserRepository(IUserRepository):
    """Mock 实现：内存存储，测试用。可完全替换 SQLAlchemyUserRepository。"""

    def __init__(self):
        self._data: Dict[UUID, User] = {}

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        return self._data.get(user_id)

    async def get_by_email(self, email: str) -> Optional[User]:
        for user in self._data.values():
            if user.email == email:
                return user
        return None

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[User]:
        return list(self._data.values())[offset:offset + limit]

    async def create(self, entity: User) -> User:
        self._data[entity.id] = entity
        return entity

    async def update(self, entity: User) -> User:
        self._data[entity.id] = entity
        return entity

    async def delete(self, user_id: UUID) -> bool:
        if user_id in self._data:
            del self._data[user_id]
            return True
        return False

    async def get_by_phone(self, phone: str) -> Optional[User]:
        for user in self._data.values():
            if user.phone == phone:
                return user
        return None
```

---

### 2.4 I — Interface Segregation（接口隔离）

拆分为小接口：`IReadable` / `IWritable` / `IDeletable`，避免让不需要的类实现不需要的方法。

```python
# app/services/audit_log_service.py
from app.repositories.base import IReadable
from app.domain.audit_log import AuditLog
from uuid import UUID
from typing import List


class AuditLogReadService:
    """
    审计日志只读服务：仅依赖 IReadable 接口，不依赖完整 Repository。
    如果 AuditLog 的存储层只提供查询能力，无需强制实现 create/update/delete。
    """

    def __init__(self, audit_repo: IReadable[AuditLog]):
        self._repo = audit_repo

    async def get_recent_logs(self, count: int = 50) -> List[AuditLog]:
        return await self._repo.list_all(limit=count, offset=0)
```

```python
# app/repositories/audit_log_repository.py
from app.repositories.base import IReadable
from app.domain.audit_log import AuditLog
from typing import Optional, List
from uuid import UUID


class AuditLogRepository(IReadable[AuditLog]):
    """
    审计日志存储：只实现 IReadable（只读）。
    写入通过 Kafka consumer 异步批量写入，不走此接口。
    """

    async def get_by_id(self, log_id: UUID) -> Optional[AuditLog]:
        ...

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[AuditLog]:
        ...
    # 不需要实现 create / update / delete
```

---

### 2.5 D — Dependency Inversion（依赖倒置）

`Service` 层依赖 `Repository` 接口，不依赖具体实现。通过 `Depends` / 构造函数注入。

```python
# app/api/deps.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db_session
from app.repositories.user_repository import SQLAlchemyUserRepository
from app.repositories.base import IUserRepository
from app.services.user_service import UserService
from app.services.billing_service import BillingService
from app.repositories.balance_repository import SQLAlchemyBalanceRepository


async def get_user_repo(
    session: AsyncSession = Depends(get_db_session),
) -> IUserRepository:
    """依赖注入：返回 Repository 接口，而非具体实现。"""
    return SQLAlchemyUserRepository(session)


async def get_billing_service(
    session: AsyncSession = Depends(get_db_session),
) -> BillingService:
    """依赖注入：BillingService 内部依赖 IBalanceRepository 接口。"""
    balance_repo = SQLAlchemyBalanceRepository(session)
    return BillingService(balance_repo)


async def get_user_service(
    user_repo: IUserRepository = Depends(get_user_repo),
    billing_service: BillingService = Depends(get_billing_service),
) -> UserService:
    """依赖注入：UserService 依赖 IUserRepository 接口和 IBillingService 接口。"""
    return UserService(user_repo=user_repo, billing_service=billing_service)
```

```python
# app/api/v1/users.py
from fastapi import APIRouter, Depends
from app.api.deps import get_user_service
from app.services.user_service import UserService
from app.schemas.user import UserResponse, UserUpdateRequest
from app.schemas.base import BaseResponse
from uuid import UUID

router = APIRouter()


@router.patch("/{user_id}", response_model=BaseResponse[UserResponse])
async def update_user(
    user_id: UUID,
    req: UserUpdateRequest,
    service: UserService = Depends(get_user_service),
):
    """更新用户信息：Service 层完全由接口驱动，可替换。"""
    result = await service.update_user_profile(user_id, req)
    return BaseResponse(data=result)
```

---

## 3. FastAPI 接口设计规范

### 3.1 统一响应模型

所有接口返回统一结构，前端无需处理不同格式。

```python
# app/schemas/base.py
from typing import Optional, Generic, TypeVar, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import uuid4

T = TypeVar("T")


class BaseResponse(BaseModel, Generic[T]):
    """统一响应模型。"""

    code: str = Field(default="0", description="业务状态码：0=成功，其他=错误")
    message: str = Field(default="success", description="状态描述")
    data: Optional[T] = Field(default=None, description="业务数据")
    request_id: str = Field(default_factory=lambda: str(uuid4()), description="请求追踪ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PaginationParams(BaseModel):
    """通用分页参数。"""

    page: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页条数")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应包装。"""

    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    items: List[T] = Field(description="当前页数据")


class PagedBaseResponse(BaseResponse[PaginatedResponse[T]], Generic[T]):
    """分页的统一响应：data 内嵌 PaginatedResponse。"""
    pass
```

```python
# 使用示例
@router.get("/", response_model=PagedBaseResponse[UserResponse])
async def list_users(
    pagination: PaginationParams = Depends(),
    service: UserService = Depends(get_user_service),
):
    items, total = await service.list_users(pagination.page, pagination.page_size)
    return PagedBaseResponse(
        data=PaginatedResponse(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            items=items,
        )
    )
```

---

### 3.2 依赖注入设计

```python
# app/dependencies.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from redis.asyncio import Redis
from aiokafka import AIOKafkaProducer
from app.core.config import settings

# ---------------------------------------------------------------------------
# 数据库：每次请求创建 Session，响应后关闭
# ---------------------------------------------------------------------------
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # 连接池健康检查
)

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends 用：每个请求独立 Session。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Redis：连接池单例，通过请求状态传递
# ---------------------------------------------------------------------------
_redis_pool: Optional[Redis] = None


async def get_redis() -> Redis:
    """获取 Redis 连接（单例连接池）。"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )
    return _redis_pool


# ---------------------------------------------------------------------------
# Kafka Producer：单例，应用生命周期管理
# ---------------------------------------------------------------------------
_kafka_producer: Optional[AIOKafkaProducer] = None


async def get_kafka_producer() -> AIOKafkaProducer:
    """获取 Kafka Producer（单例）。"""
    global _kafka_producer
    if _kafka_producer is None:
        _kafka_producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        await _kafka_producer.start()
    return _kafka_producer


async def close_kafka_producer():
    """应用关闭时释放。"""
    global _kafka_producer
    if _kafka_producer:
        await _kafka_producer.stop()
        _kafka_producer = None
```

```python
# app/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.dependencies import close_kafka_producer
from app.core.middleware import RequestIDMiddleware, LoggingMiddleware, ExceptionMiddleware
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动/关闭钩子。"""
    # startup
    yield
    # shutdown
    await close_kafka_producer()


app = FastAPI(
    title="TokenMarket API",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册中间件
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(ExceptionMiddleware)

# 注册路由
app.include_router(api_router, prefix="/api/v1")
```

---

### 3.3 异步编程规范

```python
# 1. 所有 I/O 操作使用 async/await
# 2. 数据库使用 async SQLAlchemy (asyncpg)
# 3. 外部 HTTP 调用使用 aiohttp / httpx
# 4. 后台任务：关键用 Celery，非关键用 asyncio.create_task

# app/services/external_ai_service.py
import httpx
from typing import Dict, Any


class ExternalAIClient:
    """外部 AI 平台 HTTP 客户端：使用 httpx 异步调用。"""

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def chat_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """异步调用 AI 平台 chat completion。"""
        response = await self._client.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self._client.aclose()
```

```python
# 关键后台任务：使用 Celery（需要可靠执行，如结算、Escrow）
# app/tasks/celery_app.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "billing_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.settlement_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 单任务 5 分钟上限
)
```

```python
# app/tasks/settlement_tasks.py
from app.tasks.celery_app import celery_app
from app.services.settlement_service import SettlementService


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_settlement_batch(self, batch_id: str):
    """结算批次处理：Celery 任务，失败自动重试。"""
    try:
        service = SettlementService()  # 实际通过工厂/依赖注入获取
        service.process_batch(batch_id)
    except Exception as exc:
        raise self.retry(exc=exc)
```

```python
# 非关键后台任务：使用 asyncio.create_task（可丢失，如日志发送）
# app/services/notification_service.py
import asyncio
from typing import Optional
from app.dependencies import get_redis


class NotificationService:
    async def send_notification_async(self, user_id: str, message: str):
        """非关键通知：异步发送，不阻塞主流程，失败不影响业务。"""
        asyncio.create_task(self._do_send(user_id, message))

    async def _do_send(self, user_id: str, message: str):
        try:
            redis = await get_redis()
            await redis.publish(f"notifications:{user_id}", message)
        except Exception:
            # 非关键任务，失败仅记录日志，不抛异常
            pass
```

---

## 4. 数据库设计规范（重点）

### 4.1 设计原则

| 原则 | 说明 |
|---|---|
| **第三范式为主** | 消除冗余，保证数据一致性。 |
| **适度反范化** | 高频查询场景（如交易流水列表）允许冗余字段，用空间换时间。 |
| **通用字段** | 所有表必须有 `id`（UUID 主键）、`created_at`、`updated_at`、`is_deleted`（软删除）。 |
| **外键索引** | 所有外键必须建立索引，避免全表扫描。 |
| **枚举类型** | 使用 PostgreSQL ENUM 或整型常量，禁止直接用字符串（易出错、无约束）。 |

---

### 4.2 核心表设计（V0.1-0.2 最小集合）

#### 4.2.1 用户表 `users`

```sql
CREATE TYPE user_role AS ENUM ('buyer', 'seller', 'admin');
CREATE TYPE user_status AS ENUM ('active', 'suspended', 'deleted');

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    phone           VARCHAR(20) UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            user_role NOT NULL DEFAULT 'buyer',
    status          user_status NOT NULL DEFAULT 'active',
    nickname        VARCHAR(100),
    avatar_url      VARCHAR(500),
    -- 审计字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    version         INTEGER NOT NULL DEFAULT 1,          -- 乐观锁版本号

    CONSTRAINT uq_users_email_not_deleted UNIQUE (email, is_deleted)
);

CREATE INDEX idx_users_phone ON users(phone) WHERE is_deleted = FALSE;
CREATE INDEX idx_users_role ON users(role) WHERE is_deleted = FALSE;
CREATE INDEX idx_users_created_at ON users(created_at DESC);
```

#### 4.2.2 卖家原始 Key 表 `api_keys`

```sql
CREATE TYPE platform_enum AS ENUM ('zhipu', 'volcano', 'minimax', 'kimi', 'claude', 'gpt');
CREATE TYPE key_status AS ENUM ('active', 'inactive', 'revoked', 'expired');

CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    platform        platform_enum NOT NULL,
    -- 加密存储：原始 Key 经 AES-256-GCM 加密后存储
    encrypted_key   BYTEA NOT NULL,
    key_hash        VARCHAR(64) NOT NULL,                  -- SHA-256 哈希，用于快速查找/去重
    key_nonce       BYTEA NOT NULL,                        -- 加密 nonce
    key_tag         BYTEA NOT NULL,                        -- GCM auth tag
    -- 额度信息
    total_quota     NUMERIC(20, 6) NOT NULL DEFAULT 0,    -- 总额度（按平台单位）
    remaining_quota NUMERIC(20, 6) NOT NULL DEFAULT 0,    -- 剩余额度
    used_quota      NUMERIC(20, 6) NOT NULL DEFAULT 0,    -- 已用额度
    -- 状态
    status          key_status NOT NULL DEFAULT 'active',
    expires_at      TIMESTAMPTZ,                           -- 可选过期时间
    -- 审计字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT chk_api_keys_quota CHECK (remaining_quota >= 0),
    CONSTRAINT chk_api_keys_used CHECK (used_quota >= 0)
);

CREATE INDEX idx_api_keys_seller ON api_keys(seller_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_api_keys_platform ON api_keys(platform) WHERE is_deleted = FALSE;
CREATE INDEX idx_api_keys_status ON api_keys(status) WHERE is_deleted = FALSE;
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);    -- 用于快速去重检测
```

#### 4.2.3 代理 Key 表 `proxy_keys`

```sql
CREATE TABLE proxy_keys (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    api_key_id      UUID NOT NULL REFERENCES api_keys(id) ON DELETE RESTRICT,
    -- 代理 Key 信息
    proxy_key       VARCHAR(255) UNIQUE NOT NULL,          -- 买家使用的代理 Key（可明文，含随机前缀）
    proxy_key_hash  VARCHAR(64) NOT NULL,                   -- 哈希，用于快速校验
    -- 额度配置
    total_quota     NUMERIC(20, 6) NOT NULL DEFAULT 0,      -- 卖家分配给此代理 Key 的额度
    remaining_quota NUMERIC(20, 6) NOT NULL DEFAULT 0,
    used_quota      NUMERIC(20, 6) NOT NULL DEFAULT 0,
    -- 状态
    status          key_status NOT NULL DEFAULT 'active',
    expires_at      TIMESTAMPTZ,
    -- 审计字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT chk_proxy_keys_quota CHECK (remaining_quota >= 0)
);

CREATE INDEX idx_proxy_keys_seller ON proxy_keys(seller_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_proxy_keys_api_key ON proxy_keys(api_key_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_proxy_keys_hash ON proxy_keys(proxy_key_hash);
CREATE INDEX idx_proxy_keys_status ON proxy_keys(status) WHERE is_deleted = FALSE;
```

#### 4.2.4 挂售表 `listings`

```sql
CREATE TYPE listing_status AS ENUM ('active', 'paused', 'sold_out', 'expired', 'cancelled');
CREATE TYPE pricing_unit AS ENUM ('per_token', 'per_request', 'per_1k_tokens');

CREATE TABLE listings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    api_key_id      UUID NOT NULL REFERENCES api_keys(id) ON DELETE RESTRICT,
    -- 挂售信息
    platform        platform_enum NOT NULL,
    model_name      VARCHAR(100) NOT NULL,               -- 如 "glm-4", "claude-3-opus"
    total_amount    NUMERIC(20, 6) NOT NULL,              -- 总出售额度
    unit_price      NUMERIC(20, 8) NOT NULL,              -- 单价（CNY/单位）
    pricing_unit    pricing_unit NOT NULL DEFAULT 'per_1k_tokens',
    min_purchase    NUMERIC(20, 6) NOT NULL DEFAULT 1,    -- 最小购买量
    -- 状态
    status          listing_status NOT NULL DEFAULT 'active',
    expires_at      TIMESTAMPTZ,
    -- 审计字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT chk_listings_amount CHECK (total_amount > 0),
    CONSTRAINT chk_listings_price CHECK (unit_price >= 0)
);

CREATE INDEX idx_listings_seller ON listings(seller_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_listings_platform ON listings(platform) WHERE is_deleted = FALSE;
CREATE INDEX idx_listings_status ON listings(status) WHERE is_deleted = FALSE;
CREATE INDEX idx_listings_created_at ON listings(created_at DESC);
```

#### 4.2.5 交易流水表 `transactions`

```sql
CREATE TYPE transaction_type AS ENUM ('purchase', 'refund', 'settlement', 'escrow_release', 'adjustment');
CREATE TYPE transaction_status AS ENUM ('pending', 'completed', 'failed', 'reversed');

CREATE TABLE transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 参与方
    buyer_id        UUID REFERENCES users(id) ON DELETE RESTRICT,
    seller_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    listing_id      UUID REFERENCES listings(id) ON DELETE SET NULL,
    -- 交易信息
    type            transaction_type NOT NULL,
    status          transaction_status NOT NULL DEFAULT 'pending',
    amount          NUMERIC(20, 8) NOT NULL,              -- 交易金额（CNY）
    currency        VARCHAR(10) NOT NULL DEFAULT 'CNY',
    quantity        NUMERIC(20, 6) NOT NULL,              -- 交易额度数量
    platform        platform_enum NOT NULL,
    model_name      VARCHAR(100) NOT NULL,
    -- 幂等性
    idempotency_key VARCHAR(64) UNIQUE NOT NULL,          -- 幂等键：全局唯一，24h 去重
    -- Escrow 相关
    escrow_status   VARCHAR(20),                          -- 'locked', 'released', 'refunded'
    escrow_release_at TIMESTAMPTZ,
    -- 审计字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT chk_transactions_amount CHECK (amount >= 0),
    CONSTRAINT chk_transactions_quantity CHECK (quantity >= 0)
);

CREATE INDEX idx_transactions_buyer ON transactions(buyer_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_transactions_seller ON transactions(seller_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_transactions_listing ON transactions(listing_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_transactions_idempotency ON transactions(idempotency_key);
CREATE INDEX idx_transactions_status ON transactions(status) WHERE is_deleted = FALSE;
CREATE INDEX idx_transactions_created_at ON transactions(created_at DESC);
CREATE INDEX idx_transactions_escrow ON transactions(escrow_status) WHERE escrow_status IS NOT NULL;
```

#### 4.2.6 余额表 `balances`

```sql
CREATE TABLE balances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    currency        VARCHAR(10) NOT NULL DEFAULT 'CNY',
    available       NUMERIC(20, 8) NOT NULL DEFAULT 0,      -- 可用余额
    frozen          NUMERIC(20, 8) NOT NULL DEFAULT 0,      -- 冻结金额（Escrow）
    total           NUMERIC(20, 8) NOT NULL DEFAULT 0,      -- 总额 = available + frozen
    -- 审计字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT uq_balances_user_currency UNIQUE (user_id, currency, is_deleted),
    CONSTRAINT chk_balances_available CHECK (available >= 0),
    CONSTRAINT chk_balances_frozen CHECK (frozen >= 0),
    CONSTRAINT chk_balances_total CHECK (total = available + frozen)
);

CREATE INDEX idx_balances_user ON balances(user_id) WHERE is_deleted = FALSE;
```

#### 4.2.7 结算记录表 `settlements`

```sql
CREATE TYPE settlement_status AS ENUM ('pending', 'processing', 'completed', 'failed');

CREATE TABLE settlements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    batch_id        VARCHAR(64) NOT NULL,                   -- 结算批次号：幂等核心
    -- 结算金额
    amount          NUMERIC(20, 8) NOT NULL,
    currency        VARCHAR(10) NOT NULL DEFAULT 'CNY',
    fee_amount      NUMERIC(20, 8) NOT NULL DEFAULT 0,      -- 平台手续费
    net_amount      NUMERIC(20, 8) NOT NULL,                -- 实际到账 = amount - fee
    -- 状态
    status          settlement_status NOT NULL DEFAULT 'pending',
    settled_at      TIMESTAMPTZ,                            -- 实际结算时间
    transaction_ids UUID[] NOT NULL DEFAULT '{}',           -- 关联交易 IDs
    -- 幂等性
    idempotency_key VARCHAR(64) UNIQUE NOT NULL,
    -- 审计字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
    version         INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT chk_settlements_amount CHECK (amount >= 0),
    CONSTRAINT chk_settlements_net CHECK (net_amount >= 0)
);

CREATE INDEX idx_settlements_seller ON settlements(seller_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_settlements_batch ON settlements(batch_id) WHERE is_deleted = FALSE;
CREATE INDEX idx_settlements_status ON settlements(status) WHERE is_deleted = FALSE;
CREATE INDEX idx_settlements_idempotency ON settlements(idempotency_key);
```

---

### 4.3 幂等性设计规范（重点！）

前期表设计无法穷尽，**幂等性是防止数据混乱的核心防线**。以下从 5 个维度提供具体实现。

#### 4.3.1 接口幂等：所有修改操作必须携带 `idempotency_key`

服务端在 Redis 中维护 `idempotency_key` 到响应结果的映射，TTL 24 小时。

```python
# app/core/idempotency.py
import json
from datetime import timedelta
from typing import Optional, Dict, Any
from app.dependencies import get_redis

IDEMPOTENCY_TTL = 86400  # 24 小时


class IdempotencyStore:
    """幂等性存储：Redis 缓存请求结果，24h 内重复请求返回相同结果。"""

    @staticmethod
    def _key(idempotency_key: str) -> str:
        return f"idempotency:{idempotency_key}"

    async def get_result(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """获取已缓存的幂等结果。"""
        redis = await get_redis()
        cached = await redis.get(self._key(idempotency_key))
        if cached:
            return json.loads(cached)
        return None

    async def store_result(self, idempotency_key: str, result: Dict[str, Any]) -> None:
        """缓存幂等结果。"""
        redis = await get_redis()
        await redis.setex(
            self._key(idempotency_key),
            IDEMPOTENCY_TTL,
            json.dumps(result, default=str),
        )

    async def acquire_processing(self, idempotency_key: str) -> bool:
        """尝试获取处理锁：防止并发重复执行。"""
        redis = await get_redis()
        lock_key = f"idempotency_lock:{idempotency_key}"
        acquired = await redis.setnx(lock_key, "1")
        if acquired:
            await redis.expire(lock_key, 60)  # 锁 60 秒自动释放
        return acquired

    async def release_processing(self, idempotency_key: str) -> None:
        redis = await get_redis()
        await redis.delete(f"idempotency_lock:{idempotency_key}")
```

```python
# 使用示例：装饰器模式
from functools import wraps
from fastapi import HTTPException, Header
from app.core.idempotency import IdempotencyStore
from app.schemas.base import BaseResponse


def idempotent(handler):
    """幂等装饰器：用于 Service 层或 API 层。"""
    @wraps(handler)
    async def wrapper(*args, **kwargs):
        idempotency_key: Optional[str] = kwargs.get("idempotency_key")
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="缺少幂等键 Idempotency-Key")

        store = IdempotencyStore()

        # 1. 检查是否已处理过
        cached = await store.get_result(idempotency_key)
        if cached:
            return BaseResponse(**cached)

        # 2. 尝试获取处理锁
        if not await store.acquire_processing(idempotency_key):
            raise HTTPException(status_code=409, detail="请求正在处理中，请稍后重试")

        try:
            # 3. 执行业务逻辑
            result = await handler(*args, **kwargs)
            # 4. 缓存结果
            await store.store_result(idempotency_key, result.dict())
            return result
        finally:
            await store.release_processing(idempotency_key)
    return wrapper
```

```python
# API 层使用
@router.post("/purchase", response_model=BaseResponse[TransactionResponse])
@idempotent
async def create_purchase(
    req: PurchaseRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: TransactionService = Depends(get_transaction_service),
):
    """购买接口：必须携带 Idempotency-Key 请求头。"""
    result = await service.create_purchase(req, idempotency_key)
    return BaseResponse(data=result)
```

---

#### 4.3.2 数据库写入幂等：INSERT ON CONFLICT DO NOTHING / UPDATE

```python
# app/repositories/transaction_repository.py
from sqlalchemy import insert, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.transaction import Transaction as TransactionModel


class TransactionRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_with_idempotency(self, transaction_data: dict) -> TransactionModel:
        """
        幂等创建交易：相同 idempotency_key 重复插入时返回已有记录。
        """
        stmt = (
            pg_insert(TransactionModel)
            .values(**transaction_data)
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(TransactionModel)
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # ON CONFLICT DO NOTHING 不会返回已存在行，需手动查询
        stmt2 = select(TransactionModel).where(
            TransactionModel.idempotency_key == transaction_data["idempotency_key"]
        )
        result2 = await self._session.execute(stmt2)
        return result2.scalar_one()

    async def update_with_optimistic_lock(
        self, transaction_id: UUID, update_data: dict, expected_version: int
    ) -> bool:
        """
        乐观锁更新：WHERE version = expected_version，防止并发覆盖。
        """
        stmt = (
            update(TransactionModel)
            .where(
                TransactionModel.id == transaction_id,
                TransactionModel.version == expected_version,
                TransactionModel.is_deleted == False,
            )
            .values(**update_data, version=expected_version + 1)
        )
        result = await self._session.execute(stmt)
        return result.rowcount == 1
```

```sql
-- SQL 示例：INSERT ON CONFLICT
INSERT INTO transactions (id, buyer_id, seller_id, amount, idempotency_key, status, created_at)
VALUES (
    gen_random_uuid(),
    'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    100.00,
    'purchase_20240115_001',
    'pending',
    NOW()
)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING *;

-- SQL 示例：UPDATE 乐观锁
UPDATE balances
SET available = available - 100.00,
    frozen = frozen + 100.00,
    version = version + 1,
    updated_at = NOW()
WHERE user_id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
  AND currency = 'CNY'
  AND version = 5
  AND available >= 100.00;
-- 检查返回的 rowcount，若为 0 则并发冲突，需重试
```

---

#### 4.3.3 消息消费幂等：Kafka consumer 用消息 ID + 消费组去重

```python
# app/tasks/kafka_consumer.py
import json
from aiokafka import AIOKafkaConsumer
from app.dependencies import get_redis
from app.core.logging import get_logger

logger = get_logger(__name__)


class IdempotentKafkaConsumer:
    """
    幂等 Kafka Consumer：同一消息在同一消费组内只处理一次。
    使用 Redis SETNX 记录已消费的消息 ID。
    """

    def __init__(self, topic: str, group_id: str, bootstrap_servers: str):
        self.topic = topic
        self.group_id = group_id
        self.bootstrap_servers = bootstrap_servers
        self.consumer: Optional[AIOKafkaConsumer] = None

    async def start(self):
        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=False,  # 手动提交，确保处理完成后再提交
        )
        await self.consumer.start()

    async def consume(self, process_func):
        """消费循环：每条消息幂等处理。"""
        redis = await get_redis()
        async for msg in self.consumer:
            message_id = msg.value.get("message_id") or f"{msg.topic}-{msg.partition}-{msg.offset}"
            dedup_key = f"kafka_consumed:{self.group_id}:{message_id}"

            # 1. 检查是否已消费
            already_processed = await redis.get(dedup_key)
            if already_processed:
                logger.info(f"消息已消费，跳过: {message_id}")
                await self.consumer.commit()
                continue

            try:
                # 2. 业务处理
                await process_func(msg.value)

                # 3. 标记已消费（24h 过期）
                await redis.setex(dedup_key, 86400, "1")

                # 4. 提交 offset
                await self.consumer.commit()
            except Exception as e:
                logger.error(f"消息处理失败: {message_id}, error={e}")
                # 不提交 offset，消息会重新投递（根据 retry 策略）
                raise

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
```

---

#### 4.3.4 定时任务幂等：分布式锁（Redis RedLock）

```python
# app/tasks/scheduled_tasks.py
import asyncio
from datetime import timedelta
from typing import Optional
from app.dependencies import get_redis
from app.core.logging import get_logger

logger = get_logger(__name__)


class DistributedLock:
    """基于 Redis 的分布式锁（简化版 RedLock）。"""

    def __init__(self, lock_key: str, ttl_seconds: int = 60):
        self.lock_key = f"lock:{lock_key}"
        self.ttl = ttl_seconds
        self.identifier = f"{asyncio.current_task().get_name()}-{id(asyncio.current_task())}"

    async def acquire(self) -> bool:
        redis = await get_redis()
        acquired = await redis.set(self.lock_key, self.identifier, nx=True, ex=self.ttl)
        return acquired is not None

    async def release(self) -> None:
        redis = await get_redis()
        # 安全释放：只有持有锁的实例才能释放
        current = await redis.get(self.lock_key)
        if current == self.identifier:
            await redis.delete(self.lock_key)

    async def __aenter__(self):
        if not await self.acquire():
            raise RuntimeError(f"无法获取分布式锁: {self.lock_key}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


async def daily_settlement_task():
    """每日结算定时任务：分布式锁确保单实例执行。"""
    async with DistributedLock("daily_settlement", ttl_seconds=300):
        logger.info("开始执行每日结算任务...")
        # 执行结算逻辑...
        await asyncio.sleep(1)
        logger.info("每日结算任务完成")
```

---

#### 4.3.5 Escrow 结算幂等：结算批次号唯一，重复结算检测

```python
# app/services/escrow_service.py
from decimal import Decimal
from uuid import UUID
from app.core.idempotency import IdempotencyStore
from app.repositories.settlement_repository import SettlementRepository
from app.core.exceptions import BizException


class EscrowService:
    """Escrow 服务：确保结算操作绝对幂等。"""

    def __init__(self, settlement_repo: SettlementRepository):
        self._settlement_repo = settlement_repo

    async def release_escrow(self, batch_id: str, transaction_ids: list[UUID], seller_id: UUID) -> dict:
        """
        释放 Escrow 资金到卖家余额。
        核心幂等手段：
        1. batch_id 唯一索引 → 重复请求直接返回已有结果
        2.  settlements 表 idempotency_key 唯一约束
        3.  乐观锁版本号控制并发更新
        """
        # 1. 检查批次是否已存在
        existing = await self._settlement_repo.get_by_batch_id(batch_id)
        if existing:
            if existing.status == "completed":
                return {"status": "already_completed", "settlement_id": str(existing.id)}
            elif existing.status == "processing":
                raise BizException(code="SETTLEMENT_IN_PROGRESS", message="结算正在处理中")

        # 2. 计算结算金额
        total_amount = await self._calculate_settlement_amount(transaction_ids)
        fee = total_amount * Decimal("0.05")  # 5% 平台手续费
        net_amount = total_amount - fee

        idempotency_key = f"escrow_release:{batch_id}"

        # 3. 创建结算记录（INSERT ON CONFLICT 幂等）
        settlement = await self._settlement_repo.create_with_idempotency(
            {
                "seller_id": seller_id,
                "batch_id": batch_id,
                "amount": total_amount,
                "currency": "CNY",
                "fee_amount": fee,
                "net_amount": net_amount,
                "status": "processing",
                "transaction_ids": transaction_ids,
                "idempotency_key": idempotency_key,
            }
        )

        # 4. 更新卖家余额（乐观锁）
        success = await self._settlement_repo.update_seller_balance(
            seller_id=seller_id,
            amount=net_amount,
            settlement_id=settlement.id,
        )
        if not success:
            raise BizException(code="SETTLEMENT_CONFLICT", message="结算冲突，请重试")

        # 5. 更新结算状态为完成
        await self._settlement_repo.update_status(settlement.id, "completed")

        return {"status": "completed", "settlement_id": str(settlement.id), "net_amount": float(net_amount)}
```

```sql
-- Escrow 结算幂等 SQL 流程
-- 1. 幂等创建结算记录
INSERT INTO settlements (
    id, seller_id, batch_id, amount, currency, fee_amount, net_amount,
    status, transaction_ids, idempotency_key, created_at
)
VALUES (
    gen_random_uuid(),
    'seller-uuid',
    'batch_20240115_001',
    1000.00,
    'CNY',
    50.00,
    950.00,
    'processing',
    ARRAY['tx-uuid-1', 'tx-uuid-2'],
    'escrow_release:batch_20240115_001',
    NOW()
)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING *;

-- 2. 如果 ON CONFLICT DO NOTHING 没有返回，查询已有记录
SELECT * FROM settlements WHERE idempotency_key = 'escrow_release:batch_20240115_001';

-- 3. 更新卖家余额（乐观锁 + 原子操作）
UPDATE balances
SET available = available + 950.00,
    total = total + 950.00,
    version = version + 1,
    updated_at = NOW()
WHERE user_id = 'seller-uuid'
  AND currency = 'CNY'
  AND version = 5;
```

---

### 4.4 数据库写入规范

```python
# app/repositories/base.py
from typing import List, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, update, delete

T = TypeVar("T")


class BaseRepository:
    """Repository 基础类：所有写入必须通过 Repository 层，禁止 Service 直接执行 SQL。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    # -----------------------------------------------------------------------
    # 批量写入：使用 execute_many，避免 N+1
    # -----------------------------------------------------------------------
    async def bulk_insert(self, model_class, items: List[dict]) -> None:
        """批量插入：单条 SQL 执行，适用于 <= 1000 条记录。"""
        if not items:
            return
        if len(items) > 1000:
            raise ValueError("单批次写入不超过 1000 条，请拆分")
        stmt = insert(model_class).values(items)
        await self._session.execute(stmt)

    async def bulk_upsert(self, model_class, items: List[dict], index_elements: List[str]) -> None:
        """批量 UPSERT：插入或更新，避免重复处理。"""
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        if not items:
            return
        if len(items) > 1000:
            raise ValueError("单批次写入不超过 1000 条，请拆分")
        stmt = pg_insert(model_class).values(items)
        update_dict = {c.name: stmt.excluded[c.name] for c in model_class.__table__.columns if c.name not in index_elements}
        stmt = stmt.on_conflict_do_update(index_elements=index_elements, set_=update_dict)
        await self._session.execute(stmt)

    # -----------------------------------------------------------------------
    # 大事务拆分：单笔事务不超过 1000 条记录
    # -----------------------------------------------------------------------
    async def chunked_transaction(self, items: List[T], chunk_size: int = 1000, processor):
        """分块处理大数据集，每块一个独立事务。"""
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i + chunk_size]
            async with self._session.begin():
                await processor(chunk)

    # -----------------------------------------------------------------------
    # 乐观锁：版本号字段控制并发
    # -----------------------------------------------------------------------
    async def optimistic_update(self, model_class, entity_id, update_data: dict, expected_version: int) -> bool:
        """乐观锁更新：成功返回 True，冲突返回 False。"""
        stmt = (
            update(model_class)
            .where(
                model_class.id == entity_id,
                model_class.version == expected_version,
                model_class.is_deleted == False,
            )
            .values(**update_data, version=expected_version + 1)
        )
        result = await self._session.execute(stmt)
        return result.rowcount == 1
```

```python
# 使用示例：批量写入（如批量导入交易记录）
class TransactionRepository(BaseRepository):
    async def import_transactions(self, transactions: List[dict]) -> None:
        """批量导入：1000 条一批，避免大事务锁表。"""
        await self.chunked_transaction(
            transactions,
            chunk_size=1000,
            processor=lambda chunk: self.bulk_insert(TransactionModel, chunk),
        )
```

---

### 4.5 迁移管理（Alembic）

```python
# alembic.ini 配置节选
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

# 命名规范：{timestamp}_{description}.py
# 示例：alembic/versions/20240115_001_create_users_table.py
```

```python
# alembic/versions/20240115_001_create_users_table.py
"""create users table

Revision ID: 20240115_001
Revises: 
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20240115_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 ENUM 类型
    user_role = postgresql.ENUM('buyer', 'seller', 'admin', name='user_role')
    user_role.create(op.get_bind())

    user_status = postgresql.ENUM('active', 'suspended', 'deleted', name='user_status')
    user_status.create(op.get_bind())

    # 创建表
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('buyer', 'seller', 'admin', name='user_role'), nullable=False, server_default='buyer'),
        sa.Column('status', sa.Enum('active', 'suspended', 'deleted', name='user_status'), nullable=False, server_default='active'),
        sa.Column('nickname', sa.String(100), nullable=True),
        sa.Column('avatar_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.UniqueConstraint('email', 'is_deleted', name='uq_users_email_not_deleted'),
    )

    # 创建索引
    op.create_index('idx_users_phone', 'users', ['phone'], unique=False, postgresql_where=sa.text('is_deleted = false'))
    op.create_index('idx_users_role', 'users', ['role'], unique=False, postgresql_where=sa.text('is_deleted = false'))
    op.create_index('idx_users_created_at', 'users', ['created_at'], unique=False, postgresql_using='btree')


def downgrade() -> None:
    # 删除索引
    op.drop_index('idx_users_created_at', table_name='users')
    op.drop_index('idx_users_role', table_name='users')
    op.drop_index('idx_users_phone', table_name='users')

    # 删除表
    op.drop_table('users')

    # 删除 ENUM 类型
    user_role = postgresql.ENUM('buyer', 'seller', 'admin', name='user_role')
    user_role.drop(op.get_bind())
    user_status = postgresql.ENUM('active', 'suspended', 'deleted', name='user_status')
    user_status.drop(op.get_bind())
```

**迁移铁律：**

| 禁止操作 | 正确做法 |
|---|---|
| 删除列 | 先标记为废弃（`deprecated_at`），后续版本清理 |
| 修改列类型 | 新增列 → 双写数据 → 验证 → 删除旧列 |
| 删除表 | 重命名（`_deprecated`），保留至少一个版本 |
| 无 down 升级 | 每个迁移必须有 `upgrade` + `downgrade` |
| 手动改生产库 | 所有变更必须通过 Alembic 迁移文件执行 |

```python
# 列修改示例：不直接改类型，而是新增列 + 迁移
# 20240120_001_add_user_display_name.py

def upgrade() -> None:
    # 1. 新增列（新类型/新用途）
    op.add_column('users', sa.Column('display_name', sa.String(100), nullable=True))

    # 2. 数据迁移：从旧列到新列
    op.execute("UPDATE users SET display_name = nickname WHERE display_name IS NULL")

    # 3. 后续版本（非本次）删除旧列 nickname
    # op.drop_column('users', 'nickname')


def downgrade() -> None:
    # 回滚：删除新列（旧列仍在，业务逻辑兼容）
    op.drop_column('users', 'display_name')
```

---

## 5. 领域驱动设计（DDD）轻量实践

### 5.1 Entity：含业务方法的领域实体

```python
# app/domain/user.py
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from app.domain.money import Money


@dataclass
class User:
    """用户实体：包含业务规则，不依赖任何框架。"""

    id: UUID = field(default_factory=uuid4)
    email: str = ""
    phone: Optional[str] = None
    nickname: Optional[str] = None
    role: str = "buyer"  # buyer | seller | admin
    status: str = "active"  # active | suspended | deleted
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_deleted: bool = False

    def can_purchase(self, amount: Money) -> bool:
        """业务规则：被冻结/删除用户不能购买。"""
        if self.status != "active":
            return False
        if self.is_deleted:
            return False
        return True

    def upgrade_to_seller(self) -> "User":
        """业务规则：买家升级卖家。"""
        if self.role != "buyer":
            raise ValueError("只有买家可以升级卖家")
        self.role = "seller"
        return self

    def deactivate(self) -> "User":
        """业务规则：软删除。"""
        self.status = "deleted"
        self.is_deleted = True
        return self
```

### 5.2 Value Object：不可变值对象

```python
# app/domain/money.py
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Self


@dataclass(frozen=True)
class Money:
    """Money 值对象：不可变，所有运算返回新实例。"""

    amount: Decimal
    currency: str = "CNY"

    def __post_init__(self):
        # 确保金额精度
        object.__setattr__(
            self, "amount", self.amount.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        )

    def add(self, other: Self) -> Self:
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other: Self) -> Self:
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        if self.amount < other.amount:
            raise ValueError("Insufficient funds")
        return Money(self.amount - other.amount, self.currency)

    def multiply(self, factor: Decimal) -> Self:
        return Money(self.amount * factor, self.currency)

    def is_positive(self) -> bool:
        return self.amount > 0

    def __str__(self) -> str:
        return f"{self.currency} {self.amount}"
```

```python
# app/domain/usage.py
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class Usage:
    """AI 用量值对象：不可变。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: Self) -> Self:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )
```

```python
# app/domain/platform.py
from dataclasses import dataclass
from enum import Enum, auto


class PlatformType(Enum):
    """平台类型：枚举值对象。"""
    ZHIPU = "zhipu"
    VOLCANO = "volcano"
    MINIMAX = "minimax"
    KIMI = "kimi"
    CLAUDE = "claude"
    GPT = "gpt"


@dataclass(frozen=True)
class Platform:
    """平台值对象：标识 AI 平台，不可变。"""

    name: PlatformType
    display_name: str
    base_url: str

    def supports_model(self, model_name: str) -> bool:
        """业务规则：检查平台是否支持指定模型。"""
        # 实际逻辑根据平台文档维护
        supported = {
            PlatformType.ZHIPU: ["glm-4", "glm-3-turbo"],
            PlatformType.VOLCANO: ["doubao-pro", "doubao-lite"],
            PlatformType.CLAUDE: ["claude-3-opus", "claude-3-sonnet"],
        }
        return model_name in supported.get(self.name, [])
```

### 5.3 Aggregate：聚合根与一致性边界

```python
# app/domain/transaction_aggregate.py
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from typing import List
from decimal import Decimal
from app.domain.money import Money
from app.domain.usage import Usage
from app.domain.events import TransactionCompleted, DomainEvent


@dataclass
class BillingItem:
    """计费项：聚合内的实体，无独立生命周期。"""

    id: UUID = field(default_factory=uuid4)
    proxy_key_id: UUID = field(default_factory=uuid4)
    usage: Usage = field(default_factory=Usage)
    cost: Money = field(default_factory=lambda: Money(Decimal("0")))
    platform: str = ""
    model_name: str = ""


@dataclass
class TransactionAggregate:
    """
    交易聚合：以 transaction 为根，包含所有计费项。
    聚合内强一致性：transaction 和 billing_items 必须在同一事务中保存。
    """

    id: UUID = field(default_factory=uuid4)
    buyer_id: Optional[UUID] = None
    seller_id: UUID = field(default_factory=uuid4)
    listing_id: Optional[UUID] = None
    total_amount: Money = field(default_factory=lambda: Money(Decimal("0")))
    status: str = "pending"  # pending | completed | failed | reversed
    escrow_status: Optional[str] = None
    billing_items: List[BillingItem] = field(default_factory=list)
    _events: List[DomainEvent] = field(default_factory=list, repr=False)

    def add_billing_item(self, item: BillingItem) -> None:
        """添加计费项：仅允许 pending 状态。"""
        if self.status != "pending":
            raise ValueError("只能向 pending 状态的交易添加计费项")
        self.billing_items.append(item)
        self._recalculate_total()

    def _recalculate_total(self) -> None:
        """重新计算总金额：所有计费项之和。"""
        total = sum((item.cost for item in self.billing_items), Money(Decimal("0")))
        self.total_amount = total

    def complete(self) -> None:
        """完成交易：发布领域事件。"""
        if self.status != "pending":
            raise ValueError("只能完成 pending 状态的交易")
        self.status = "completed"
        self.escrow_status = "locked"
        self._events.append(
            TransactionCompleted(
                transaction_id=self.id,
                seller_id=self.seller_id,
                amount=self.total_amount,
            )
        )

    def release_escrow(self) -> None:
        """释放 Escrow：卖家资金到账。"""
        if self.status != "completed" or self.escrow_status != "locked":
            raise ValueError("交易未锁定或未完成")
        self.escrow_status = "released"

    def pop_events(self) -> List[DomainEvent]:
        """获取并清空领域事件：由外部事件发布器调用。"""
        events = self._events[:]
        self._events.clear()
        return events
```

### 5.4 Domain Event：通过 Kafka 异步发布

```python
# app/domain/events.py
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from typing import Optional
from abc import ABC


class DomainEvent(ABC):
    """领域事件基类。"""
    pass


@dataclass
class KeyListed(DomainEvent):
    """Key 挂售事件：卖家发布新挂售。"""

    listing_id: UUID
    seller_id: UUID
    platform: str
    model_name: str
    total_amount: float
    unit_price: float
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TransactionCompleted(DomainEvent):
    """交易完成事件：触发 Escrow 锁定、余额冻结。"""

    transaction_id: UUID
    seller_id: UUID
    buyer_id: Optional[UUID]
    amount: "Money"  # 使用字符串引用避免循环导入
    platform: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EscrowReleased(DomainEvent):
    """Escrow 释放事件：卖家资金到账。"""

    transaction_id: UUID
    seller_id: UUID
    amount: "Money"
    settlement_batch_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
```

```python
# app/core/event_publisher.py
import json
from typing import List
from aiokafka import AIOKafkaProducer
from app.domain.events import DomainEvent
from app.dependencies import get_kafka_producer
from app.core.logging import get_logger

logger = get_logger(__name__)


class KafkaEventPublisher:
    """领域事件发布器：将领域事件序列化后发布到 Kafka。"""

    async def publish(self, topic: str, events: List[DomainEvent]) -> None:
        if not events:
            return
        producer = await get_kafka_producer()
        for event in events:
            message = self._serialize(event)
            await producer.send(topic, value=message)
            logger.info(f"Published event to {topic}: {event.__class__.__name__}")

    def _serialize(self, event: DomainEvent) -> dict:
        """将领域事件序列化为 JSON 友好的字典。"""
        data = {}
        for key, value in event.__dict__.items():
            if isinstance(value, UUID):
                data[key] = str(value)
            elif hasattr(value, "amount") and hasattr(value, "currency"):
                # Money 值对象
                data[key] = {"amount": str(value.amount), "currency": value.currency}
            else:
                data[key] = value
        data["event_type"] = event.__class__.__name__
        return data
```

```python
# 使用示例：交易完成后发布事件
from app.core.event_publisher import KafkaEventPublisher
from app.repositories.transaction_repository import TransactionRepository


class TransactionService:
    def __init__(self, repo: TransactionRepository, event_publisher: KafkaEventPublisher):
        self._repo = repo
        self._publisher = event_publisher

    async def complete_transaction(self, transaction_id: UUID) -> None:
        # 1. 加载聚合
        aggregate = await self._repo.get_aggregate(transaction_id)

        # 2. 执行业务操作
        aggregate.complete()

        # 3. 保存聚合
        await self._repo.save_aggregate(aggregate)

        # 4. 发布领域事件
        events = aggregate.pop_events()
        await self._publisher.publish("domain_events", events)
```

---

## 6. 日志规范

### 6.1 统一格式

```
timestamp | level | request_id | service | message | context
```

```python
# app/core/logging.py
import sys
import json
import structlog
from datetime import datetime, timezone
from typing import Any, Dict


def get_logger(name: str = None):
    """获取结构化日志记录器。"""
    return structlog.get_logger(name)


def configure_logging():
    """配置 structlog：JSON 输出，统一字段。"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 标准库日志也使用 structlog 处理
    import logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
```

### 6.2 使用示例

```python
from app.core.logging import get_logger

logger = get_logger(__name__)

# 标准日志
logger.info("用户登录", user_id="uuid", ip="192.168.1.1")

# 输出（JSON）：
# {"timestamp": "2024-01-15T10:30:00.000Z", "level": "info", "logger": "app.services.user_service", "event": "用户登录", "user_id": "uuid", "ip": "192.168.1.1"}

# 错误日志
logger.error("交易失败", transaction_id="tx-uuid", error="余额不足", buyer_id="buyer-uuid")
```

### 6.3 敏感字段脱敏

```python
# app/core/sensitive_filter.py
import copy
import re
from typing import Any, Dict, Union

SENSITIVE_PATTERNS = [
    (re.compile(r"(api_key|secret|password|token|auth).*", re.I), "***"),
    (re.compile(r".*(身份证|id_card|ssn).*", re.I), "***"),
]

SENSITIVE_KEYS = {
    "api_key", "secret_key", "password", "token", "auth_token", "access_token",
    "refresh_token", "id_card", "ssn", "credit_card", "cvv",
}


def mask_sensitive(data: Union[Dict, list, Any]) -> Union[Dict, list, Any]:
    """递归脱敏：敏感字段替换为 ***。"""
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            if key in SENSITIVE_KEYS or any(p[0].match(key) for p in SENSITIVE_PATTERNS):
                masked[key] = "***"
            else:
                masked[key] = mask_sensitive(value)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive(item) for item in data]
    elif isinstance(data, str) and len(data) > 20:
        # 长字符串可能是密钥，脱敏首尾
        return data[:4] + "***" + data[-4:] if len(data) > 8 else "***"
    return data
```

```python
# 使用示例：在日志记录前脱敏
from app.core.sensitive_filter import mask_sensitive

log_data = {
    "user_id": "uuid",
    "api_key": "sk-abcdefghijklmnopqrstuvwxyz1234567890",
    "request": {"prompt": "Hello"},
}
logger.info("API 请求", **mask_sensitive(log_data))
# 输出：{"api_key": "***", "request": {"prompt": "Hello"}, "user_id": "uuid"}
```

---

## 7. 测试规范

### 7.1 测试框架配置

```python
# pyproject.toml 配置节选
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import app
from httpx import AsyncClient


@pytest_asyncio.fixture(scope="session")
async def postgres_container():
    """PostgreSQL 测试容器。"""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest_asyncio.fixture(scope="session")
async def redis_container():
    """Redis 测试容器。"""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest_asyncio.fixture
async def db_session(postgres_container):
    """每个测试用例独立的 DB Session。"""
    url = postgres_container.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg")
    engine = create_async_engine(url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    # 创建所有表
    from app.models.base import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session, redis_container):
    """HTTP 测试客户端。"""
    # 覆盖依赖注入
    from app.dependencies import get_db_session, get_redis

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        return Redis.from_url(redis_container.get_connection_url(), decode_responses=True)

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
```

### 7.2 单元测试：Mock Repository

```python
# tests/unit/test_user_service.py
import pytest
from uuid import uuid4
from app.services.user_service import UserService
from app.services.billing_service import BillingService
from tests.unit.mocks import MockUserRepository, MockBalanceRepository
from app.schemas.user import UserUpdateRequest
from app.domain.user import User
from app.core.exceptions import BizException


class TestUserService:
    """用户服务单元测试：Mock Repository，不依赖真实 DB。"""

    @pytest.fixture
    def user_repo(self):
        return MockUserRepository()

    @pytest.fixture
    def balance_repo(self):
        return MockBalanceRepository()

    @pytest.fixture
    def billing_service(self, balance_repo):
        return BillingService(balance_repo)

    @pytest.fixture
    def user_service(self, user_repo, billing_service):
        return UserService(user_repo, billing_service)

    @pytest.mark.asyncio
    async def test_update_user_profile(self, user_service, user_repo):
        """测试更新用户资料。"""
        user = User(id=uuid4(), email="test@example.com", nickname="Old")
        await user_repo.create(user)

        req = UserUpdateRequest(nickname="New")
        result = await user_service.update_user_profile(user.id, req)

        assert result.nickname == "New"

    @pytest.mark.asyncio
    async def test_check_purchase_eligibility_sufficient_balance(self, user_service, balance_repo):
        """测试余额充足时可以购买。"""
        user_id = uuid4()
        await balance_repo.create_with_balance(user_id, "CNY", 1000.00)

        eligible = await user_service.check_purchase_eligibility(user_id, 500.00)
        assert eligible is True

    @pytest.mark.asyncio
    async def test_check_purchase_eligibility_insufficient_balance(self, user_service, balance_repo):
        """测试余额不足时不能购买。"""
        user_id = uuid4()
        await balance_repo.create_with_balance(user_id, "CNY", 100.00)

        eligible = await user_service.check_purchase_eligibility(user_id, 500.00)
        assert eligible is False

    @pytest.mark.asyncio
    async def test_update_nonexistent_user(self, user_service):
        """测试更新不存在的用户应抛出异常。"""
        req = UserUpdateRequest(nickname="New")
        with pytest.raises(BizException) as exc_info:
            await user_service.update_user_profile(uuid4(), req)
        assert exc_info.value.code == "USER_NOT_FOUND"
```

### 7.3 集成测试：使用 testcontainers

```python
# tests/integration/test_user_api.py
import pytest
from uuid import uuid4


class TestUserAPI:
    """用户接口集成测试：真实 DB + Redis + FastAPI。"""

    @pytest.mark.asyncio
    async def test_create_user(self, client):
        """测试创建用户。"""
        response = await client.post("/api/v1/users/", json={
            "email": "test@example.com",
            "password": "Secure123!",
            "nickname": "TestUser",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["code"] == "0"
        assert data["data"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_duplicate_user(self, client):
        """测试重复邮箱应返回错误。"""
        payload = {
            "email": "dup@example.com",
            "password": "Secure123!",
        }
        # 第一次创建
        r1 = await client.post("/api/v1/users/", json=payload)
        assert r1.status_code == 201

        # 重复创建
        r2 = await client.post("/api/v1/users/", json=payload)
        assert r2.status_code == 409
        assert r2.json()["code"] == "USER_EMAIL_EXISTS"

    @pytest.mark.asyncio
    async def test_purchase_idempotency(self, client):
        """测试购买接口幂等性：相同 Idempotency-Key 应返回相同结果。"""
        idempotency_key = "test_key_001"
        payload = {
            "listing_id": str(uuid4()),
            "quantity": 100.0,
        }

        r1 = await client.post(
            "/api/v1/transactions/purchase",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            "/api/v1/transactions/purchase",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert r2.status_code == 200
        # 两次返回的数据应一致（幂等）
        assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
```

### 7.4 工厂模式：factory_boy 生成测试数据

```python
# tests/factories.py
import factory
from uuid import uuid4
from app.models.user import User as UserModel
from app.models.transaction import Transaction as TransactionModel
from decimal import Decimal


class UserFactory(factory.Factory):
    """用户工厂：快速生成测试用户。"""

    class Meta:
        model = UserModel

    id = factory.LazyFunction(uuid4)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    phone = factory.Sequence(lambda n: f"1380000{n:04d}")
    password_hash = "hashed_password"
    role = "buyer"
    status = "active"
    nickname = factory.Faker("name")
    created_at = factory.Faker("date_time")
    updated_at = factory.Faker("date_time")
    is_deleted = False
    version = 1


class TransactionFactory(factory.Factory):
    """交易工厂：快速生成测试交易。"""

    class Meta:
        model = TransactionModel

    id = factory.LazyFunction(uuid4)
    buyer_id = factory.LazyFunction(uuid4)
    seller_id = factory.LazyFunction(uuid4)
    listing_id = factory.LazyFunction(uuid4)
    type = "purchase"
    status = "pending"
    amount = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    currency = "CNY"
    quantity = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    platform = factory.Iterator(["zhipu", "volcano", "claude", "gpt"])
    model_name = factory.Iterator(["glm-4", "doubao-pro", "claude-3-opus", "gpt-4"])
    idempotency_key = factory.Sequence(lambda n: f"idempotency_{n}")
    escrow_status = None
    created_at = factory.Faker("date_time")
    updated_at = factory.Faker("date_time")
    is_deleted = False
    version = 1
```

```python
# 使用示例
@pytest.mark.asyncio
async def test_list_transactions(self, db_session):
    from tests.factories import TransactionFactory

    # 创建 10 条测试交易
    transactions = TransactionFactory.build_batch(10)
    db_session.add_all(transactions)
    await db_session.commit()

    # 测试查询
    result = await transaction_repo.list_all(limit=5, offset=0)
    assert len(result) == 5
```

---

## 附录：快速检查清单

| 检查项 | 状态 |
|---|---|
| [ ] 所有表有 `id`, `created_at`, `updated_at`, `is_deleted`, `version` | |
| [ ] 所有外键有索引 | |
| [ ] 枚举使用 PostgreSQL ENUM 或整型常量 | |
| [ ] 所有修改接口携带 `Idempotency-Key` | |
| [ ] Redis 缓存 `idempotency_key` 结果（TTL 24h） | |
| [ ] 数据库写入使用 `INSERT ON CONFLICT` 或 `UPDATE ... WHERE version = ?` | |
| [ ] Kafka consumer 用 `SETNX` 去重 | |
| [ ] 定时任务用分布式锁（Redis） | |
| [ ] Escrow 结算有 `batch_id` 唯一约束 | |
| [ ] 批量写入 <= 1000 条/事务 | |
| [ ] 敏感字段日志脱敏 | |
| [ ] Service 层不直接执行 SQL | |
| [ ] Repository 依赖接口而非实现 | |
| [ ] Alembic 迁移有 `upgrade` + `downgrade` | |
| [ ] 单元测试使用 Mock Repository | |
| [ ] 集成测试使用 testcontainers | |

---

> 本文档由 TokenMarket 架构组维护，遵循 "快速迭代，严格底线" 原则。
> V0.1-0.2 阶段允许适度灵活，但幂等性、软删除、接口契约三项为绝对红线。
