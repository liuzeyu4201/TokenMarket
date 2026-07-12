# TokenMarket Go 代理网关开发规范

> 版本：V0.1
> 状态：快速原型验证阶段
> 目标：建立可迭代、强兼容的 Clean Architecture 代码基线

---

## 目录

1. [Go 项目目录结构](#1-go-项目目录结构)
2. [SOLID 原则在 Go 中的具体实践](#2-solid-原则在-go-中的具体实践)
3. [代理网关核心设计](#3-代理网关核心设计)
4. [API 设计规范](#4-api-设计规范)
5. [错误处理规范](#5-错误处理规范)
6. [并发编程规范](#6-并发编程规范)
7. [测试规范](#7-测试规范)
8. [关键代码示例](#8-关键代码示例)

---

## 1. Go 项目目录结构

按 **Clean Architecture / 端口适配器模式** 设计，严格遵循依赖方向：**Domain → Application → Interfaces → Infrastructure**。

```
proxy-gateway/
├── cmd/
│   └── server/
│       └── main.go              # 入口：仅负责初始化与依赖注入
├── internal/
│   ├── domain/                  # 领域层：纯 struct + interface，零外部依赖
│   │   ├── models.go            # 核心领域模型（ProxyRequest, ProxyResponse, UsageInfo 等）
│   │   ├── errors.go            # 领域错误定义
│   │   ├── platform.go          # PlatformAdapter 接口定义
│   │   ├── router.go            # RouteStrategy 接口定义
│   │   ├── key.go               # KeyInfo, KeyPool 领域模型
│   │   └── metering.go          # 计量领域模型
│   ├── application/             # 应用层：用例编排、事务边界
│   │   ├── proxy_service.go     # 核心代理用例
│   │   ├── key_service.go       # Key 管理用例
│   │   ├── routing_service.go    # 路由编排用例
│   │   └── metering_service.go   # 计量上报用例
│   ├── infrastructure/          # 基础设施层：具体技术实现
│   │   ├── http/
│   │   │   ├── client.go         # 通用 HTTP client（带超时、重试）
│   │   │   └── middleware.go     # 基础设施级中间件（日志、追踪）
│   │   ├── redis/
│   │   │   └── client.go         # Redis 连接与封装
│   │   ├── kafka/
│   │   │   └── producer.go       # Kafka 生产者（异步计量事件）
│   │   ├── platform/            # 各平台适配器具体实现
│   │   │   ├── volcano_adapter.go
│   │   │   ├── zhipu_adapter.go
│   │   │   ├── minimax_adapter.go
│   │   │   ├── kimi_adapter.go
│   │   │   ├── claude_adapter.go
│   │   │   └── gpt_adapter.go
│   │   └── repository/          # 仓储实现（如有持久化需求）
│   │       └── key_repository.go
│   ├── interfaces/              # 接口适配层：HTTP handlers、middleware
│   │   ├── http/
│   │   │   ├── server.go         # HTTP 服务器初始化（gin/echo）
│   │   │   ├── router.go         # 路由注册
│   │   │   ├── handlers/
│   │   │   │   ├── proxy_handler.go
│   │   │   │   └── admin_handler.go
│   │   │   └── middleware/
│   │   │       ├── auth.go         # L1/L2 Key 认证
│   │   │       ├── rate_limit.go   # 速率限制
│   │   │       ├── recovery.go     # Panic 恢复
│   │   │       ├── request_id.go   # 请求 ID 注入
│   │   │       └── metering.go     # 计量中间件
│   │   └── dto/                 # 请求/响应 DTO（仅本层使用）
│   │       ├── proxy_dto.go
│   │       └── admin_dto.go
│   └── config/                  # 配置管理
│       ├── config.go            # 配置结构体定义
│       └── loader.go            # 配置文件加载（viper）
├── pkg/                         # 可复用公共包（可被外部项目导入）
│   ├── router/                  # 智能路由引擎（独立包）
│   │   ├── strategy.go           # 路由策略接口与实现
│   │   ├── pool.go               # KeyPool 管理器
│   │   ├── health.go             # 健康检查器
│   │   └── affinity.go           # 会话亲和性
│   ├── meter/                   # Token 计量器
│   │   ├── counter.go            # Token 计数器
│   │   ├── parser.go             # 响应解析器
│   │   └── aggregator.go         # 用量聚合器
│   ├── keymgr/                  # Key 管理工具
│   │   ├── encrypt.go            # 加密工具
│   │   ├── mapper.go             # Key 映射器
│   │   └── validator.go          # Key 格式校验器
│   └── platform/                # 平台抽象与通用工具
│       ├── adapter.go            # PlatformAdapter 接口
│       ├── registry.go           # 适配器注册中心
│       └── transformer.go        # 请求/响应转换器
├── tests/                       # 集成测试
│   ├── integration/
│   │   ├── proxy_flow_test.go
│   │   ├── routing_test.go
│   │   └── platform_adapter_test.go
│   ├── benchmark/
│   │   └── router_benchmark_test.go
│   └── fixtures/
│       └── mock_responses/
├── scripts/                     # 开发脚本
│   ├── build.sh
│   └── test.sh
├── configs/
│   └── config.yaml
├── go.mod
├── go.sum
├── Makefile
└── README.md
```

### 依赖规则

| 层 | 可依赖 | 禁止依赖 |
|---|---|---|
| `domain` | 标准库 | 任何外部包、其他 internal 包 |
| `application` | `domain` | `infrastructure`, `interfaces` |
| `infrastructure` | `domain`, `pkg/*` | `interfaces`, `application`（除DI外） |
| `interfaces` | `domain`, `application`, `pkg/*` | `infrastructure`（除DI外） |
| `pkg/*` | `domain`, 标准库 | `application`, `interfaces`, `infrastructure` |

### 模块边界检查

使用 `golangci-lint` + `depguard` 规则强制依赖方向：

```yaml
# .golangci.yml
linters:
  enable:
    - depguard
linters-settings:
  depguard:
    rules:
      domain:
        files: ["$all"]
        deny:
          - pkg: "github.com/redis/go-redis"
            desc: "domain 层禁止依赖 Redis"
          - pkg: "github.com/segmentio/kafka-go"
            desc: "domain 层禁止依赖 Kafka"
      application:
        files: ["internal/application/**/*.go"]
        deny:
          - pkg: "github.com/gin-gonic/gin"
            desc: "application 层禁止依赖 Web 框架"
```

---

## 2. SOLID 原则在 Go 中的具体实践

### S — 单一职责原则（Single Responsibility）

**原则**：每个类型、函数、模块只负责一件事。

**实践**：

```go
// ❌ 错误：一个 handler 处理多种请求
func (h *Handler) Handle(w http.ResponseWriter, r *http.Request) {
    switch r.URL.Path {
    case "/proxy":  // 处理代理
    case "/admin":  // 处理管理
    case "/health": // 处理健康检查
    }
}

// ✅ 正确：每个 handler 只处理一种请求
type ProxyHandler struct { proxySvc ProxyService }
func (h *ProxyHandler) ChatCompletions(c *gin.Context) { ... }
func (h *ProxyHandler) Embeddings(c *gin.Context)       { ... }

type AdminHandler struct { keySvc KeyService }
func (h *AdminHandler) ListKeys(c *gin.Context)   { ... }
func (h *AdminHandler) RefreshKeys(c *gin.Context) { ... }

type HealthHandler struct { checker HealthChecker }
func (h *HealthHandler) Check(c *gin.Context) { ... }
```

**服务层拆分**：

```go
// 每个 service 只负责一个业务用例
type ProxyService interface {
    ExecuteProxy(ctx context.Context, req *ProxyRequest) (*ProxyResponse, error)
}

type KeyManagementService interface {
    ValidateKey(ctx context.Context, key string) (*KeyInfo, error)
    RefreshKeyPool(ctx context.Context, platform string) error
}

type RoutingService interface {
    SelectKey(ctx context.Context, strategy RouteStrategy, req *ProxyRequest) (*KeyInfo, error)
}

type MeteringService interface {
    RecordUsage(ctx context.Context, usage *UsageInfo) error
    FlushAsync(ctx context.Context) error
}
```

---

### O — 开闭原则（Open/Closed）

**原则**：对扩展开放，对修改关闭。

**实践**：新增平台只需实现 `PlatformAdapter` 接口，无需修改路由核心逻辑。

```go
// 注册中心：新平台只需 Register，无需修改任何现有代码
type AdapterRegistry struct {
    adapters map[string]domain.PlatformAdapter
}

func (r *AdapterRegistry) Register(name string, adapter domain.PlatformAdapter) {
    r.adapters[name] = adapter
}

func (r *AdapterRegistry) Get(name string) (domain.PlatformAdapter, error) {
    adapter, ok := r.adapters[name]
    if !ok {
        return nil, fmt.Errorf("platform %s not registered", name)
    }
    return adapter, nil
}

// 初始化时注册（main.go 中）
registry := platform.NewRegistry()
registry.Register("volcano", infrastructure.NewVolcanoAdapter(cfg.Volcano))
registry.Register("zhipu", infrastructure.NewZhipuAdapter(cfg.Zhipu))
registry.Register("minimax", infrastructure.NewMiniMaxAdapter(cfg.MiniMax))
registry.Register("kimi", infrastructure.NewKimiAdapter(cfg.Kimi))
registry.Register("claude", infrastructure.NewClaudeAdapter(cfg.Claude))
registry.Register("gpt", infrastructure.NewGPTAdapter(cfg.GPT))
// 新增平台：只需加一行 Register，零修改已有代码
```

---

### L — 里氏替换原则（Liskov Substitution）

**原则**：所有平台适配器可互换使用，调用方无需关心具体类型。

**实践**：

```go
// 领域层定义接口
type PlatformAdapter interface {
    Name() string
    ValidateKey(ctx context.Context, key string) (*KeyInfo, error)
    Forward(ctx context.Context, req *ProxyRequest, key string) (*ProxyResponse, error)
    ParseUsage(resp *ProxyResponse) (*UsageInfo, error)
    TransformRequest(req *ProxyRequest) ([]byte, error)
    TransformResponse(body []byte, statusCode int) (*ProxyResponse, error)
}

// 所有实现可互换使用
func (s *ProxyService) ExecuteProxy(ctx context.Context, req *ProxyRequest) (*ProxyResponse, error) {
    adapter, err := s.registry.Get(req.Platform)
    if err != nil {
        return nil, err
    }

    // 以下代码对任何平台适配器都适用，无需类型断言
    keyInfo, err := adapter.ValidateKey(ctx, req.Key)
    if err != nil {
        return nil, err
    }

    resp, err := adapter.Forward(ctx, req, keyInfo.OriginalKey)
    if err != nil {
        return nil, err
    }

    usage, err := adapter.ParseUsage(resp)
    if err != nil {
        return nil, err
    }

    s.metering.RecordUsage(ctx, usage)
    return resp, nil
}
```

**单元测试验证 LSP**：

```go
func TestAllAdaptersImplementInterface(t *testing.T) {
    var _ domain.PlatformAdapter = (*VolcanoAdapter)(nil)
    var _ domain.PlatformAdapter = (*ZhipuAdapter)(nil)
    var _ domain.PlatformAdapter = (*MiniMaxAdapter)(nil)
    var _ domain.PlatformAdapter = (*KimiAdapter)(nil)
    var _ domain.PlatformAdapter = (*ClaudeAdapter)(nil)
    var _ domain.PlatformAdapter = (*GPTAdapter)(nil)
}
```

---

### I — 接口隔离原则（Interface Segregation）

**原则**：将大接口拆分为小接口，调用方只依赖所需方法。

**实践**：

```go
// ❌ 错误：大接口，调用方被迫依赖不需要的方法
type BigAdapter interface {
    Name() string
    ValidateKey(ctx context.Context, key string) (*KeyInfo, error)
    Forward(ctx context.Context, req *ProxyRequest, key string) (*ProxyResponse, error)
    ParseUsage(resp *ProxyResponse) (*UsageInfo, error)
    TransformRequest(req *ProxyRequest) ([]byte, error)
    TransformResponse(body []byte, statusCode int) (*ProxyResponse, error)
    StreamForward(ctx context.Context, req *ProxyRequest, key string) (chan StreamChunk, error)
    ParseStreamChunk(chunk []byte) (*StreamChunk, error)
    GetModelList(ctx context.Context) ([]string, error)
    GetBalance(ctx context.Context, key string) (*BalanceInfo, error)
    HealthCheck(ctx context.Context, key string) error
}

// ✅ 正确：拆分为小接口
type KeyValidator interface {
    ValidateKey(ctx context.Context, key string) (*KeyInfo, error)
}

type RequestForwarder interface {
    Forward(ctx context.Context, req *ProxyRequest, key string) (*ProxyResponse, error)
    StreamForward(ctx context.Context, req *ProxyRequest, key string) (chan StreamChunk, error)
}

type UsageParser interface {
    ParseUsage(resp *ProxyResponse) (*UsageInfo, error)
    ParseStreamChunk(chunk []byte) (*StreamChunk, error)
}

type RequestTransformer interface {
    TransformRequest(req *ProxyRequest) ([]byte, error)
    TransformResponse(body []byte, statusCode int) (*ProxyResponse, error)
}

type HealthChecker interface {
    HealthCheck(ctx context.Context, key string) error
}

// 组合小接口形成完整适配器
type PlatformAdapter interface {
    KeyValidator
    RequestForwarder
    UsageParser
    RequestTransformer
    HealthChecker
    Name() string
}

// 路由服务只依赖 Forwarder，不需要 Transformer
func (s *RoutingService) Route(ctx context.Context, forwarder RequestForwarder, req *ProxyRequest) (*ProxyResponse, error) {
    return forwarder.Forward(ctx, req, req.Key)
}

// 健康检查服务只依赖 HealthChecker
func (s *HealthService) Check(ctx context.Context, checker HealthChecker, key string) error {
    return checker.HealthCheck(ctx, key)
}
```

---

### D — 依赖倒置原则（Dependency Inversion）

**原则**：高层模块定义接口，低层模块实现接口。

**实践**：领域层定义接口，基础设施层实现接口，应用层通过接口注入依赖。

```go
// internal/domain/platform.go — 领域层定义接口（高层）
package domain

type PlatformAdapter interface {
    Name() string
    ValidateKey(ctx context.Context, key string) (*KeyInfo, error)
    Forward(ctx context.Context, req *ProxyRequest, key string) (*ProxyResponse, error)
    ParseUsage(resp *ProxyResponse) (*UsageInfo, error)
    TransformRequest(req *ProxyRequest) ([]byte, error)
    TransformResponse(body []byte, statusCode int) (*ProxyResponse, error)
}

type RouteStrategy interface {
    Select(ctx context.Context, keys []KeyInfo, req *ProxyRequest) (*KeyInfo, error)
}

type KeyPool interface {
    GetAvailableKeys(platform string) []KeyInfo
    Refresh(platform string) error
}

type MeteringPublisher interface {
    Publish(ctx context.Context, event *UsageEvent) error
}

// internal/application/proxy_service.go — 应用层依赖接口（高层）
package application

type ProxyService struct {
    registry  domain.AdapterRegistry      // 接口
    router    domain.Router               // 接口
    strategy  domain.RouteStrategy        // 接口
    publisher domain.MeteringPublisher    // 接口
    cache     domain.UsageCache           // 接口
}

func NewProxyService(
    registry domain.AdapterRegistry,
    router domain.Router,
    strategy domain.RouteStrategy,
    publisher domain.MeteringPublisher,
    cache domain.UsageCache,
) *ProxyService {
    return &ProxyService{
        registry:  registry,
        router:    router,
        strategy:  strategy,
        publisher: publisher,
        cache:     cache,
    }
}

// internal/infrastructure/platform/volcano_adapter.go — 基础设施层实现（低层）
package platform

type VolcanoAdapter struct {
    baseURL    string
    httpClient *http.Client
    timeout    time.Duration
}

func NewVolcanoAdapter(cfg config.VolcanoConfig) *VolcanoAdapter {
    return &VolcanoAdapter{
        baseURL: cfg.BaseURL,
        httpClient: &http.Client{
            Timeout: cfg.Timeout,
        },
        timeout: cfg.Timeout,
    }
}

func (a *VolcanoAdapter) Name() string { return "volcano" }

func (a *VolcanoAdapter) ValidateKey(ctx context.Context, key string) (*domain.KeyInfo, error) {
    // 具体实现...
}

func (a *VolcanoAdapter) Forward(ctx context.Context, req *domain.ProxyRequest, key string) (*domain.ProxyResponse, error) {
    // 具体实现...
}

func (a *VolcanoAdapter) ParseUsage(resp *domain.ProxyResponse) (*domain.UsageInfo, error) {
    // 具体实现...
}

func (a *VolcanoAdapter) TransformRequest(req *domain.ProxyRequest) ([]byte, error) {
    // 火山方舟请求格式转换...
}

func (a *VolcanoAdapter) TransformResponse(body []byte, statusCode int) (*domain.ProxyResponse, error) {
    // 火山方舟响应格式转换...
}

// cmd/server/main.go — 依赖注入（唯一知道所有具体类型的位置）
func main() {
    cfg := config.Load("config.yaml")

    // 基础设施层实例化
    redisClient := redis.NewClient(cfg.Redis)
    kafkaProducer := kafka.NewProducer(cfg.Kafka)
    httpClient := &http.Client{Timeout: 30 * time.Second}

    // 适配器实例化
    volcanoAdapter := platform.NewVolcanoAdapter(cfg.Volcano)
    zhipuAdapter := platform.NewZhipuAdapter(cfg.Zhipu)
    // ... 其他适配器

    // 注册中心
    registry := pkgplatform.NewRegistry()
    registry.Register("volcano", volcanoAdapter)
    registry.Register("zhipu", zhipuAdapter)
    // ...

    // 路由策略
    strategy := router.NewWeightedRoundRobinStrategy()

    // 应用层服务（注入接口）
    proxySvc := application.NewProxyService(
        registry,
        router.NewEngine(redisClient),
        strategy,
        kafkaProducer,
        redisClient,
    )

    // 接口层
    proxyHandler := http.NewProxyHandler(proxySvc)
    adminHandler := http.NewAdminHandler(keySvc)

    // 启动服务器
    server := http.NewServer(cfg.Server, proxyHandler, adminHandler)
    server.Start()
}
```

---

## 3. 代理网关核心设计

### 3.1 请求处理流水线（Pipeline Pattern）

```
Request → Auth → RateLimit → Routing → Transform → Forward → Metering → Response
```

每个阶段是一个可插拔的 middleware/handler，满足开闭原则。

**接口定义**：

```go
// internal/domain/pipeline.go
package domain

// PipelineStage 流水线阶段接口
type PipelineStage interface {
    Name() string
    Execute(ctx context.Context, req *ProxyRequest, state *PipelineState) error
}

// PipelineState 流水线共享状态
type PipelineState struct {
    RequestID      string
    ProxyKey       string          // L2 代理 Key
    OriginalKey    string          // L1 原始平台 Key
    Platform       string
    Strategy       RouteStrategy
    Adapter        PlatformAdapter
    TargetURL      string
    TransformedReq []byte
    Response       *ProxyResponse
    Usage          *UsageInfo
    Errors         []error
    StartedAt      time.Time
    Metadata       map[string]any
}

// Pipeline 执行器
type Pipeline struct {
    stages []PipelineStage
}

func (p *Pipeline) Execute(ctx context.Context, req *ProxyRequest) (*ProxyResponse, error) {
    state := &PipelineState{
        RequestID: generateRequestID(),
        StartedAt: time.Now(),
        Metadata:  make(map[string]any),
    }

    for _, stage := range p.stages {
        if err := stage.Execute(ctx, req, state); err != nil {
            return nil, fmt.Errorf("stage %s failed: %w", stage.Name(), err)
        }
    }

    return state.Response, nil
}
```

**各阶段实现**：

```go
// interfaces/http/middleware/auth.go
package middleware

type AuthStage struct {
    keySvc application.KeyService
}

func (s *AuthStage) Name() string { return "auth" }

func (s *AuthStage) Execute(ctx context.Context, req *domain.ProxyRequest, state *domain.PipelineState) error {
    keyInfo, err := s.keySvc.ValidateKey(ctx, req.ProxyKey)
    if err != nil {
        return domain.NewAuthError("invalid proxy key", err)
    }
    state.OriginalKey = keyInfo.OriginalKey
    state.Platform = keyInfo.Platform
    return nil
}

// interfaces/http/middleware/rate_limit.go
package middleware

type RateLimitStage struct {
    limiter RateLimiter
}

func (s *RateLimitStage) Name() string { return "rate_limit" }

func (s *RateLimitStage) Execute(ctx context.Context, req *domain.ProxyRequest, state *domain.PipelineState) error {
    allowed, err := s.limiter.Allow(ctx, req.ProxyKey, req.RateLimitKey)
    if err != nil {
        return domain.NewSystemError("rate limit check failed", err)
    }
    if !allowed {
        return domain.NewRateLimitError("rate limit exceeded")
    }
    return nil
}

// interfaces/http/middleware/routing.go
package middleware

type RoutingStage struct {
    registry domain.AdapterRegistry
    router   domain.Router
    strategy domain.RouteStrategy
}

func (s *RoutingStage) Name() string { return "routing" }

func (s *RoutingStage) Execute(ctx context.Context, req *domain.ProxyRequest, state *domain.PipelineState) error {
    adapter, err := s.registry.Get(state.Platform)
    if err != nil {
        return domain.NewRoutingError("platform not found", err)
    }
    state.Adapter = adapter

    keys, err := s.router.GetAvailableKeys(ctx, state.Platform)
    if err != nil {
        return domain.NewRoutingError("failed to get keys", err)
    }

    selected, err := s.strategy.Select(ctx, keys, req)
    if err != nil {
        return domain.NewRoutingError("route selection failed", err)
    }
    state.OriginalKey = selected.OriginalKey
    return nil
}

// interfaces/http/middleware/transform.go
package middleware

type TransformStage struct{}

func (s *TransformStage) Name() string { return "transform" }

func (s *TransformStage) Execute(ctx context.Context, req *domain.ProxyRequest, state *domain.PipelineState) error {
    body, err := state.Adapter.TransformRequest(req)
    if err != nil {
        return domain.NewPlatformError("transform request failed", err)
    }
    state.TransformedReq = body
    return nil
}

// interfaces/http/middleware/forward.go
package middleware

type ForwardStage struct {
    httpClient *http.Client
}

func (s *ForwardStage) Name() string { return "forward" }

func (s *ForwardStage) Execute(ctx context.Context, req *domain.ProxyRequest, state *domain.PipelineState) error {
    resp, err := state.Adapter.Forward(ctx, req, state.OriginalKey)
    if err != nil {
        return domain.NewPlatformError("forward failed", err)
    }
    state.Response = resp
    return nil
}

// interfaces/http/middleware/metering.go
package middleware

type MeteringStage struct {
    publisher domain.MeteringPublisher
    cache     domain.UsageCache
}

func (s *MeteringStage) Name() string { return "metering" }

func (s *MeteringStage) Execute(ctx context.Context, req *domain.ProxyRequest, state *domain.PipelineState) error {
    usage, err := state.Adapter.ParseUsage(state.Response)
    if err != nil {
        return domain.NewBillingError("parse usage failed", err)
    }
    state.Usage = usage

    // 异步发送 Kafka
    event := &domain.UsageEvent{
        RequestID:   state.RequestID,
        ProxyKey:    req.ProxyKey,
        Platform:    state.Platform,
        Model:       req.Model,
        PromptTokens:   usage.PromptTokens,
        CompletionTokens: usage.CompletionTokens,
        TotalTokens:    usage.TotalTokens,
        Timestamp: time.Now(),
    }

    go func() {
        // 带 recover 的 goroutine
        defer func() {
            if r := recover(); r != nil {
                log.Printf("metering panic recovered: %v", r)
            }
        }()

        ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
        defer cancel()

        if err := s.publisher.Publish(ctx, event); err != nil {
            log.Printf("metering publish failed: %v", err)
        }
    }()

    // 更新 Redis 实时缓存
    if err := s.cache.Increment(ctx, req.ProxyKey, usage.TotalTokens); err != nil {
        log.Printf("cache update failed: %v", err)
    }

    return nil
}

// interfaces/http/middleware/response.go
package middleware

type ResponseStage struct{}

func (s *ResponseStage) Name() string { return "response" }

func (s *ResponseStage) Execute(ctx context.Context, req *domain.ProxyRequest, state *domain.PipelineState) error {
    // 响应头注入
    state.Response.Headers = map[string]string{
        "X-Request-ID":      state.RequestID,
        "X-Remaining-Balance": fmt.Sprintf("%.4f", state.Usage.RemainingBalance),
    }
    return nil
}
```

---

### 3.2 智能路由引擎设计

#### 3.2.1 RouteStrategy 接口

```go
// pkg/router/strategy.go
package router

import (
    "context"
    "sync"
    "time"

    "tokenmarket/proxy-gateway/internal/domain"
)

// RouteStrategy 路由策略接口
type RouteStrategy interface {
    Name() string
    Select(ctx context.Context, keys []domain.KeyInfo, req *domain.ProxyRequest) (*domain.KeyInfo, error)
}

// 1. 加权轮询策略（Weighted Round Robin）
type WeightedRoundRobin struct {
    weights map[string]int // keyID -> weight
    current map[string]int // keyID -> current counter
    mu      sync.RWMutex
}

func (w *WeightedRoundRobin) Select(ctx context.Context, keys []domain.KeyInfo, req *domain.ProxyRequest) (*domain.KeyInfo, error) {
    w.mu.Lock()
    defer w.mu.Unlock()

    var selected *domain.KeyInfo
    maxWeight := -1

    for i := range keys {
        key := &keys[i]
        weight := w.weights[key.ID]
        if weight == 0 {
            weight = 1 // 默认权重
        }
        w.current[key.ID] += weight

        if w.current[key.ID] > maxWeight {
            maxWeight = w.current[key.ID]
            selected = key
        }
    }

    if selected != nil {
        w.current[selected.ID] -= sumWeights(keys, w.weights)
    }

    return selected, nil
}

func sumWeights(keys []domain.KeyInfo, weights map[string]int) int {
    total := 0
    for _, key := range keys {
        w := weights[key.ID]
        if w == 0 {
            w = 1
        }
        total += w
    }
    return total
}

// 2. 最低延迟策略（Lowest Latency）
type LowestLatencyStrategy struct {
    latencyTracker *LatencyTracker
}

func (s *LowestLatencyStrategy) Select(ctx context.Context, keys []domain.KeyInfo, req *domain.ProxyRequest) (*domain.KeyInfo, error) {
    var selected *domain.KeyInfo
    minLatency := time.Duration(1<<63 - 1)

    for i := range keys {
        key := &keys[i]
        latency := s.latencyTracker.GetAverage(key.ID)
        if latency < minLatency {
            minLatency = latency
            selected = key
        }
    }

    return selected, nil
}

// 3. 最高性价比策略（Best Price-Performance）
type BestPricePerformanceStrategy struct {
    pricePerToken map[string]float64 // keyID -> price per 1K tokens
}

func (s *BestPricePerformanceStrategy) Select(ctx context.Context, keys []domain.KeyInfo, req *domain.ProxyRequest) (*domain.KeyInfo, error) {
    var selected *domain.KeyInfo
    bestRatio := math.MaxFloat64

    for i := range keys {
        key := &keys[i]
        price := s.pricePerToken[key.ID]
        if price == 0 {
            price = key.DefaultPrice
        }
        latency := key.AvgLatency
        if latency == 0 {
            latency = 1 // 避免除以零
        }

        ratio := price / float64(latency)
        if ratio < bestRatio {
            bestRatio = ratio
            selected = key
        }
    }

    return selected, nil
}

// 4. 会话亲和性策略（Session Affinity）
type SessionAffinityStrategy struct {
    fallback RouteStrategy
    affinity *AffinityStore
}

func (s *SessionAffinityStrategy) Select(ctx context.Context, keys []domain.KeyInfo, req *domain.ProxyRequest) (*domain.KeyInfo, error) {
    // 基于 buyer ID 或会话 ID 查找历史路由记录
    buyerID := req.BuyerID
    if buyerID == "" {
        return s.fallback.Select(ctx, keys, req)
    }

    lastKeyID := s.affinity.GetLastKey(buyerID)
    if lastKeyID != "" {
        for i := range keys {
            if keys[i].ID == lastKeyID && keys[i].IsHealthy {
                return &keys[i], nil
            }
        }
    }

    // 回退到 fallback 策略
    selected, err := s.fallback.Select(ctx, keys, req)
    if err != nil {
        return nil, err
    }
    s.affinity.SetLastKey(buyerID, selected.ID)
    return selected, nil
}
```

#### 3.2.2 KeyPool 管理器

```go
// pkg/router/pool.go
package router

import (
    "context"
    "sync"
    "time"

    "tokenmarket/proxy-gateway/internal/domain"
)

// KeyPool 维护各平台可用 Key 列表
type KeyPool struct {
    pools     map[string][]domain.KeyInfo // platform -> keys
    health    map[string]bool             // keyID -> healthy
    mu        sync.RWMutex
    ticker    *time.Ticker
    stopCh    chan struct{}
    checker   HealthChecker
}

func NewKeyPool(checker HealthChecker) *KeyPool {
    return &KeyPool{
        pools:   make(map[string][]domain.KeyInfo),
        health:  make(map[string]bool),
        stopCh:  make(chan struct{}),
        checker: checker,
    }
}

func (p *KeyPool) Start(ctx context.Context) {
    p.ticker = time.NewTicker(30 * time.Second)
    go p.healthCheckLoop(ctx)
}

func (p *KeyPool) Stop() {
    if p.ticker != nil {
        p.ticker.Stop()
    }
    close(p.stopCh)
}

func (p *KeyPool) healthCheckLoop(ctx context.Context) {
    for {
        select {
        case <-p.ticker.C:
            p.runHealthCheck(ctx)
        case <-p.stopCh:
            return
        case <-ctx.Done():
            return
        }
    }
}

func (p *KeyPool) runHealthCheck(ctx context.Context) {
    p.mu.RLock()
    allKeys := make([]domain.KeyInfo, 0)
    for _, keys := range p.pools {
        allKeys = append(allKeys, keys...)
    }
    p.mu.RUnlock()

    // 使用 errgroup 并发健康检查
    g, ctx := errgroup.WithContext(ctx)
    g.SetLimit(10) // 限制并发数

    results := make(map[string]bool)
    var mu sync.Mutex

    for _, key := range allKeys {
        key := key // 闭包捕获
        g.Go(func() error {
            healthy, err := p.checker.Check(ctx, key)
            mu.Lock()
            results[key.ID] = err == nil && healthy
            mu.Unlock()
            return nil
        })
    }

    _ = g.Wait()

    p.mu.Lock()
    for id, healthy := range results {
        p.health[id] = healthy
    }
    p.mu.Unlock()
}

func (p *KeyPool) GetAvailableKeys(platform string) []domain.KeyInfo {
    p.mu.RLock()
    defer p.mu.RUnlock()

    keys := p.pools[platform]
    available := make([]domain.KeyInfo, 0, len(keys))
    for _, key := range keys {
        if p.health[key.ID] {
            available = append(available, key)
        }
    }
    return available
}

func (p *KeyPool) UpdateKeys(platform string, keys []domain.KeyInfo) {
    p.mu.Lock()
    defer p.mu.Unlock()
    p.pools[platform] = keys
}
```

#### 3.2.3 会话亲和性存储

```go
// pkg/router/affinity.go
package router

import (
    "sync"
    "time"
)

// AffinityStore 会话亲和性存储
type AffinityStore struct {
    store map[string]affinityEntry
    mu    sync.RWMutex
    ttl   time.Duration
}

type affinityEntry struct {
    keyID     string
    expiresAt time.Time
}

func NewAffinityStore(ttl time.Duration) *AffinityStore {
    store := &AffinityStore{
        store: make(map[string]affinityEntry),
        ttl:   ttl,
    }
    go store.cleanupLoop()
    return store
}

func (s *AffinityStore) GetLastKey(buyerID string) string {
    s.mu.RLock()
    entry, ok := s.store[buyerID]
    s.mu.RUnlock()

    if !ok || time.Now().After(entry.expiresAt) {
        return ""
    }
    return entry.keyID
}

func (s *AffinityStore) SetLastKey(buyerID, keyID string) {
    s.mu.Lock()
    s.store[buyerID] = affinityEntry{
        keyID:     keyID,
        expiresAt: time.Now().Add(s.ttl),
    }
    s.mu.Unlock()
}

func (s *AffinityStore) cleanupLoop() {
    ticker := time.NewTicker(5 * time.Minute)
    for range ticker.C {
        s.cleanup()
    }
}

func (s *AffinityStore) cleanup() {
    s.mu.Lock()
    defer s.mu.Unlock()
    now := time.Now()
    for buyerID, entry := range s.store {
        if now.After(entry.expiresAt) {
            delete(s.store, buyerID)
        }
    }
}
```

---

### 3.3 平台适配器设计（关键！强兼容）

#### 3.3.1 PlatformAdapter 接口定义

```go
// pkg/platform/adapter.go
package platform

import "context"

// PlatformAdapter 统一平台适配器接口
// 所有平台适配器必须实现此接口，确保调用方无需关心平台差异
type PlatformAdapter interface {
    // Name 返回平台名称（volcano/zhipu/minimax/kimi/claude/gpt）
    Name() string

    // ValidateKey 验证平台 Key 是否有效
    ValidateKey(ctx context.Context, key string) (*KeyInfo, error)

    // Forward 转发请求到目标平台
    // originalKey: 经过解密后的真实平台 Key
    Forward(ctx context.Context, req *ProxyRequest, originalKey string) (*ProxyResponse, error)

    // StreamForward 流式转发请求
    StreamForward(ctx context.Context, req *ProxyRequest, originalKey string) (<-chan StreamChunk, error)

    // ParseUsage 从响应中解析 Token 使用量
    ParseUsage(resp *ProxyResponse) (*UsageInfo, error)

    // ParseStreamChunk 从流式块中解析 Token 使用量
    ParseStreamChunk(chunk []byte) (*UsageInfo, error)

    // TransformRequest 将统一请求转换为平台特定格式
    TransformRequest(req *ProxyRequest) ([]byte, error)

    // TransformResponse 将平台响应转换回统一格式
    TransformResponse(body []byte, statusCode int) (*ProxyResponse, error)

    // TransformStreamChunk 将平台流式块转换回统一格式
    TransformStreamChunk(chunk []byte) ([]byte, error)

    // HealthCheck 检查平台 Key 健康状态
    HealthCheck(ctx context.Context, key string) error

    // GetBalance 获取 Key 余额（可选，部分平台不支持）
    GetBalance(ctx context.Context, key string) (*BalanceInfo, error)
}

// KeyInfo Key 元信息
type KeyInfo struct {
    ID            string
    Platform      string
    OriginalKey   string
    IsHealthy     bool
    AvgLatency    time.Duration
    DefaultPrice  float64
    Weight        int
    RemainingQuota float64
}

// ProxyRequest 统一代理请求
type ProxyRequest struct {
    RequestID     string
    BuyerID       string
    ProxyKey      string
    Platform      string
    Model         string
    Messages      []Message
    Stream        bool
    Temperature   float64
    MaxTokens     int
    RateLimitKey  string
    Headers       map[string]string
    Body          []byte
}

// ProxyResponse 统一代理响应
type ProxyResponse struct {
    StatusCode    int
    Headers       map[string]string
    Body          []byte
    Model         string
    Content       string
    Usage         *UsageInfo
}

// StreamChunk 流式响应块
type StreamChunk struct {
    Data  []byte
    Done  bool
    Error error
}

// UsageInfo Token 使用量
type UsageInfo struct {
    PromptTokens     int
    CompletionTokens int
    TotalTokens      int
    RemainingBalance float64
    CostCents        int64
}

// BalanceInfo Key 余额信息
type BalanceInfo struct {
    Total     float64
    Used      float64
    Remaining float64
    Currency  string
}

// Message 对话消息
type Message struct {
    Role    string `json:"role"`
    Content string `json:"content"`
}
```

#### 3.3.2 适配器注册中心

```go
// pkg/platform/registry.go
package platform

import (
    "fmt"
    "sync"
)

// Registry 适配器注册中心
type Registry struct {
    adapters map[string]PlatformAdapter
    mu       sync.RWMutex
}

func NewRegistry() *Registry {
    return &Registry{
        adapters: make(map[string]PlatformAdapter),
    }
}

func (r *Registry) Register(name string, adapter PlatformAdapter) {
    r.mu.Lock()
    defer r.mu.Unlock()
    r.adapters[name] = adapter
}

func (r *Registry) Get(name string) (PlatformAdapter, error) {
    r.mu.RLock()
    defer r.mu.RUnlock()
    adapter, ok := r.adapters[name]
    if !ok {
        return nil, fmt.Errorf("platform adapter %q not registered", name)
    }
    return adapter, nil
}

func (r *Registry) List() []string {
    r.mu.RLock()
    defer r.mu.RUnlock()
    names := make([]string, 0, len(r.adapters))
    for name := range r.adapters {
        names = append(names, name)
    }
    return names
}

func (r *Registry) Has(name string) bool {
    r.mu.RLock()
    defer r.mu.RUnlock()
    _, ok := r.adapters[name]
    return ok
}
```

#### 3.3.3 适配器目录结构

```
internal/infrastructure/platform/
├── base_adapter.go            # 基础适配器（通用 HTTP 逻辑、错误处理）
├── volcano_adapter.go         # 火山方舟适配器
├── zhipu_adapter.go           # 智谱 GLM 适配器
├── minimax_adapter.go         # MiniMax 适配器
├── kimi_adapter.go            # 月之暗面 Kimi 适配器
├── claude_adapter.go          # Anthropic Claude 适配器
├── gpt_adapter.go             # OpenAI GPT 适配器
└── transformer.go             # 通用请求/响应转换器
```

**每个适配器文件格式**：

```go
// internal/infrastructure/platform/volcano_adapter.go
package platform

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "time"

    "tokenmarket/proxy-gateway/pkg/platform"
)

// VolcanoAdapter 火山方舟平台适配器
type VolcanoAdapter struct {
    baseURL    string
    httpClient *http.Client
}

// 确保实现接口
var _ platform.PlatformAdapter = (*VolcanoAdapter)(nil)

func NewVolcanoAdapter(cfg VolcanoConfig) *VolcanoAdapter {
    return &VolcanoAdapter{
        baseURL: cfg.BaseURL,
        httpClient: &http.Client{
            Timeout: cfg.Timeout,
        },
    }
}

func (a *VolcanoAdapter) Name() string {
    return "volcano"
}

func (a *VolcanoAdapter) ValidateKey(ctx context.Context, key string) (*platform.KeyInfo, error) {
    // 火山方舟：通过调用模型列表接口验证 Key
    req, err := http.NewRequestWithContext(ctx, "GET",
        fmt.Sprintf("%s/api/v3/models", a.baseURL), nil)
    if err != nil {
        return nil, fmt.Errorf("create request: %w", err)
    }
    req.Header.Set("Authorization", "Bearer "+key)

    resp, err := a.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("validate key: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("invalid key, status: %d", resp.StatusCode)
    }

    return &platform.KeyInfo{
        Platform:    "volcano",
        OriginalKey: key,
        IsHealthy:   true,
    }, nil
}

func (a *VolcanoAdapter) Forward(ctx context.Context, req *platform.ProxyRequest, originalKey string) (*platform.ProxyResponse, error) {
    body, err := a.TransformRequest(req)
    if err != nil {
        return nil, fmt.Errorf("transform request: %w", err)
    }

    httpReq, err := http.NewRequestWithContext(ctx, "POST",
        fmt.Sprintf("%s/api/v3/chat/completions", a.baseURL), bytes.NewReader(body))
    if err != nil {
        return nil, fmt.Errorf("create request: %w", err)
    }
    httpReq.Header.Set("Content-Type", "application/json")
    httpReq.Header.Set("Authorization", "Bearer "+originalKey)

    resp, err := a.httpClient.Do(httpReq)
    if err != nil {
        return nil, fmt.Errorf("forward request: %w", err)
    }
    defer resp.Body.Close()

    respBody, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("read response: %w", err)
    }

    return a.TransformResponse(respBody, resp.StatusCode)
}

func (a *VolcanoAdapter) StreamForward(ctx context.Context, req *platform.ProxyRequest, originalKey string) (<-chan platform.StreamChunk, error) {
    // SSE 流式实现...
    // 具体实现省略，返回 channel
    return nil, nil
}

func (a *VolcanoAdapter) ParseUsage(resp *platform.ProxyResponse) (*platform.UsageInfo, error) {
    // 火山方舟响应格式：
    // { "usage": { "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30 } }
    var result struct {
        Usage struct {
            PromptTokens     int `json:"prompt_tokens"`
            CompletionTokens int `json:"completion_tokens"`
            TotalTokens      int `json:"total_tokens"`
        } `json:"usage"`
    }

    if err := json.Unmarshal(resp.Body, &result); err != nil {
        return nil, fmt.Errorf("parse usage: %w", err)
    }

    return &platform.UsageInfo{
        PromptTokens:     result.Usage.PromptTokens,
        CompletionTokens: result.Usage.CompletionTokens,
        TotalTokens:      result.Usage.TotalTokens,
    }, nil
}

func (a *VolcanoAdapter) ParseStreamChunk(chunk []byte) (*platform.UsageInfo, error) {
    // 火山方舟流式：在最后一个 chunk 中返回 usage
    // 解析 SSE 数据行...
    return nil, nil
}

func (a *VolcanoAdapter) TransformRequest(req *platform.ProxyRequest) ([]byte, error) {
    // 火山方舟使用 OpenAI-compatible 格式，直接透传
    return req.Body, nil
}

func (a *VolcanoAdapter) TransformResponse(body []byte, statusCode int) (*platform.ProxyResponse, error) {
    return &platform.ProxyResponse{
        StatusCode: statusCode,
        Body:       body,
        Headers:    map[string]string{"Content-Type": "application/json"},
    }, nil
}

func (a *VolcanoAdapter) TransformStreamChunk(chunk []byte) ([]byte, error) {
    // 火山方舟流式格式已 OpenAI-compatible，直接透传
    return chunk, nil
}

func (a *VolcanoAdapter) HealthCheck(ctx context.Context, key string) error {
    // 复用 ValidateKey 逻辑
    _, err := a.ValidateKey(ctx, key)
    return err
}

func (a *VolcanoAdapter) GetBalance(ctx context.Context, key string) (*platform.BalanceInfo, error) {
    // 火山方舟暂不提供余额查询接口，返回零值
    return &platform.BalanceInfo{
        Total:     0,
        Remaining: 0,
        Currency:  "CNY",
    }, nil
}
```

---

### 3.4 计量数据采集

#### 3.4.1 架构设计

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Response   │────▶│ Token Parser │────▶│ Usage Info   │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │ Async Queue  │
                                        │ (channel)    │
                                        └──────┬───────┘
                                               │
                          ┌────────────────────┼────────────────────┐
                          │                    │                    │
                          ▼                    ▼                    ▼
                   ┌────────────┐      ┌────────────┐      ┌────────────┐
                   │   Kafka    │      │   Redis    │      │   Log     │
                   │  Producer  │      │   Cache    │      │  Backup   │
                   └────────────┘      └────────────┘      └────────────┘
```

#### 3.4.2 核心代码

```go
// pkg/meter/parser.go
package meter

import (
    "encoding/json"
    "fmt"
    "strings"

    "tokenmarket/proxy-gateway/pkg/platform"
)

// Parser Token 使用解析器
type Parser struct {
    platform string
}

func NewParser(platform string) *Parser {
    return &Parser{platform: platform}
}

func (p *Parser) Parse(resp *platform.ProxyResponse) (*platform.UsageInfo, error) {
    switch p.platform {
    case "volcano", "zhipu", "kimi", "gpt":
        return p.parseOpenAICompatible(resp.Body)
    case "minimax":
        return p.parseMiniMax(resp.Body)
    case "claude":
        return p.parseClaude(resp.Body)
    default:
        return nil, fmt.Errorf("unsupported platform: %s", p.platform)
    }
}

func (p *Parser) parseOpenAICompatible(body []byte) (*platform.UsageInfo, error) {
    var result struct {
        Usage struct {
            PromptTokens     int `json:"prompt_tokens"`
            CompletionTokens int `json:"completion_tokens"`
            TotalTokens      int `json:"total_tokens"`
        } `json:"usage"`
    }

    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("unmarshal usage: %w", err)
    }

    return &platform.UsageInfo{
        PromptTokens:     result.Usage.PromptTokens,
        CompletionTokens: result.Usage.CompletionTokens,
        TotalTokens:      result.Usage.TotalTokens,
    }, nil
}

func (p *Parser) parseMiniMax(body []byte) (*platform.UsageInfo, error) {
    // MiniMax 特殊格式解析
    var result struct {
        Usage struct {
            TotalTokens int `json:"total_tokens"`
        } `json:"usage"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, err
    }
    return &platform.UsageInfo{
        TotalTokens: result.Usage.TotalTokens,
    }, nil
}

func (p *Parser) parseClaude(body []byte) (*platform.UsageInfo, error) {
    // Anthropic 格式解析
    var result struct {
        Usage struct {
            InputTokens  int `json:"input_tokens"`
            OutputTokens int `json:"output_tokens"`
        } `json:"usage"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, err
    }
    return &platform.UsageInfo{
        PromptTokens:     result.Usage.InputTokens,
        CompletionTokens: result.Usage.OutputTokens,
        TotalTokens:      result.Usage.InputTokens + result.Usage.OutputTokens,
    }, nil
}

// StreamParser 流式响应解析器
type StreamParser struct {
    platform string
}

func (p *StreamParser) ParseChunk(chunk []byte) (*platform.UsageInfo, error) {
    // SSE 格式解析：data: {...}
    lines := strings.Split(string(chunk), "\n")
    for _, line := range lines {
        if !strings.HasPrefix(line, "data: ") {
            continue
        }
        data := strings.TrimPrefix(line, "data: ")
        if data == "[DONE]" {
            continue
        }

        var result struct {
            Usage *struct {
                PromptTokens     int `json:"prompt_tokens"`
                CompletionTokens int `json:"completion_tokens"`
                TotalTokens      int `json:"total_tokens"`
            } `json:"usage"`
        }
        if err := json.Unmarshal([]byte(data), &result); err != nil {
            continue
        }
        if result.Usage != nil {
            return &platform.UsageInfo{
                PromptTokens:     result.Usage.PromptTokens,
                CompletionTokens: result.Usage.CompletionTokens,
                TotalTokens:      result.Usage.TotalTokens,
            }, nil
        }
    }
    return nil, nil // 当前 chunk 无 usage 信息
}
```

```go
// pkg/meter/aggregator.go
package meter

import (
    "context"
    "sync"
    "time"

    "tokenmarket/proxy-gateway/pkg/platform"
)

// Aggregator 实时用量聚合器
type Aggregator struct {
    cache      UsageCache
    buffer     map[string]*platform.UsageInfo // buyerID -> 聚合用量
    mu         sync.Mutex
    flushInterval time.Duration
    stopCh     chan struct{}
}

func NewAggregator(cache UsageCache, flushInterval time.Duration) *Aggregator {
    a := &Aggregator{
        cache:         cache,
        buffer:        make(map[string]*platform.UsageInfo),
        flushInterval: flushInterval,
        stopCh:        make(chan struct{}),
    }
    go a.flushLoop()
    return a
}

func (a *Aggregator) Record(ctx context.Context, buyerID string, usage *platform.UsageInfo) {
    a.mu.Lock()
    defer a.mu.Unlock()

    if existing, ok := a.buffer[buyerID]; ok {
        existing.PromptTokens += usage.PromptTokens
        existing.CompletionTokens += usage.CompletionTokens
        existing.TotalTokens += usage.TotalTokens
    } else {
        a.buffer[buyerID] = &platform.UsageInfo{
            PromptTokens:     usage.PromptTokens,
            CompletionTokens: usage.CompletionTokens,
            TotalTokens:      usage.TotalTokens,
        }
    }
}

func (a *Aggregator) flushLoop() {
    ticker := time.NewTicker(a.flushInterval)
    defer ticker.Stop()

    for {
        select {
        case <-ticker.C:
            a.flush()
        case <-a.stopCh:
            a.flush()
            return
        }
    }
}

func (a *Aggregator) flush() {
    a.mu.Lock()
    snapshot := a.buffer
    a.buffer = make(map[string]*platform.UsageInfo)
    a.mu.Unlock()

    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()

    for buyerID, usage := range snapshot {
        if err := a.cache.Increment(ctx, buyerID, usage.TotalTokens); err != nil {
            // 记录日志，不中断流程
            continue
        }
    }
}

func (a *Aggregator) Stop() {
    close(a.stopCh)
}

// UsageCache 接口
type UsageCache interface {
    Increment(ctx context.Context, key string, tokens int) error
    Get(ctx context.Context, key string) (int, error)
    Reset(ctx context.Context, key string) error
}
```

```go
// internal/infrastructure/kafka/producer.go
package kafka

import (
    "context"
    "encoding/json"
    "fmt"
    "time"

    "github.com/segmentio/kafka-go"
    "tokenmarket/proxy-gateway/internal/domain"
)

// Producer 计量事件生产者
type Producer struct {
    writer *kafka.Writer
    topic  string
}

func NewProducer(brokers []string, topic string) *Producer {
    return &Producer{
        writer: &kafka.Writer{
            Addr:     kafka.TCP(brokers...),
            Topic:    topic,
            Balancer: &kafka.LeastBytes{},
            Async:    true,
        },
        topic: topic,
    }
}

func (p *Producer) Publish(ctx context.Context, event *domain.UsageEvent) error {
    payload, err := json.Marshal(event)
    if err != nil {
        return fmt.Errorf("marshal event: %w", err)
    }

    msg := kafka.Message{
        Key:   []byte(event.RequestID),
        Value: payload,
        Time:  time.Now(),
    }

    if err := p.writer.WriteMessages(ctx, msg); err != nil {
        return fmt.Errorf("write message: %w", err)
    }

    return nil
}

func (p *Producer) Close() error {
    return p.writer.Close()
}
```



---

## 4. API 设计规范

### 4.1 代理接口（买家调用）

所有代理接口统一前缀 `/v1/proxy/{platform}/`，支持 OpenAI-compatible 格式，降低买家迁移成本。

```
POST /v1/proxy/{platform}/chat/completions
POST /v1/proxy/{platform}/embeddings
GET  /v1/proxy/{platform}/models
```

**请求头规范**：

| Header | 必填 | 说明 |
|---|---|---|
| `Authorization` | 是 | `Bearer {proxy_key}`，L2 代理 Key |
| `Content-Type` | 是 | `application/json` |
| `X-Request-ID` | 否 | 买家自定义请求 ID（用于链路追踪） |
| `X-Route-Strategy` | 否 | 路由策略覆盖：`weighted`, `latency`, `price`, `affinity`，默认 `weighted` |

**请求体示例（chat/completions）**：

```json
{
  "model": "gpt-4o",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 2048
}
```

**响应头规范**：

| Header | 说明 |
|---|---|
| `X-Request-ID` | 网关生成的唯一请求 ID |
| `X-Remaining-Balance` | 买家剩余额度（浮点数，单位：分） |
| `X-Platform-Name` | 实际路由到的平台名称 |
| `X-Model-Used` | 实际使用的模型 |
| `X-Response-Time` | 网关处理耗时（毫秒） |

**响应体示例（非流式）**：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1699999999,
  "model": "gpt-4o",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "Hello! How can I help you today?"},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 10,
    "total_tokens": 30
  }
}
```

**SSE 流式响应规范**：

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Request-ID: req_abc123

// 流式响应

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1699999999,"model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1699999999,"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

// ... 更多 chunk

// 最后一个 chunk（包含 usage，如平台支持）
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1699999999,"model":"gpt-4o","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":20,"completion_tokens":10,"total_tokens":30}}

data: [DONE]

```

**路由参数说明**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `platform` | path | 目标平台：`volcano` / `zhipu` / `minimax` / `kimi` / `claude` / `gpt` |

---

### 4.2 管理接口（内部调用）

管理接口前缀 `/v1/admin/`，需内部认证（IP 白名单或内部 Token）。

```
GET  /health                    # 网关健康检查
GET  /v1/admin/keys/status      # 获取各平台 Key 状态
POST /v1/admin/keys/refresh     # 强制刷新 KeyPool
GET  /v1/admin/metrics          # Prometheus 指标端点
GET  /v1/admin/routing/stats    # 路由统计信息
POST /v1/admin/routing/strategy # 动态切换路由策略
```

#### 4.2.1 健康检查

```
GET /health

响应：
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime": "72h15m",
  "checks": {
    "redis": {"status": "pass", "latency_ms": 2},
    "kafka": {"status": "pass", "latency_ms": 15},
    "platforms": {
      "volcano": {"status": "pass", "available_keys": 3},
      "zhipu": {"status": "pass", "available_keys": 2},
      "minimax": {"status": "fail", "error": "timeout"}
    }
  }
}
```

#### 4.2.2 Key 状态查询

```
GET /v1/admin/keys/status

响应：
{
  "volcano": {
    "total_keys": 5,
    "healthy_keys": 3,
    "unhealthy_keys": 2,
    "keys": [
      {"id": "vk_001", "status": "healthy", "latency_ms": 120, "last_check": "2024-01-15T10:00:00Z"},
      {"id": "vk_002", "status": "unhealthy", "error": "401 Unauthorized", "last_check": "2024-01-15T10:00:00Z"}
    ]
  },
  "zhipu": {
    "total_keys": 3,
    "healthy_keys": 3,
    "keys": [...]
  }
}
```

#### 4.2.3 强制刷新 KeyPool

```
POST /v1/admin/keys/refresh

请求体：
{
  "platform": "volcano"  // 可选，不指定则刷新全部
}

响应：
{
  "success": true,
  "refreshed_platforms": ["volcano", "zhipu"],
  "timestamp": "2024-01-15T10:05:00Z"
}
```

---

### 4.3 API 通用规范

#### 4.3.1 响应结构

```go
// 统一 API 响应结构
type APIResponse struct {
    Success bool        `json:"success"`
    Code    string      `json:"code"`
    Message string      `json:"message"`
    Data    interface{} `json:"data,omitempty"`
    Error   *APIError   `json:"error,omitempty"`
    Meta    *MetaInfo   `json:"meta,omitempty"`
}

type APIError struct {
    Code    string `json:"code"`
    Message string `json:"message"`
    Details string `json:"details,omitempty"`
}

type MetaInfo struct {
    RequestID string `json:"request_id"`
    Timestamp int64  `json:"timestamp"`
}

// 成功响应
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {...},
  "meta": {
    "request_id": "req_abc123",
    "timestamp": 1699999999000
  }
}

// 错误响应
{
  "success": false,
  "code": "AUTH_KEY_INVALID",
  "message": "proxy key validation failed",
  "error": {
    "code": "AUTH_KEY_INVALID",
    "message": "proxy key validation failed",
    "details": "key token_xxx has expired or been revoked"
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": 1699999999000
  }
}
```

#### 4.3.2 分页规范

```go
type PageRequest struct {
    Page     int `form:"page" json:"page"`         // 页码，从 1 开始
    PageSize int `form:"page_size" json:"page_size"` // 每页数量，默认 20，最大 100
}

type PageResponse struct {
    List       interface{} `json:"list"`
    Total      int64       `json:"total"`
    Page       int         `json:"page"`
    PageSize   int         `json:"page_size"`
    TotalPages int         `json:"total_pages"`
    HasMore    bool        `json:"has_more"`
}
```

#### 4.3.3 时间格式

- 所有时间字段使用 **RFC 3339** 格式（`2006-01-02T15:04:05Z`）
- 时间戳使用 **Unix 毫秒**（`1699999999000`）

---

## 5. 错误处理规范

### 5.1 统一错误结构

```go
// internal/domain/errors.go
package domain

import "fmt"

// ErrorCode 错误码类型
type ErrorCode string

const (
    // 系统级错误 (SYS)
    ErrCodeInternal       ErrorCode = "SYS_INTERNAL"
    ErrCodeTimeout        ErrorCode = "SYS_TIMEOUT"
    ErrCodeUnavailable    ErrorCode = "SYS_UNAVAILABLE"
    ErrCodeConfigError    ErrorCode = "SYS_CONFIG"

    // 认证错误 (AUTH)
    ErrCodeKeyInvalid     ErrorCode = "AUTH_KEY_INVALID"
    ErrCodeKeyExpired     ErrorCode = "AUTH_KEY_EXPIRED"
    ErrCodeKeyRevoked     ErrorCode = "AUTH_KEY_REVOKED"
    ErrCodeUnauthorized   ErrorCode = "AUTH_UNAUTHORIZED"

    // 路由错误 (ROUTING)
    ErrCodeNoAvailableKey ErrorCode = "ROUTING_NO_KEY"
    ErrCodePlatformDown   ErrorCode = "ROUTING_PLATFORM_DOWN"
    ErrCodeRateLimited    ErrorCode = "ROUTING_RATE_LIMIT"

    // 平台错误 (PLATFORM)
    ErrCodePlatformError  ErrorCode = "PLATFORM_ERROR"
    ErrCodePlatformTimeout ErrorCode = "PLATFORM_TIMEOUT"
    ErrCodeInvalidResponse ErrorCode = "PLATFORM_INVALID_RESPONSE"

    // 计费错误 (BILLING)
    ErrCodeInsufficientQuota ErrorCode = "BILLING_INSUFFICIENT_QUOTA"
    ErrCodeParseUsage     ErrorCode = "BILLING_PARSE_USAGE"
)

// DomainError 领域错误
type DomainError struct {
    Code    ErrorCode `json:"code"`
    Message string    `json:"message"`
    Details string    `json:"details,omitempty"`
    Err     error     `json:"-"`
}

func (e *DomainError) Error() string {
    if e.Err != nil {
        return fmt.Sprintf("[%s] %s: %v", e.Code, e.Message, e.Err)
    }
    return fmt.Sprintf("[%s] %s", e.Code, e.Message)
}

func (e *DomainError) Unwrap() error {
    return e.Err
}

// 构造函数
func NewSystemError(msg string, err error) *DomainError {
    return &DomainError{Code: ErrCodeInternal, Message: msg, Err: err}
}

func NewAuthError(msg string, err error) *DomainError {
    return &DomainError{Code: ErrCodeKeyInvalid, Message: msg, Err: err}
}

func NewRateLimitError(msg string) *DomainError {
    return &DomainError{Code: ErrCodeRateLimited, Message: msg}
}

func NewRoutingError(msg string, err error) *DomainError {
    return &DomainError{Code: ErrCodeNoAvailableKey, Message: msg, Err: err}
}

func NewPlatformError(msg string, err error) *DomainError {
    return &DomainError{Code: ErrCodePlatformError, Message: msg, Err: err}
}

func NewBillingError(msg string, err error) *DomainError {
    return &DomainError{Code: ErrCodeParseUsage, Message: msg, Err: err}
}
```

### 5.2 错误码分层

| 层级 | 前缀 | 说明 | HTTP 状态码映射 |
|---|---|---|---|
| `SYS` | `SYS_*` | 系统内部错误 | 500 |
| `AUTH` | `AUTH_*` | 认证鉴权错误 | 401 |
| `ROUTING` | `ROUTING_*` | 路由策略错误 | 503 / 429 |
| `PLATFORM` | `PLATFORM_*` | 目标平台错误 | 502 / 504 |
| `BILLING` | `BILLING_*` | 计费/额度错误 | 402 / 403 |

### 5.3 HTTP 状态码映射

```go
// interfaces/http/errors/mapper.go
package errors

import (
    "net/http"
    "tokenmarket/proxy-gateway/internal/domain"
)

func MapToHTTPStatus(err error) int {
    var domainErr *domain.DomainError
    if !errors.As(err, &domainErr) {
        return http.StatusInternalServerError
    }

    switch domainErr.Code {
    // AUTH -> 401
    case domain.ErrCodeKeyInvalid, domain.ErrCodeKeyExpired, domain.ErrCodeKeyRevoked:
        return http.StatusUnauthorized

    // ROUTING -> 429 / 503
    case domain.ErrCodeRateLimited:
        return http.StatusTooManyRequests
    case domain.ErrCodeNoAvailableKey, domain.ErrCodePlatformDown:
        return http.StatusServiceUnavailable

    // PLATFORM -> 502 / 504
    case domain.ErrCodePlatformError, domain.ErrCodeInvalidResponse:
        return http.StatusBadGateway
    case domain.ErrCodePlatformTimeout:
        return http.StatusGatewayTimeout

    // BILLING -> 402 / 403
    case domain.ErrCodeInsufficientQuota:
        return http.StatusPaymentRequired

    // SYS -> 500
    default:
        return http.StatusInternalServerError
    }
}
```

### 5.4 Panic Recovery

**每个 goroutine 必须有 defer recover()**：

```go
// interfaces/http/middleware/recovery.go
package middleware

import (
    "fmt"
    "log"
    "net/http"
    "runtime/debug"

    "github.com/gin-gonic/gin"
)

// Recovery 中间件：捕获 handler 内 panic
func Recovery() gin.HandlerFunc {
    return func(c *gin.Context) {
        defer func() {
            if r := recover(); r != nil {
                log.Printf("[PANIC] request_id=%s error=%v\n%s",
                    c.GetString("request_id"), r, string(debug.Stack()))

                c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{
                    "success": false,
                    "code":    "SYS_INTERNAL",
                    "message": "internal server error",
                    "meta": gin.H{
                        "request_id": c.GetString("request_id"),
                    },
                })
            }
        }()
        c.Next()
    }
}

// SafeGo 安全 goroutine 包装器
func SafeGo(fn func()) {
    go func() {
        defer func() {
            if r := recover(); r != nil {
                log.Printf("[GOROUTINE PANIC] recovered: %v\n%s", r, string(debug.Stack()))
            }
        }()
        fn()
    }()
}

// SafeGoWithContext 带 context 的安全 goroutine
func SafeGoWithContext(ctx context.Context, fn func(ctx context.Context)) {
    go func() {
        defer func() {
            if r := recover(); r != nil {
                log.Printf("[GOROUTINE PANIC] recovered: %v\n%s", r, string(debug.Stack()))
            }
        }()
        fn(ctx)
    }()
}
```

### 5.5 错误传播最佳实践

```go
// ✅ 使用 error wrapping 保留原始错误链
if err := doSomething(); err != nil {
    return fmt.Errorf("process request: %w", err)
}

// ✅ 创建领域错误时保留原始错误
if err := adapter.Forward(ctx, req, key); err != nil {
    return domain.NewPlatformError("forward to volcano failed", err)
}

// ✅ 使用 errors.Is 检查特定错误
if errors.Is(err, context.DeadlineExceeded) {
    return domain.NewPlatformError("platform timeout", err)
}

// ✅ 使用 errors.As 提取领域错误
var domainErr *domain.DomainError
if errors.As(err, &domainErr) {
    status := errors.MapToHTTPStatus(domainErr)
}

// ❌ 不要丢失原始错误信息
if err != nil {
    return errors.New("failed") // 丢失了原始错误上下文
}

// ❌ 不要过度包装
if err != nil {
    return fmt.Errorf("layer1: %w", fmt.Errorf("layer2: %w", fmt.Errorf("layer3: %w", err)))
}
```

---

## 6. 并发编程规范

### 6.1 Context 传递

**每个请求必须携带 context，超时/取消级联传递**。

```go
// 请求级超时配置
const (
    DefaultRequestTimeout = 60 * time.Second
    MaxRequestTimeout     = 300 * time.Second
    HealthCheckTimeout    = 10 * time.Second
    MeteringPublishTimeout = 5 * time.Second
)

// handler 中创建带超时的 context
func (h *ProxyHandler) ChatCompletions(c *gin.Context) {
    ctx, cancel := context.WithTimeout(c.Request.Context(), DefaultRequestTimeout)
    defer cancel()

    // 将 context 传递给所有下游调用
    resp, err := h.proxySvc.ExecuteProxy(ctx, req)
    if err != nil {
        handleError(c, err)
        return
    }

    writeResponse(c, resp)
}

// 适配器中使用 context 控制 HTTP 请求
func (a *VolcanoAdapter) Forward(ctx context.Context, req *domain.ProxyRequest, key string) (*domain.ProxyResponse, error) {
    httpReq, err := http.NewRequestWithContext(ctx, "POST", url, body)
    if err != nil {
        return nil, err
    }
    // httpClient.Do 会在 context 取消时自动终止请求
    resp, err := a.httpClient.Do(httpReq)
    // ...
}

// Redis 操作传递 context
func (c *RedisCache) Increment(ctx context.Context, key string, tokens int) error {
    return c.client.IncrBy(ctx, key, int64(tokens)).Err()
}

// Kafka 发送传递 context
func (p *Producer) Publish(ctx context.Context, event *domain.UsageEvent) error {
    return p.writer.WriteMessages(ctx, msg)
}
```

### 6.2 goroutine 管理

**使用 errgroup 管理并发任务，避免 goroutine 泄漏**。

```go
import "golang.org/x/sync/errgroup"

// 并发健康检查示例
func (p *KeyPool) runHealthCheck(ctx context.Context) {
    p.mu.RLock()
    allKeys := p.getAllKeys()
    p.mu.RUnlock()

    g, ctx := errgroup.WithContext(ctx)
    g.SetLimit(20) // 限制最大并发数

    results := make(map[string]bool)
    var mu sync.Mutex

    for _, key := range allKeys {
        key := key // 闭包捕获
        g.Go(func() error {
            healthy := p.checker.Check(ctx, key) == nil
            mu.Lock()
            results[key.ID] = healthy
            mu.Unlock()
            return nil // errgroup 任一 goroutine 返回 error 时全部取消
        })
    }

    // 等待所有 goroutine 完成
    if err := g.Wait(); err != nil {
        log.Printf("health check batch failed: %v", err)
    }
}

// 带超时和取消的并发任务
func (s *ProxyService) parallelFetch(ctx context.Context, keys []string) ([]Result, error) {
    ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
    defer cancel()

    g, ctx := errgroup.WithContext(ctx)
    g.SetLimit(5)

    results := make([]Result, len(keys))

    for i, key := range keys {
        i, key := i, key
        g.Go(func() error {
            res, err := s.fetch(ctx, key)
            if err != nil {
                return err // 任一失败则整体失败
            }
            results[i] = res
            return nil
        })
    }

    if err := g.Wait(); err != nil {
        return nil, err
    }
    return results, nil
}

// 等待组 + channel 模式（不使用 errgroup 时）
func processBatch(ctx context.Context, items []Item) ([]Result, error) {
    ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
    defer cancel()

    type result struct {
        index int
        res   Result
        err   error
    }

    resultCh := make(chan result, len(items))
    var wg sync.WaitGroup

    for i, item := range items {
        wg.Add(1)
        go func(i int, item Item) {
            defer wg.Done()
            res, err := process(ctx, item)
            resultCh <- result{index: i, res: res, err: err}
        }(i, item)
    }

    // 关闭 channel
    go func() {
        wg.Wait()
        close(resultCh)
    }()

    // 收集结果
    results := make([]Result, len(items))
    for r := range resultCh {
        if r.err != nil {
            return nil, r.err
        }
        results[r.index] = r.res
    }

    return results, nil
}
```

### 6.3 通道规范

```go
// ✅ 明确通道方向（只读/只写/双向）

// 生产者：只写通道
func produce(ctx context.Context, out chan<- Event) {
    for {
        select {
        case <-ctx.Done():
            return
        case out <- generateEvent():
        }
    }
}

// 消费者：只读通道
func consume(ctx context.Context, in <-chan Event) {
    for {
        select {
        case <-ctx.Done():
            return
        case event, ok := <-in:
            if !ok {
                return // channel 已关闭
            }
            process(event)
        }
    }
}

// ✅ 有缓冲 vs 无缓冲的选择原则

// 1. 无缓冲通道：同步通信，强耦合（必须配对收发）
ch := make(chan int)           // 无缓冲：发送和接收必须同时就绪

// 2. 有缓冲通道：异步通信，解耦生产消费速率
ch := make(chan int, 100)      // 缓冲 100：允许生产者短暂快于消费者

// 3. 批处理通道：大数据量时使用大缓冲
ch := make(chan []byte, 10)    // 每个元素是一个批次，减少 channel 操作次数

// 4. 扇出模式：一个生产者 + 多个消费者
func fanOut(ctx context.Context, source <-chan Event, workers int) {
    var wg sync.WaitGroup
    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            for event := range source {
                process(event)
            }
        }(i)
    }
    wg.Wait()
}

// 5. 扇入模式：多个生产者 + 一个消费者
func fanIn(ctx context.Context, sources ...<-chan Event) <-chan Event {
    out := make(chan Event)
    var wg sync.WaitGroup

    output := func(c <-chan Event) {
        defer wg.Done()
        for n := range c {
            out <- n
        }
    }

    wg.Add(len(sources))
    for _, c := range sources {
        go output(c)
    }

    go func() {
        wg.Wait()
        close(out)
    }()

    return out
}

// ✅ 通道关闭规范

// 1. 只有发送方才能关闭通道
// 2. 已关闭的通道总是可读的（返回零值 + false）
// 3. 不要重复关闭通道（panic）
// 4. 使用 context 或 done channel 控制退出

func SafeChannelExample() {
    ch := make(chan int, 10)
    done := make(chan struct{})

    // 生产者
    go func() {
        defer close(ch) // 发送方负责关闭
        for i := 0; i < 100; i++ {
            select {
            case <-done:
                return
            case ch <- i:
            }
        }
    }()

    // 消费者
    go func() {
        for val := range ch { // 通道关闭后自动退出
            fmt.Println(val)
        }
    }()
}
```

### 6.4 并发安全模式

```go
// 1. 使用 sync.Map 代替 map + mutex（读多写少场景）
var keyCache sync.Map

func getOrLoad(key string) (*KeyInfo, error) {
    if val, ok := keyCache.Load(key); ok {
        return val.(*KeyInfo), nil
    }

    // 不存在，加载并写入
    info, err := loadFromDB(key)
    if err != nil {
        return nil, err
    }

    actual, loaded := keyCache.LoadOrStore(key, info)
    if loaded {
        return actual.(*KeyInfo), nil
    }
    return info, nil
}

// 2. 使用 atomic 进行计数器操作
type Counter struct {
    value int64
}

func (c *Counter) Inc() int64 {
    return atomic.AddInt64(&c.value, 1)
}

func (c *Counter) Get() int64 {
    return atomic.LoadInt64(&c.value)
}

// 3. 使用 RWMutex（读多写少）
type ConfigStore struct {
    mu     sync.RWMutex
    config map[string]string
}

func (s *ConfigStore) Get(key string) (string, bool) {
    s.mu.RLock()
    defer s.mu.RUnlock()
    val, ok := s.config[key]
    return val, ok
}

func (s *ConfigStore) Set(key, val string) {
    s.mu.Lock()
    defer s.mu.Unlock()
    s.config[key] = val
}

// 4. 使用 sync.Once 实现单例
var (
    instance *Service
    once     sync.Once
)

func GetService() *Service {
    once.Do(func() {
        instance = newService()
    })
    return instance
}

// 5. 使用 context 控制 goroutine 生命周期
func worker(ctx context.Context, input <-chan Task) {
    for {
        select {
        case <-ctx.Done():
            return // context 取消时优雅退出
        case task, ok := <-input:
            if !ok {
                return // 输入通道关闭
            }
            process(task)
        }
    }
}
```

---

## 7. 测试规范

### 7.1 单元测试

**每个 domain 函数必须有测试，覆盖率 ≥ 70%**。

```go
// internal/domain/errors_test.go
package domain

import (
    "errors"
    "testing"
)

func TestDomainError_Error(t *testing.T) {
    tests := []struct {
        name     string
        err      *DomainError
        expected string
    }{
        {
            name:     "with wrapped error",
            err:      NewSystemError("test failed", errors.New("root cause")),
            expected: "[SYS_INTERNAL] test failed: root cause",
        },
        {
            name:     "without wrapped error",
            err:      NewRateLimitError("too many requests"),
            expected: "[ROUTING_RATE_LIMIT] too many requests",
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            if got := tt.err.Error(); got != tt.expected {
                t.Errorf("Error() = %v, want %v", got, tt.expected)
            }
        })
    }
}

func TestMapToHTTPStatus(t *testing.T) {
    tests := []struct {
        code     ErrorCode
        expected int
    }{
        {ErrCodeKeyInvalid, 401},
        {ErrCodeRateLimited, 429},
        {ErrCodePlatformError, 502},
        {ErrCodeInsufficientQuota, 402},
        {ErrCodeInternal, 500},
    }

    for _, tt := range tests {
        t.Run(string(tt.code), func(t *testing.T) {
            err := &DomainError{Code: tt.code, Message: "test"}
            if got := MapToHTTPStatus(err); got != tt.expected {
                t.Errorf("MapToHTTPStatus(%v) = %d, want %d", tt.code, got, tt.expected)
            }
        })
    }
}
```

### 7.2 平台适配器 Mock 测试

**使用 httptest 模拟各平台 API**：

```go
// internal/infrastructure/platform/volcano_adapter_test.go
package platform

import (
    "context"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"

    "tokenmarket/proxy-gateway/pkg/platform"
)

func TestVolcanoAdapter_ValidateKey(t *testing.T) {
    // 创建 mock 服务器
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        auth := r.Header.Get("Authorization")
        if auth != "Bearer valid_key" {
            w.WriteHeader(http.StatusUnauthorized)
            return
        }
        w.WriteHeader(http.StatusOK)
        w.Write([]byte(`{"data":[{"id":"model-1"}]}`))
    }))
    defer server.Close()

    adapter := NewVolcanoAdapter(VolcanoConfig{
        BaseURL: server.URL,
        Timeout: 10 * time.Second,
    })

    ctx := context.Background()

    t.Run("valid key", func(t *testing.T) {
        info, err := adapter.ValidateKey(ctx, "valid_key")
        if err != nil {
            t.Fatalf("unexpected error: %v", err)
        }
        if !info.IsHealthy {
            t.Error("expected key to be healthy")
        }
    })

    t.Run("invalid key", func(t *testing.T) {
        _, err := adapter.ValidateKey(ctx, "invalid_key")
        if err == nil {
            t.Fatal("expected error for invalid key")
        }
    })
}

func TestVolcanoAdapter_Forward(t *testing.T) {
    server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if r.Method != "POST" {
            t.Errorf("expected POST, got %s", r.Method)
        }

        w.Header().Set("Content-Type", "application/json")
        w.WriteHeader(http.StatusOK)
        w.Write([]byte(`{
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [{"index":0,"message":{"role":"assistant","content":"Hello"}}],
            "usage": {"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}
        }`))
    }))
    defer server.Close()

    adapter := NewVolcanoAdapter(VolcanoConfig{
        BaseURL: server.URL,
        Timeout: 10 * time.Second,
    })

    req := &platform.ProxyRequest{
        Model:   "gpt-4o",
        Stream:  false,
        Body:    []byte(`{"model":"gpt-4o","messages":[{"role":"user","content":"Hi"}]}`),
    }

    resp, err := adapter.Forward(context.Background(), req, "test_key")
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    if resp.StatusCode != 200 {
        t.Errorf("expected status 200, got %d", resp.StatusCode)
    }
}

func TestVolcanoAdapter_ParseUsage(t *testing.T) {
    adapter := NewVolcanoAdapter(VolcanoConfig{})

    resp := &platform.ProxyResponse{
        Body: []byte(`{"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}}`),
    }

    usage, err := adapter.ParseUsage(resp)
    if err != nil {
        t.Fatalf("unexpected error: %v", err)
    }

    if usage.PromptTokens != 10 {
        t.Errorf("expected prompt_tokens=10, got %d", usage.PromptTokens)
    }
    if usage.CompletionTokens != 20 {
        t.Errorf("expected completion_tokens=20, got %d", usage.CompletionTokens)
    }
    if usage.TotalTokens != 30 {
        t.Errorf("expected total_tokens=30, got %d", usage.TotalTokens)
    }
}
```

### 7.3 路由引擎 Benchmark

**模拟 10000 QPS 压力测试**：

```go
// tests/benchmark/router_benchmark_test.go
package benchmark

import (
    "context"
    "math/rand"
    "sync"
    "testing"
    "time"

    "tokenmarket/proxy-gateway/pkg/router"
    "tokenmarket/proxy-gateway/pkg/platform"
)

func BenchmarkWeightedRoundRobin_Select(b *testing.B) {
    // 构造 10 个 Key
    keys := make([]platform.KeyInfo, 10)
    for i := 0; i < 10; i++ {
        keys[i] = platform.KeyInfo{
            ID:     fmt.Sprintf("key_%d", i),
            Weight: rand.Intn(5) + 1,
        }
    }

    strategy := router.NewWeightedRoundRobin()
    req := &platform.ProxyRequest{BuyerID: "buyer_001"}
    ctx := context.Background()

    b.ResetTimer()
    b.RunParallel(func(pb *testing.PB) {
        for pb.Next() {
            _, err := strategy.Select(ctx, keys, req)
            if err != nil {
                b.Fatal(err)
            }
        }
    })
}

func BenchmarkLowestLatency_Select(b *testing.B) {
    keys := make([]platform.KeyInfo, 10)
    tracker := router.NewLatencyTracker()

    for i := 0; i < 10; i++ {
        keys[i] = platform.KeyInfo{
            ID:         fmt.Sprintf("key_%d", i),
            AvgLatency: time.Duration(rand.Intn(100)+50) * time.Millisecond,
        }
        tracker.Record(keys[i].ID, keys[i].AvgLatency)
    }

    strategy := router.NewLowestLatencyStrategy(tracker)
    req := &platform.ProxyRequest{BuyerID: "buyer_001"}
    ctx := context.Background()

    b.ResetTimer()
    b.RunParallel(func(pb *testing.PB) {
        for pb.Next() {
            _, err := strategy.Select(ctx, keys, req)
            if err != nil {
                b.Fatal(err)
            }
        }
    })
}

func BenchmarkSessionAffinity_Select(b *testing.B) {
    keys := make([]platform.KeyInfo, 10)
    for i := 0; i < 10; i++ {
        keys[i] = platform.KeyInfo{
            ID: fmt.Sprintf("key_%d", i),
        }
    }

    fallback := router.NewWeightedRoundRobin()
    affinity := router.NewAffinityStore(5 * time.Minute)
    strategy := router.NewSessionAffinityStrategy(fallback, affinity)

    // 预热：绑定 buyer 到 key
    for i := 0; i < 1000; i++ {
        buyerID := fmt.Sprintf("buyer_%d", i)
        affinity.SetLastKey(buyerID, keys[rand.Intn(10)].ID)
    }

    ctx := context.Background()

    b.ResetTimer()
    b.RunParallel(func(pb *testing.PB) {
        i := 0
        for pb.Next() {
            req := &platform.ProxyRequest{BuyerID: fmt.Sprintf("buyer_%d", i%1000)}
            _, err := strategy.Select(ctx, keys, req)
            if err != nil {
                b.Fatal(err)
            }
            i++
        }
    })
}

// 并发安全测试
func TestKeyPool_ConcurrentAccess(t *testing.T) {
    pool := router.NewKeyPool(nil)

    // 并发读写
    var wg sync.WaitGroup
    for i := 0; i < 100; i++ {
        wg.Add(2)
        go func() {
            defer wg.Done()
            pool.UpdateKeys("volcano", []platform.KeyInfo{
                {ID: fmt.Sprintf("key_%d", rand.Intn(10))},
            })
        }()
        go func() {
            defer wg.Done()
            _ = pool.GetAvailableKeys("volcano")
        }()
    }
    wg.Wait()
}
```

### 7.4 集成测试

```go
// tests/integration/proxy_flow_test.go
package integration

import (
    "bytes"
    "context"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "testing"
    "time"

    "github.com/gin-gonic/gin"
    "tokenmarket/proxy-gateway/internal/application"
    "tokenmarket/proxy-gateway/internal/infrastructure/platform"
    "tokenmarket/proxy-gateway/internal/interfaces/http/handlers"
    "tokenmarket/proxy-gateway/pkg/router"
)

func TestProxyFlow_EndToEnd(t *testing.T) {
    // 1. 搭建 mock 平台服务器
    mockPlatform := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        json.NewEncoder(w).Encode(map[string]interface{}{
            "id":      "chatcmpl-test",
            "choices": []map[string]interface{}{{"message": map[string]string{"content": "Hello"}}},
            "usage":   map[string]int{"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })
    }))
    defer mockPlatform.Close()

    // 2. 初始化组件
    registry := platform.NewRegistry()
    adapter := platform.NewVolcanoAdapter(platform.VolcanoConfig{BaseURL: mockPlatform.URL})
    registry.Register("volcano", adapter)

    routingSvc := application.NewRoutingService(registry, router.NewWeightedRoundRobin())
    proxySvc := application.NewProxyService(registry, routingSvc, adapter, nil, nil)

    // 3. 创建 handler
    handler := handlers.NewProxyHandler(proxySvc)

    // 4. 搭建 gin 路由
    gin.SetMode(gin.TestMode)
    r := gin.New()
    r.POST("/v1/proxy/:platform/chat/completions", handler.ChatCompletions)

    // 5. 构造请求
    body, _ := json.Marshal(map[string]interface{}{
        "model":    "gpt-4o",
        "messages": []map[string]string{{"role": "user", "content": "Hi"}},
    })

    req := httptest.NewRequest("POST", "/v1/proxy/volcano/chat/completions", bytes.NewReader(body))
    req.Header.Set("Authorization", "Bearer test_proxy_key")
    req.Header.Set("Content-Type", "application/json")

    w := httptest.NewRecorder()
    r.ServeHTTP(w, req)

    // 6. 验证
    if w.Code != http.StatusOK {
        t.Fatalf("expected 200, got %d", w.Code)
    }

    var resp map[string]interface{}
    if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
        t.Fatal(err)
    }

    // 验证响应头
    if w.Header().Get("X-Request-ID") == "" {
        t.Error("missing X-Request-ID header")
    }

    // 验证响应体
    choices, ok := resp["choices"].([]interface{})
    if !ok || len(choices) == 0 {
        t.Error("expected choices in response")
    }
}
```

---

## 8. 关键代码示例

### 8.1 入口 main.go

```go
// cmd/server/main.go
package main

import (
    "context"
    "log"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"

    "github.com/gin-gonic/gin"
    "tokenmarket/proxy-gateway/internal/application"
    "tokenmarket/proxy-gateway/internal/config"
    "tokenmarket/proxy-gateway/internal/infrastructure/kafka"
    "tokenmarket/proxy-gateway/internal/infrastructure/platform"
    "tokenmarket/proxy-gateway/internal/infrastructure/redis"
    httphandlers "tokenmarket/proxy-gateway/internal/interfaces/http/handlers"
    httpmiddleware "tokenmarket/proxy-gateway/internal/interfaces/http/middleware"
    "tokenmarket/proxy-gateway/pkg/router"
)

func main() {
    // 1. 加载配置
    cfg := config.Load("configs/config.yaml")

    // 2. 初始化基础设施
    redisClient := redis.NewClient(cfg.Redis)
    kafkaProducer := kafka.NewProducer(cfg.Kafka.Brokers, "billing.events")
    defer kafkaProducer.Close()

    // 3. 初始化平台适配器并注册
    registry := platform.NewRegistry()
    registry.Register("volcano", platform.NewVolcanoAdapter(cfg.Platforms.Volcano))
    registry.Register("zhipu", platform.NewZhipuAdapter(cfg.Platforms.Zhipu))
    registry.Register("minimax", platform.NewMiniMaxAdapter(cfg.Platforms.MiniMax))
    registry.Register("kimi", platform.NewKimiAdapter(cfg.Platforms.Kimi))
    registry.Register("claude", platform.NewClaudeAdapter(cfg.Platforms.Claude))
    registry.Register("gpt", platform.NewGPTAdapter(cfg.Platforms.GPT))

    // 4. 初始化路由引擎
    keyPool := router.NewKeyPool(nil)
    keyPool.Start(context.Background())
    defer keyPool.Stop()

    // 5. 初始化应用层服务（依赖注入）
    proxySvc := application.NewProxyService(
        registry,
        router.NewEngine(keyPool),
        router.NewWeightedRoundRobin(),
        kafkaProducer,
        redisClient,
    )

    // 6. 初始化接口层
    proxyHandler := httphandlers.NewProxyHandler(proxySvc)
    adminHandler := httphandlers.NewAdminHandler(nil)
    healthHandler := httphandlers.NewHealthHandler(redisClient, kafkaProducer, registry)

    // 7. 初始化 Gin 引擎
    gin.SetMode(gin.ReleaseMode)
    r := gin.New()

    // 全局中间件（按顺序）
    r.Use(httpmiddleware.Recovery())      // 1. Panic 恢复
    r.Use(httpmiddleware.RequestID())     // 2. 请求 ID
    r.Use(httpmiddleware.Logger())        // 3. 日志
    r.Use(httpmiddleware.CORS())          // 4. 跨域

    // 代理路由
    proxyGroup := r.Group("/v1/proxy/:platform")
    proxyGroup.Use(httpmiddleware.Auth(nil))       // 认证
    proxyGroup.Use(httpmiddleware.RateLimit(nil))  // 限流
    proxyGroup.POST("/chat/completions", proxyHandler.ChatCompletions)
    proxyGroup.POST("/embeddings", proxyHandler.Embeddings)

    // 管理路由
    adminGroup := r.Group("/v1/admin")
    adminGroup.GET("/keys/status", adminHandler.ListKeys)
    adminGroup.POST("/keys/refresh", adminHandler.RefreshKeys)

    // 健康检查
    r.GET("/health", healthHandler.Check)
    r.GET("/v1/admin/metrics", healthHandler.Metrics)

    // 8. 启动服务器
    srv := &http.Server{
        Addr:    cfg.Server.Port,
        Handler: r,
    }

    go func() {
        log.Printf("Server starting on %s", cfg.Server.Port)
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("Server failed: %v", err)
        }
    }()

    // 9. 优雅关闭
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit

    log.Println("Shutting down server...")
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    if err := srv.Shutdown(ctx); err != nil {
        log.Printf("Server forced to shutdown: %v", err)
    }

    log.Println("Server exited")
}
```

### 8.2 Handler 模板

```go
// internal/interfaces/http/handlers/proxy_handler.go
package handlers

import (
    "context"
    "net/http"
    "time"

    "github.com/gin-gonic/gin"
    "tokenmarket/proxy-gateway/internal/application"
    "tokenmarket/proxy-gateway/internal/domain"
    "tokenmarket/proxy-gateway/pkg/platform"
)

// ProxyHandler 代理请求处理器
type ProxyHandler struct {
    proxySvc application.ProxyService
}

func NewProxyHandler(proxySvc application.ProxyService) *ProxyHandler {
    return &ProxyHandler{proxySvc: proxySvc}
}

// ChatCompletions 聊天补全代理接口
// POST /v1/proxy/:platform/chat/completions
func (h *ProxyHandler) ChatCompletions(c *gin.Context) {
    ctx, cancel := context.WithTimeout(c.Request.Context(), 60*time.Second)
    defer cancel()

    // 提取路由参数
    platformName := c.Param("platform")

    // 绑定请求体
    var req platform.ProxyRequest
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, errorResponse("invalid request body", err))
        return
    }

    req.RequestID = c.GetString("request_id")
    req.ProxyKey = extractBearerToken(c.GetHeader("Authorization"))
    req.Platform = platformName

    // 执行代理
    resp, err := h.proxySvc.ExecuteProxy(ctx, &req)
    if err != nil {
        h.handleError(c, err)
        return
    }

    // 注入响应头
    for k, v := range resp.Headers {
        c.Header(k, v)
    }

    // 流式响应处理
    if req.Stream {
        h.handleStreamResponse(c, resp)
        return
    }

    c.Data(resp.StatusCode, "application/json", resp.Body)
}

// Embeddings 嵌入向量代理接口
// POST /v1/proxy/:platform/embeddings
func (h *ProxyHandler) Embeddings(c *gin.Context) {
    // 类似 ChatCompletions 实现...
}

// handleStreamResponse SSE 流式响应
func (h *ProxyHandler) handleStreamResponse(c *gin.Context, resp *platform.ProxyResponse) {
    c.Header("Content-Type", "text/event-stream")
    c.Header("Cache-Control", "no-cache")
    c.Header("Connection", "keep-alive")

    // 实际实现中使用 channel 读取流式数据
    // 这里仅示意
    c.String(http.StatusOK, "data: %s\n\n", resp.Body)
    c.String(http.StatusOK, "data: [DONE]\n\n")
}

// handleError 统一错误处理
func (h *ProxyHandler) handleError(c *gin.Context, err error) {
    var domainErr *domain.DomainError
    if errors.As(err, &domainErr) {
        status := errors.MapToHTTPStatus(domainErr)
        c.JSON(status, gin.H{
            "success": false,
            "code":    domainErr.Code,
            "message": domainErr.Message,
            "details": domainErr.Details,
            "meta": gin.H{"request_id": c.GetString("request_id")},
        })
        return
    }

    c.JSON(http.StatusInternalServerError, gin.H{
        "success": false,
        "code":    "SYS_INTERNAL",
        "message": "internal server error",
        "meta":    gin.H{"request_id": c.GetString("request_id")},
    })
}

func extractBearerToken(auth string) string {
    const prefix = "Bearer "
    if len(auth) > len(prefix) && auth[:len(prefix)] == prefix {
        return auth[len(prefix):]
    }
    return ""
}

func errorResponse(msg string, err error) gin.H {
    return gin.H{
        "success": false,
        "code":    "INVALID_REQUEST",
        "message": msg,
        "details": err.Error(),
    }
}
```

### 8.3 Adapter 模板

```go
// internal/infrastructure/platform/gpt_adapter.go
package platform

import (
    "bytes"
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "time"

    "tokenmarket/proxy-gateway/pkg/platform"
)

// GPTAdapter OpenAI GPT 平台适配器
type GPTAdapter struct {
    baseURL    string
    httpClient *http.Client
}

var _ platform.PlatformAdapter = (*GPTAdapter)(nil)

func NewGPTAdapter(cfg GPTConfig) *GPTAdapter {
    return &GPTAdapter{
        baseURL: cfg.BaseURL,
        httpClient: &http.Client{
            Timeout: cfg.Timeout,
        },
    }
}

func (a *GPTAdapter) Name() string { return "gpt" }

func (a *GPTAdapter) ValidateKey(ctx context.Context, key string) (*platform.KeyInfo, error) {
    req, _ := http.NewRequestWithContext(ctx, "GET",
        fmt.Sprintf("%s/v1/models", a.baseURL), nil)
    req.Header.Set("Authorization", "Bearer "+key)

    resp, err := a.httpClient.Do(req)
    if err != nil {
        return nil, fmt.Errorf("validate key: %w", err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("invalid key, status: %d", resp.StatusCode)
    }

    return &platform.KeyInfo{Platform: "gpt", OriginalKey: key, IsHealthy: true}, nil
}

func (a *GPTAdapter) Forward(ctx context.Context, req *platform.ProxyRequest, key string) (*platform.ProxyResponse, error) {
    body, _ := a.TransformRequest(req)

    httpReq, _ := http.NewRequestWithContext(ctx, "POST",
        fmt.Sprintf("%s/v1/chat/completions", a.baseURL), bytes.NewReader(body))
    httpReq.Header.Set("Content-Type", "application/json")
    httpReq.Header.Set("Authorization", "Bearer "+key)

    resp, err := a.httpClient.Do(httpReq)
    if err != nil {
        return nil, fmt.Errorf("forward: %w", err)
    }
    defer resp.Body.Close()

    respBody, _ := io.ReadAll(resp.Body)
    return a.TransformResponse(respBody, resp.StatusCode)
}

func (a *GPTAdapter) StreamForward(ctx context.Context, req *platform.ProxyRequest, key string) (<-chan platform.StreamChunk, error) {
    // SSE 流式实现
    return nil, fmt.Errorf("not implemented")
}

func (a *GPTAdapter) ParseUsage(resp *platform.ProxyResponse) (*platform.UsageInfo, error) {
    return parseOpenAIUsage(resp.Body)
}

func (a *GPTAdapter) ParseStreamChunk(chunk []byte) (*platform.UsageInfo, error) {
    return parseOpenAIStreamChunk(chunk)
}

func (a *GPTAdapter) TransformRequest(req *platform.ProxyRequest) ([]byte, error) {
    // GPT 使用标准 OpenAI 格式，直接透传
    return req.Body, nil
}

func (a *GPTAdapter) TransformResponse(body []byte, statusCode int) (*platform.ProxyResponse, error) {
    return &platform.ProxyResponse{
        StatusCode: statusCode,
        Body:       body,
        Headers:    map[string]string{"Content-Type": "application/json"},
    }, nil
}

func (a *GPTAdapter) TransformStreamChunk(chunk []byte) ([]byte, error) {
    return chunk, nil
}

func (a *GPTAdapter) HealthCheck(ctx context.Context, key string) error {
    _, err := a.ValidateKey(ctx, key)
    return err
}

func (a *GPTAdapter) GetBalance(ctx context.Context, key string) (*platform.BalanceInfo, error) {
    // OpenAI 不提供余额查询 API
    return &platform.BalanceInfo{Currency: "USD"}, nil
}

// parseOpenAIUsage 解析 OpenAI 格式 usage
func parseOpenAIUsage(body []byte) (*platform.UsageInfo, error) {
    var result struct {
        Usage struct {
            PromptTokens     int `json:"prompt_tokens"`
            CompletionTokens int `json:"completion_tokens"`
            TotalTokens      int `json:"total_tokens"`
        } `json:"usage"`
    }

    if err := json.Unmarshal(body, &result); err != nil {
        return nil, err
    }

    return &platform.UsageInfo{
        PromptTokens:     result.Usage.PromptTokens,
        CompletionTokens: result.Usage.CompletionTokens,
        TotalTokens:      result.Usage.TotalTokens,
    }, nil
}

func parseOpenAIStreamChunk(chunk []byte) (*platform.UsageInfo, error) {
    // SSE chunk 中 usage 在最后一个 data 行
    // 实现省略...
    return nil, nil
}
```

### 8.4 Makefile 模板

```makefile
# proxy-gateway/Makefile

.PHONY: build test test-unit test-integration test-benchmark lint clean run

APP_NAME := proxy-gateway
BUILD_DIR := ./bin
MAIN_PKG := ./cmd/server

# 构建
default: build

build:
	@echo "Building $(APP_NAME)..."
	@mkdir -p $(BUILD_DIR)
	go build -ldflags "-X main.version=$(shell git describe --tags --always) -X main.buildTime=$(shell date -u +%Y-%m-%dT%H:%M:%SZ)" \
		-o $(BUILD_DIR)/$(APP_NAME) $(MAIN_PKG)

# 测试
test: test-unit test-integration

test-unit:
	@echo "Running unit tests..."
	go test -v -race -coverprofile=coverage.out ./internal/... ./pkg/...
	go tool cover -html=coverage.out -o coverage.html

test-integration:
	@echo "Running integration tests..."
	go test -v -tags=integration ./tests/integration/...

test-benchmark:
	@echo "Running benchmarks..."
	go test -bench=. -benchmem -benchtime=10s ./tests/benchmark/...

# 代码质量
lint:
	@echo "Running linter..."
	golangci-lint run ./...

fmt:
	@echo "Formatting code..."
	go fmt ./...
	gofumpt -w .

# 开发
run:
	go run $(MAIN_PKG)

dev:
	air -c .air.toml

# 清理
clean:
	@echo "Cleaning..."
	rm -rf $(BUILD_DIR)
	rm -f coverage.out coverage.html

# 依赖管理
deps:
	go mod tidy
	go mod verify

deps-update:
	go get -u ./...
	go mod tidy

# Docker
docker-build:
	docker build -t $(APP_NAME):latest .

docker-run:
	docker run -p 8080:8080 --env-file .env $(APP_NAME):latest
```

### 8.5 go.mod 模板

```
module tokenmarket/proxy-gateway

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/redis/go-redis/v9 v9.3.0
    github.com/segmentio/kafka-go v0.4.47
    github.com/spf13/viper v1.18.2
    golang.org/x/sync v0.6.0
)

require (
    github.com/bytedance/sonic v1.9.1 // indirect
    github.com/chenzhuoyu/base64x v0.0.0-20221115062448-fe3a3abad311 // indirect
    github.com/gabriel-vasile/mimetype v1.4.2 // indirect
    github.com/gin-contrib/sse v0.1.0 // indirect
    github.com/go-playground/locales v0.14.1 // indirect
    github.com/go-playground/universal-translator v0.18.1 // indirect
    github.com/go-playground/validator/v10 v10.14.0 // indirect
    github.com/goccy/go-json v0.10.2 // indirect
    github.com/json-iterator/go v1.1.12 // indirect
    github.com/klauspost/cpuid/v2 v2.2.4 // indirect
    github.com/leodido/go-urn v1.2.4 // indirect
    github.com/mattn/go-isatty v0.0.19 // indirect
    github.com/modern-go/concurrent v0.0.0-20180306012644-bacd9c7ef1dd // indirect
    github.com/modern-go/reflect2 v1.0.2 // indirect
    github.com/pelletier/go-toml/v2 v2.0.8 // indirect
    github.com/twitchyliquid64/golang-asm v0.15.1 // indirect
    github.com/ugorji/go/codec v1.2.11 // indirect
    golang.org/x/arch v0.3.0 // indirect
    golang.org/x/crypto v0.9.0 // indirect
    golang.org/x/net v0.10.0 // indirect
    golang.org/x/sys v0.8.0 // indirect
    golang.org/x/text v0.9.0 // indirect
    google.golang.org/protobuf v1.30.0 // indirect
    gopkg.in/yaml.v3 v3.0.1 // indirect
)
```

---

## 附录

### A. 开发检查清单

- [ ] 新文件放置在正确的目录层级
- [ ] 领域模型不包含任何外部依赖
- [ ] 每个接口都有至少两个实现（真实 + mock）
- [ ] 每个 goroutine 有 defer recover()
- [ ] 每个 HTTP handler 使用 context.WithTimeout
- [ ] 新增平台适配器通过 Registry 注册
- [ ] 单元测试覆盖率 ≥ 70%
- [ ] 错误使用 error wrapping 保留原始错误链
- [ ] 并发访问使用适当的同步原语
- [ ] 代码通过 golangci-lint 检查

### B. 提交信息规范

```
feat: 新增火山方舟平台适配器
fix: 修复路由引擎并发安全问题
test: 补充 KeyPool 单元测试
refactor: 重构 Pipeline 阶段接口
docs: 更新 API 文档
deploy: 更新 Docker 配置
```

### C. 版本号规范

遵循 [SemVer](https://semver.org/)：

```
MAJOR.MINOR.PATCH
0.1.0    # 初始版本
0.1.1    # Bug 修复
0.2.0    # 新增功能（如新增平台适配器）
1.0.0    # 正式生产版本
```

---

> 本文档为 TokenMarket Go 代理网关开发的核心规范，所有代码提交前必须对照检查。
> 规范随项目演进持续更新，当前版本适用于 V0.1-0.2 快速原型阶段。
