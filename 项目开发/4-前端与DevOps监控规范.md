# TokenMarket 前端与 DevOps 监控规范

> **适用范围**：V0.1–V0.2 快速原型阶段
>
> **目标**：为单人兼职开发提供一套"够用、可执行、低维护"的前端与 DevOps 规范，兼顾开发效率与基础可观测性。

---

## 1. React 前端项目目录结构

```
frontend/
├── public/                          # 静态资源（不经过构建）
│   └── favicon.ico
│
├── src/
│   ├── main.tsx                     # 应用入口
│   ├── App.tsx                      # 路由配置 + 全局 Provider 挂载
│   │
│   ├── api/                         # API 客户端封装
│   │   ├── client.ts                # axios / fetch 统一实例
│   │   ├── interceptors.ts          # 请求/响应拦截器
│   │   ├── types.ts                 # API 通用类型（ApiResponse、ApiError）
│   │   └── v1/                      # 按版本组织 API
│   │       ├── auth.ts              # 登录/注册/Token 刷新
│   │       ├── keys.ts              # Key 创建/查询/续期
│   │       ├── billing.ts           # 充值/扣费/账单
│   │       ├── orders.ts            # 撮合/订单/状态
│   │       ├── admin.ts             # 管理后台接口
│   │       └── index.ts             # v1 API 统一导出
│   │
│   ├── components/                  # 通用组件
│   │   ├── common/                  # 纯展示组件（零业务逻辑）
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Select.tsx
│   │   │   ├── Table.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Skeleton.tsx
│   │   │   └── index.ts             # 统一导出
│   │   │
│   │   └── business/                # 业务组件（含业务逻辑）
│   │       ├── KeyCard.tsx          # Key 卡片展示
│   │       ├── BalancePanel.tsx     # 余额面板
│   │       ├── OrderItem.tsx        # 订单列表项
│   │       ├── PlatformStatus.tsx   # 平台可用状态
│   │       ├── UsageChart.tsx       # 用量图表
│   │       └── index.ts
│   │
│   ├── pages/                       # 页面级组件
│   │   ├── seller/                  # 卖家端页面
│   │   │   ├── Dashboard.tsx        # 卖家工作台
│   │   │   ├── Keys.tsx             # 我的 Key 列表
│   │   │   ├── KeyCreate.tsx        # 创建 Key
│   │   │   ├── Billing.tsx          # 账单/收入
│   │   │   └── index.ts
│   │   │
│   │   ├── buyer/                   # 买家端页面
│   │   │   ├── Dashboard.tsx        # 买家工作台
│   │   │   ├── Marketplace.tsx      # 额度市场
│   │   │   ├── MyKeys.tsx           # 已购 Key 列表
│   │   │   ├── Orders.tsx           # 订单管理
│   │   │   └── index.ts
│   │   │
│   │   ├── admin/                   # 管理后台页面
│   │   │   ├── Dashboard.tsx        # 运营总览
│   │   │   ├── Users.tsx            # 用户管理
│   │   │   ├── Keys.tsx             # Key 管理
│   │   │   ├── Orders.tsx           # 订单管理
│   │   │   ├── Billing.tsx          # 财务/对账
│   │   │   └── index.ts
│   │   │
│   │   ├── Login.tsx                # 统一登录页
│   │   ├── Register.tsx             # 注册页
│   │   └── NotFound.tsx             # 404
│   │
│   ├── hooks/                       # 自定义 React Hooks
│   │   ├── useAuth.ts               # 认证状态 + 登录/登出
│   │   ├── useBalance.ts            # 余额查询 + 自动刷新
│   │   ├── useKeyList.ts            # Key 列表 + 分页
│   │   ├── useOrder.ts              # 订单状态管理
│   │   ├── usePolling.ts            # 通用轮询 Hook
│   │   ├── useLocalStorage.ts       # localStorage 同步
│   │   └── index.ts
│   │
│   ├── stores/                      # 全局状态管理（Zustand）
│   │   ├── authStore.ts             # 用户信息 + Token
│   │   ├── balanceStore.ts          # 余额 + 变动通知
│   │   ├── notificationStore.ts     # 全局消息通知
│   │   ├── uiStore.ts               # UI 状态（侧边栏折叠、主题）
│   │   └── index.ts
│   │
│   ├── types/                       # TypeScript 类型定义
│   │   ├── auth.ts                  # 用户/角色/权限
│   │   ├── key.ts                   # Key 相关类型
│   │   ├── order.ts                 # 订单/撮合类型
│   │   ├── billing.ts               # 账单/财务类型
│   │   ├── platform.ts              # AI 平台枚举
│   │   └── index.ts
│   │
│   ├── utils/                       # 工具函数
│   │   ├── formatters.ts            # 金额/时间格式化
│   │   ├── validators.ts            # 表单验证
│   │   ├── crypto.ts                # 前端加解密辅助
│   │   ├── retry.ts                 # 重试逻辑
│   │   └── index.ts
│   │
│   └── styles/                      # 全局样式 + Tailwind 配置
│       ├── globals.css              # Tailwind 指令 + 全局覆盖
│       ├── variables.css            # CSS 变量（主题色）
│       └── tailwind.config.js       # Tailwind 扩展配置
│
├── index.html
├── package.json
├── vite.config.ts                   # Vite 构建配置
├── tsconfig.json                    # TypeScript 配置
├── tsconfig.node.json               # Vite 等 Node 工具类型
├── tailwind.config.js               # Tailwind 入口配置
├── postcss.config.js
├── .eslintrc.cjs                    # ESLint 规则
├── .prettierrc                      # Prettier 格式化
├── .env.development                 # 开发环境变量
├── .env.test                        # 测试环境变量
├── .env.production                  # 生产环境变量
├── Dockerfile                       # 前端构建镜像
└── nginx.conf                       # Nginx 静态服务配置
```

---

## 2. 前端开发规范

### 2.1 TypeScript 严格模式

**tsconfig.json 核心配置**：

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"],
      "@components/*": ["src/components/*"],
      "@hooks/*": ["src/hooks/*"],
      "@stores/*": ["src/stores/*"],
      "@types/*": ["src/types/*"],
      "@utils/*": ["src/utils/*"],
      "@api/*": ["src/api/*"]
    }
  },
  "include": ["src/**/*.ts", "src/**/*.tsx"],
  "exclude": ["node_modules", "dist"]
}
```

**严格模式执行规则**：

| 规则 | 要求 | 违规示例 | 正确写法 |
|------|------|----------|----------|
| 禁止 `any` | 全部使用具体类型或 `unknown` | `const data: any = res.data` | `const data: unknown = res.data; if (isKeyList(data)) {...}` |
| 类型守卫 | `unknown` 必须经过收窄 | `data.keys.map(...)` | `if (hasKeys(data)) data.keys.map(...)` |
| API 响应对齐 | 必须与后端 Pydantic schema 1:1 | 前端 `price: string` 后端 `price: Decimal` | 统一 `price: string`（JSON 序列化） |
| 枚举严格 | 使用 `as const` 或 enum | `type Status = 'active' \| 'inactive'` | `const Status = { Active: 'active', ... } as const` |
| 空值检查 | 所有可能为 null/undefined 必须处理 | `user.name.toUpperCase()` | `user?.name?.toUpperCase() \|\| '匿名'` |

**API ↔ 后端类型映射示例**：

```typescript
// src/types/key.ts
// 对应后端: class KeyResponse(BaseModel)
export interface KeyResponse {
  id: string;                 // UUID → string
  platform: PlatformType;     // Literal['openai', 'anthropic', ...]
  provider_key: string;       // 脱敏展示用
  balance_credits: string;    // Decimal → string（避免精度丢失）
  original_credits: string;
  status: KeyStatus;          // 'active' | 'paused' | 'expired' | 'revoked'
  expires_at: string;         // datetime → ISO 8601 string
  created_at: string;
  updated_at: string;
}

// 类型守卫（必须手写，禁止 any）
export function isKeyResponse(obj: unknown): obj is KeyResponse {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'id' in obj &&
    'platform' in obj &&
    'balance_credits' in obj
  );
}
```

### 2.2 组件设计原则（SOLID 在前端）

**S - 单一职责**：每个组件只负责一个 UI 职责

```typescript
// ❌ 错误：一个组件做了太多事
function KeyCard({ keyData }: { keyData: Key }) {
  const [balance, setBalance] = useState(0);
  const [showModal, setShowModal] = useState(false);
  
  useEffect(() => { /* 获取余额 */ }, []);
  
  return (
    <div>
      <h3>{keyData.name}</h3>
      <p>余额: {balance}</p>
      {showModal && <Modal onClose={() => setShowModal(false)}> {/* 弹窗内容 */} </Modal>}
      <button onClick={() => setShowModal(true)}>充值</button>
      <button onClick={() => setShowModal(true)}>续期</button>
      <Chart data={keyData.usage} />  {/* 图表也塞进来了 */}
    </div>
  );
}

// ✅ 正确：拆分为职责单一的组件
// components/business/KeyCard.tsx —— 只负责"卡片展示"
function KeyCard({ keyData, onRecharge, onRenew }: KeyCardProps) {
  return (
    <Card>
      <KeyHeader name={keyData.name} platform={keyData.platform} />
      <KeyBalance balance={keyData.balance_credits} />
      <KeyActions onRecharge={onRecharge} onRenew={onRenew} />
    </Card>
  );
}

// hooks/useBalance.ts —— 余额逻辑抽离
export function useBalance(keyId: string) {
  return useQuery({
    queryKey: ['balance', keyId],
    queryFn: () => api.v1.keys.getBalance(keyId),
    refetchInterval: 30000, // 30s 自动刷新
  });
}
```

**O - 开闭原则**：通过 props / 插槽扩展，不修改组件内部

```typescript
// ✅ 正确：通过 render props / slots 扩展
interface TableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  renderEmpty?: React.ReactNode;     // 空状态插槽
  renderLoading?: React.ReactNode;   // 加载状态插槽
  onRowClick?: (row: T) => void;     // 可选行为注入
}

// 使用时扩展，不改源码
<KeyTable
  data={keys}
  columns={keyColumns}
  renderEmpty={<EmptyState icon="🔑" message="暂无 Key" />}
  renderLoading={<Skeleton rows={5} />}
/>
```

**容器组件 vs 展示组件分离**：

| 类型 | 职责 | 数据来源 | 示例 |
|------|------|----------|------|
| 容器组件 | 取数据、调 API、状态管理 | Hooks / Store | `KeyListContainer` |
| 展示组件 | 接收 props，纯渲染 | 仅 props | `KeyCard`、`BalanceDisplay` |

```typescript
// 容器组件：pages/seller/Keys.tsx
export function SellerKeysPage() {
  const { data: keys, isLoading } = useKeyList();
  const createMutation = useKeyCreate();
  
  return (
    <PageLayout title="我的 Key">
      <KeyToolbar onCreate={() => createMutation.mutate()} />
      <KeyList 
        keys={keys || []} 
        loading={isLoading}
        onRefresh={refetch}
      />
    </PageLayout>
  );
}

// 展示组件：components/business/KeyList.tsx
export function KeyList({ keys, loading, onRefresh }: KeyListProps) {
  if (loading) return <Skeleton rows={5} />;
  return (
    <div className="grid gap-4">
      {keys.map(key => <KeyCard key={key.id} keyData={key} />)}
    </div>
  );
}
```

### 2.3 状态管理规范

**三层状态分离**：

```
┌─────────────────────────────────────────────────────────────┐
│  全局状态 (Zustand)                                          │
│  ├── 用户信息 (authStore) —— 登录后全生命周期存在               │
│  ├── 余额通知 (balanceStore) —— 跨页面共享的余额变动            │
│  ├── 全局通知 (notificationStore) —— Toast / 消息             │
│  └── UI 状态 (uiStore) —— 侧边栏、主题、弹窗堆栈               │
├─────────────────────────────────────────────────────────────┤
│  服务端状态 (React Query / TanStack Query)                    │
│  ├── Key 列表 —— 自动缓存、失效、后台刷新                      │
│  ├── 订单状态 —— 轮询更新                                      │
│  └── 账单记录 —— 分页 + 预加载                                 │
├─────────────────────────────────────────────────────────────┤
│  本地状态 (useState / useReducer)                             │
│  ├── 表单输入值 —— 不上报全局                                   │
│  ├── 弹窗开关 —— 局部作用域                                    │
│  └── 临时筛选条件 —— 页面级                                   │
└─────────────────────────────────────────────────────────────┘
```

**Zustand Store 规范**：

```typescript
// stores/authStore.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  
  // Actions
  setUser: (user: User) => void;
  setToken: (token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      
      setUser: (user) => set({ user, isAuthenticated: true }),
      setToken: (token) => set({ token }),
      logout: () => set({ user: null, token: null, isAuthenticated: false }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }), // 只持久化 token
    }
  )
);

// ⚠️ 禁止使用：在组件外直接调用 getState() 修改状态
// ✅ 正确：在 hook / 事件回调中通过 actions 修改
```

**React Query 规范**：

```typescript
// hooks/useKeyList.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export function useKeyList(params?: KeyListParams) {
  return useQuery({
    queryKey: ['keys', params],           // 缓存 key，参数变化自动重新请求
    queryFn: () => api.v1.keys.list(params),
    staleTime: 1000 * 30,                 // 30s 内视为新鲜，不重复请求
    gcTime: 1000 * 60 * 5,                // 5min 缓存保留
    refetchOnWindowFocus: true,           // 切回页面自动刷新
  });
}

export function useKeyCreate() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.v1.keys.create,
    onSuccess: () => {
      // 创建成功后，使 keys 列表缓存失效，自动重新获取
      queryClient.invalidateQueries({ queryKey: ['keys'] });
      notificationStore.getState().success('Key 创建成功');
    },
    onError: (error: ApiError) => {
      notificationStore.getState().error(error.message || '创建失败');
    },
  });
}
```

### 2.4 API 调用规范

**统一 Client 实例**：

```typescript
// api/client.ts
import axios, { AxiosInstance, AxiosError } from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const client: AxiosInstance = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// 请求拦截器：自动附加 token + request-id
client.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // 生成唯一请求 ID（用于全链路追踪）
    config.headers['X-Request-ID'] = crypto.randomUUID();
    return config;
  },
  (error) => Promise.reject(error)
);
```

**响应拦截器（全局错误处理）**：

```typescript
// api/interceptors.ts
client.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    const requestId = error.config?.headers?.['X-Request-ID'];
    
    if (error.response) {
      switch (error.response.status) {
        case 401:
          // Token 过期，清除认证状态并跳转登录
          useAuthStore.getState().logout();
          window.location.href = '/login?expired=true';
          break;
          
        case 403:
          notificationStore.getState().error('权限不足，请联系管理员');
          break;
          
        case 429:
          notificationStore.getState().warning('请求过于频繁，请稍后再试');
          break;
          
        case 500:
        case 502:
        case 503:
          notificationStore.getState().error(
            `服务暂时不可用 (Request ID: ${requestId})`
          );
          break;
          
        default:
          notificationStore.getState().error(
            error.response.data?.message || '请求失败'
          );
      }
    } else if (error.request) {
      notificationStore.getState().error('网络异常，请检查连接');
    }
    
    return Promise.reject(error);
  }
);
```

**请求去重（300ms 内同一请求不重复发送）**：

```typescript
// api/client.ts —— 在 client 中集成
const pendingRequests = new Map<string, AbortController>();

function generateRequestKey(config: AxiosRequestConfig): string {
  return `${config.method}-${config.url}-${JSON.stringify(config.params || {})}-${JSON.stringify(config.data || {})}`;
}

client.interceptors.request.use((config) => {
  const key = generateRequestKey(config);
  
  // 如果 300ms 内有相同请求，取消前一个
  if (pendingRequests.has(key)) {
    pendingRequests.get(key)?.abort();
  }
  
  const controller = new AbortController();
  config.signal = controller.signal;
  pendingRequests.set(key, controller);
  
  setTimeout(() => pendingRequests.delete(key), 300);
  
  return config;
});
```

**错误边界**：

```typescript
// components/common/ErrorBoundary.tsx
import { Component, ErrorInfo, ReactNode } from 'react';

interface Props { children: ReactNode; fallback?: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };
  
  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }
  
  componentDidCatch(error: Error, info: ErrorInfo) {
    // 生产环境上报 Sentry
    if (import.meta.env.PROD) {
      console.error('ErrorBoundary caught:', error, info);
    }
  }
  
  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="p-8 text-center">
          <h2 className="text-xl font-bold text-red-600">页面出现错误</h2>
          <p className="mt-2 text-gray-600">
            Request ID: {crypto.randomUUID()}
          </p>
          <button 
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded"
            onClick={() => window.location.reload()}
          >
            刷新页面
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// App.tsx —— 每个路由包裹 ErrorBoundary
<ErrorBoundary>
  <SellerDashboard />
</ErrorBoundary>
```

---

## 3. Docker 部署规范

### 3.1 本地开发 docker-compose.dev.yml

```yaml
# docker-compose.dev.yml
# 用途：本地开发只启动中间件，前后端用本地进程（热更新更快）
version: "3.8"

services:
  # PostgreSQL 15 —— 主数据库
  postgres:
    image: postgres:15-alpine
    container_name: tm-postgres
    environment:
      POSTGRES_USER: tokenmarket
      POSTGRES_PASSWORD: dev_password
      POSTGRES_DB: tokenmarket
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tokenmarket"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - tokenmarket-dev

  # Redis 7 —— 缓存 + 分布式锁
  redis:
    image: redis:7-alpine
    container_name: tm-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - tokenmarket-dev

  # Redpanda —— Kafka 兼容的消息队列（比 Kafka 轻量）
  redpanda:
    image: redpandadata/redpanda:latest
    container_name: tm-redpanda
    ports:
      - "9092:9092"      # Kafka API
      - "9644:9644"      # Admin API
      - "8082:8082"      # Pandaproxy (REST)
    volumes:
      - redpanda_data:/var/lib/redpanda/data
    command:
      - redpanda
      - start
      - --smp 1
      - --memory 1G
      - --reserve-memory 0M
      - --overprovisioned
      - --node-id 0
      - --check=false
      - --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:9092
      - --advertise-kafka-addr internal://redpanda:9092,external://localhost:9092
    networks:
      - tokenmarket-dev

  # Prometheus —— 指标采集
  prometheus:
    image: prom/prometheus:latest
    container_name: tm-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    networks:
      - tokenmarket-dev

  # Grafana —— 可视化面板
  grafana:
    image: grafana/grafana:latest
    container_name: tm-grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_INSTALL_PLUGINS: grafana-lokiexplore-app
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    depends_on:
      - prometheus
    networks:
      - tokenmarket-dev

  # Loki —— 日志聚合
  loki:
    image: grafana/loki:latest
    container_name: tm-loki
    ports:
      - "3100:3100"
    volumes:
      - ./monitoring/loki.yml:/etc/loki/local-config.yaml
      - loki_data:/loki
    command: -config.file=/etc/loki/local-config.yaml
    networks:
      - tokenmarket-dev

  # 可选：MinIO —— 对象存储
  minio:
    image: minio/minio:latest
    container_name: tm-minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    networks:
      - tokenmarket-dev

volumes:
  postgres_data:
  redis_data:
  redpanda_data:
  prometheus_data:
  grafana_data:
  loki_data:
  minio_data:

networks:
  tokenmarket-dev:
    driver: bridge
```

### 3.2 测试/生产 docker-compose.yml

```yaml
# docker-compose.yml
# 用途：测试/生产环境，所有服务容器化
version: "3.8"

services:
  # Nginx —— 反向代理 + 静态文件
  nginx:
    image: nginx:alpine
    container_name: tm-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./frontend/dist:/usr/share/nginx/html:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - proxy-gateway
      - api-service
    restart: unless-stopped
    networks:
      - tokenmarket

  # Go 代理网关
  proxy-gateway:
    image: tokenmarket/proxy-gateway:${VERSION:-latest}
    container_name: tm-proxy
    ports:
      - "8080:8080"
    environment:
      - TM_ENV=${TM_ENV:-production}
      - TM_DB_HOST=postgres
      - TM_DB_PORT=5432
      - TM_REDIS_HOST=redis
      - TM_KAFKA_BROKERS=redpanda:9092
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - tokenmarket

  # Python API 服务
  api-service:
    image: tokenmarket/api-service:${VERSION:-latest}
    container_name: tm-api
    ports:
      - "8000:8000"
    environment:
      - TM_ENV=${TM_ENV:-production}
      - TM_DB_HOST=postgres
      - TM_REDIS_HOST=redis
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - tokenmarket

  # Python 计费服务
  billing-service:
    image: tokenmarket/billing-service:${VERSION:-latest}
    container_name: tm-billing
    environment:
      - TM_ENV=${TM_ENV:-production}
      - TM_DB_HOST=postgres
      - TM_REDIS_HOST=redis
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - tokenmarket

  # Python 管理后台服务
  admin-service:
    image: tokenmarket/admin-service:${VERSION:-latest}
    container_name: tm-admin
    environment:
      - TM_ENV=${TM_ENV:-production}
      - TM_DB_HOST=postgres
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - tokenmarket

  # 数据库
  postgres:
    image: postgres:15-alpine
    container_name: tm-postgres
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - postgres_prod:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - tokenmarket

  redis:
    image: redis:7-alpine
    container_name: tm-redis
    volumes:
      - redis_prod:/data
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - tokenmarket

  redpanda:
    image: redpandadata/redpanda:latest
    container_name: tm-redpanda
    volumes:
      - redpanda_prod:/var/lib/redpanda/data
    command:
      - redpanda
      - start
      - --smp 1
      - --memory 1G
      - --reserve-memory 0M
      - --overprovisioned
      - --node-id 0
      - --check=false
      - --kafka-addr internal://0.0.0.0:9092
      - --advertise-kafka-addr internal://redpanda:9092
    restart: unless-stopped
    networks:
      - tokenmarket

  prometheus:
    image: prom/prometheus:latest
    container_name: tm-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_prod:/prometheus
    restart: unless-stopped
    networks:
      - tokenmarket

  grafana:
    image: grafana/grafana:latest
    container_name: tm-grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_USER: ${GRAFANA_USER:-admin}
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
    volumes:
      - grafana_prod:/var/lib/grafana
    restart: unless-stopped
    networks:
      - tokenmarket

volumes:
  postgres_prod:
  redis_prod:
  redpanda_prod:
  prometheus_prod:
  grafana_prod:

networks:
  tokenmarket:
    driver: bridge
```

### 3.3 Dockerfile 编写规范

**前端 Dockerfile**：

```dockerfile
# frontend/Dockerfile
# 多阶段构建：builder → runner（Nginx 静态服务）

# ========== Stage 1: Builder ==========
FROM node:20-alpine AS builder

WORKDIR /app

# 先复制依赖文件，利用缓存层
COPY package.json package-lock.json* pnpm-lock.yaml* ./

# 安装依赖（使用 lock 文件保证一致性）
RUN if [ -f pnpm-lock.yaml ]; then \
      npm install -g pnpm && pnpm install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
      npm ci; \
    else \
      npm install; \
    fi

# 复制源码
COPY . .

# 构建生产包
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# ========== Stage 2: Runner ==========
FROM nginx:alpine AS runner

# 非 root 用户运行
RUN addgroup -g 1001 -S nodejs && \
    adduser -S nextjs -u 1001

# 复制构建产物
COPY --from=builder --chown=nextjs:nodejs /app/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1

USER nextjs

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

**Go 代理网关 Dockerfile**：

```dockerfile
# proxy-gateway/Dockerfile
# 多阶段构建：builder → runner

# ========== Stage 1: Builder ==========
FROM golang:1.22-alpine AS builder

WORKDIR /build

# 安装构建依赖
RUN apk add --no-cache git ca-certificates tzdata

# 复制依赖文件
COPY go.mod go.sum ./
RUN go mod download

# 复制源码
COPY . .

# 构建（静态链接，无 CGO）
ARG VERSION=dev
ARG GIT_SHA=unknown
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-w -s \
      -X main.Version=${VERSION} \
      -X main.GitSHA=${GIT_SHA} \
      -X main.BuildTime=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    -o /build/server \
    ./cmd/server

# ========== Stage 2: Runner ==========
FROM alpine:latest AS runner

# 安装运行时依赖
RUN apk --no-cache add ca-certificates tzdata

# 非 root 用户
RUN addgroup -g 1001 -S appgroup && \
    adduser -S appuser -u 1001 -G appgroup

WORKDIR /app

# 复制二进制文件
COPY --from=builder /build/server /app/server

# 健康检查
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -q --spider http://localhost:8080/health || exit 1

USER appuser

EXPOSE 8080

ENTRYPOINT ["/app/server"]
```

**Python 服务 Dockerfile**：

```dockerfile
# api-service/Dockerfile
# 多阶段构建：builder → runner

# ========== Stage 1: Builder ==========
FROM python:3.11-slim AS builder

WORKDIR /build

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 创建虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ========== Stage 2: Runner ==========
FROM python:3.11-slim AS runner

WORKDIR /app

# 安装运行时依赖（无编译工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 非 root 用户
RUN groupadd -r appgroup --gid=1001 && \
    useradd -r -g appgroup --uid=1001 appuser

# 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制应用代码
COPY ./app ./app
COPY ./alembic ./alembic
COPY alembic.ini .

# 健康检查
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**镜像标签规范**：

```bash
# 标签格式：{service}:{version}-{git_sha}
# 示例：
#   tokenmarket/proxy-gateway:v0.1.0-a1b2c3d
#   tokenmarket/api-service:v0.1.0-a1b2c3d
#   tokenmarket/frontend:v0.1.0-a1b2c3d

VERSION=$(git describe --tags --always)
GIT_SHA=$(git rev-parse --short HEAD)
IMAGE_TAG="${VERSION}-${GIT_SHA}"

docker build \
  --build-arg VERSION=${VERSION} \
  --build-arg GIT_SHA=${GIT_SHA} \
  -t tokenmarket/proxy-gateway:${IMAGE_TAG} \
  -t tokenmarket/proxy-gateway:latest \
  ./proxy-gateway
```

---

## 4. Makefile 命令规范

```makefile
# TokenMarket —— 全项目 Makefile
# 使用方法：在项目根目录执行 make <target>

# ========== 变量定义 ==========
VERSION := $(shell git describe --tags --always 2>/dev/null || echo "dev")
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
COMPOSE_DEV := docker-compose -f docker-compose.dev.yml
COMPOSE_TEST := docker-compose -f docker-compose.test.yml
COMPOSE_PROD := docker-compose -f docker-compose.yml

# 颜色输出
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m

.PHONY: help dev dev-down dev-logs test-up test-down deploy-prod migrate \
        test lint fmt build push logs status clean

# ========== 帮助 ==========
help: ## 显示所有可用命令
	@echo "$(BLUE)TokenMarket 开发命令$(NC)"
	@echo "========================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

# ========== 本地开发 ==========
dev: ## 启动中间件服务（PostgreSQL/Redis/Kafka/Grafana）
	@echo "$(BLUE)启动开发环境中间件...$(NC)"
	$(COMPOSE_DEV) up -d
	@echo "$(GREEN)中间件已启动$(NC)"
	@echo "  PostgreSQL: localhost:5432"
	@echo "  Redis:      localhost:6379"
	@echo "  Grafana:    http://localhost:3000"
	@echo "  Prometheus: http://localhost:9090"
	@echo ""
	@echo "$(YELLOW)提示：前后端请手动启动（热更新更快）$(NC)"
	@echo "  前端: cd frontend && npm run dev"
	@echo "  后端: cd api-service && uvicorn app.main:app --reload"

dev-down: ## 停止开发环境中间件
	@echo "$(BLUE)停止开发环境中间件...$(NC)"
	$(COMPOSE_DEV) down
	@echo "$(GREEN)中间件已停止$(NC)"

dev-logs: ## 查看中间件日志
	$(COMPOSE_DEV) logs -f

dev-clean: ## 清理开发环境数据卷（⚠️ 数据丢失）
	@echo "$(RED)警告：这将删除所有开发数据！$(NC)"
	@read -p "确认删除? [y/N] " confirm && \
		[ "$$confirm" = "y" ] && $(COMPOSE_DEV) down -v || echo "已取消"

# ========== 测试环境 ==========
test-up: ## 启动测试环境（全部容器化）
	@echo "$(BLUE)启动测试环境...$(NC)"
	$(COMPOSE_TEST) up -d --build
	@echo "$(GREEN)测试环境已启动$(NC)"

test-down: ## 停止测试环境
	@echo "$(BLUE)停止测试环境...$(NC)"
	$(COMPOSE_TEST) down
	@echo "$(GREEN)测试环境已停止$(NC)"

test-logs: ## 查看测试环境日志
	$(COMPOSE_TEST) logs -f

# ========== 生产部署 ==========
build: ## 构建所有服务镜像
	@echo "$(BLUE)构建镜像 (版本: $(VERSION)-$(GIT_SHA))...$(NC)"
	docker build \
		--build-arg VERSION=$(VERSION) \
		--build-arg GIT_SHA=$(GIT_SHA) \
		-t tokenmarket/proxy-gateway:$(VERSION)-$(GIT_SHA) \
		-t tokenmarket/proxy-gateway:latest \
		./proxy-gateway
	docker build \
		-t tokenmarket/api-service:$(VERSION)-$(GIT_SHA) \
		-t tokenmarket/api-service:latest \
		./api-service
	docker build \
		--build-arg VITE_API_BASE_URL=$(VITE_API_BASE_URL) \
		-t tokenmarket/frontend:$(VERSION)-$(GIT_SHA) \
		-t tokenmarket/frontend:latest \
		./frontend
	@echo "$(GREEN)镜像构建完成$(NC)"

push: build ## 推送镜像到仓库（需要先 docker login）
	@echo "$(BLUE)推送镜像...$(NC)"
	docker push tokenmarket/proxy-gateway:$(VERSION)-$(GIT_SHA)
	docker push tokenmarket/proxy-gateway:latest
	docker push tokenmarket/api-service:$(VERSION)-$(GIT_SHA)
	docker push tokenmarket/api-service:latest
	docker push tokenmarket/frontend:$(VERSION)-$(GIT_SHA)
	docker push tokenmarket/frontend:latest
	@echo "$(GREEN)镜像推送完成$(NC)"

deploy-prod: ## 生产部署（拉取最新镜像并重启）
	@echo "$(BLUE)开始生产部署...$(NC)"
	$(COMPOSE_PROD) pull
	$(COMPOSE_PROD) up -d --remove-orphans
	@echo "$(GREEN)生产部署完成$(NC)"

# ========== 数据库 ==========
migrate: ## 执行数据库迁移
	@echo "$(BLUE)执行数据库迁移...$(NC)"
	cd api-service && alembic upgrade head
	@echo "$(GREEN)迁移完成$(NC)"

migrate-down: ## 回滚最近一次迁移
	@echo "$(YELLOW)回滚最近一次迁移...$(NC)"
	cd api-service && alembic downgrade -1
	@echo "$(GREEN)回滚完成$(NC)"

migrate-create: ## 创建新迁移（需要 NAME 参数）
	@ ifndef NAME
		$(error "请提供迁移名称: make migrate-create NAME=add_user_table")
	@ endif
	cd api-service && alembic revision --autogenerate -m "$(NAME)"

# ========== 测试 ==========
test: ## 运行全部测试
	@echo "$(BLUE)运行测试...$(NC)"
	cd proxy-gateway && go test ./... -v -race
	cd api-service && pytest -v --cov=app --cov-report=term-missing
	cd frontend && npm run test
	@echo "$(GREEN)测试完成$(NC)"

test-go: ## 仅运行 Go 测试
	cd proxy-gateway && go test ./... -v -race

test-py: ## 仅运行 Python 测试
	cd api-service && pytest -v --cov=app

test-fe: ## 仅运行前端测试
	cd frontend && npm run test

# ========== 代码质量 ==========
lint: ## 代码检查
	@echo "$(BLUE)运行代码检查...$(NC)"
	cd proxy-gateway && golangci-lint run ./...
	cd api-service && flake8 app tests && mypy app
	cd frontend && npm run lint
	@echo "$(GREEN)检查完成$(NC)"

fmt: ## 代码格式化
	@echo "$(BLUE)格式化代码...$(NC)"
	cd proxy-gateway && gofmt -w . && goimports -w .
	cd api-service && black app tests && isort app tests
	cd frontend && npm run format
	@echo "$(GREEN)格式化完成$(NC)"

# ========== 实用工具 ==========
logs: ## 查看生产环境日志
	$(COMPOSE_PROD) logs -f

status: ## 查看所有服务状态
	@echo "$(BLUE)服务状态$(NC)"
	@echo "========================"
	@$(COMPOSE_PROD) ps || $(COMPOSE_TEST) ps || $(COMPOSE_DEV) ps

clean: ## 清理构建产物、镜像、缓存
	@echo "$(BLUE)清理构建产物...$(NC)"
	docker system prune -f
	docker volume prune -f
	rm -rf frontend/dist
	rm -rf proxy-gateway/tmp
	@echo "$(GREEN)清理完成$(NC)"

# ========== 一键操作 ==========
all: dev ## 默认：启动开发环境
```

---

## 5. 日志与监控规范

### 5.1 日志管理架构

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  前端 Sentry │    │  Go 代理网关 │    │ Python 服务  │
│  (异常上报)  │    │  (JSON 日志) │    │ (JSON 日志)  │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                    │
       │                  ▼                    │
       │           ┌─────────────┐             │
       │           │ Promtail    │◄────────────┘
       │           │ (日志采集)   │
       │           └──────┬──────┘
       │                  │
       ▼                  ▼
┌─────────────────────────────────────┐
│              Loki                    │
│      (日志聚合 + 索引 + 查询)         │
│      标签: {service, level, trace_id} │
└─────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│            Grafana                   │
│   Dashboard: 日志查询 + 链路追踪      │
│   查询: {trace_id="xxx"} 关联全链路   │
└─────────────────────────────────────┘
```

### 5.2 各服务日志规范

**Go 代理网关 —— JSON 结构化日志**：

```go
// 每行一条 JSON，包含完整上下文
// 示例日志输出：
{
  "timestamp": "2025-01-15T09:23:45.123Z",
  "level": "INFO",
  "service": "proxy-gateway",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "request_id": "req-abc-123",
  "platform": "openai",
  "key_id": "key-xxx-456",
  "method": "POST",
  "path": "/v1/chat/completions",
  "latency_ms": 2345,
  "status_code": 200,
  "tokens_input": 150,
  "tokens_output": 320,
  "cost_credits": "150.50",
  "client_ip": "192.168.1.100",
  "user_agent": "python-requests/2.31.0"
}

// 错误日志示例：
{
  "timestamp": "2025-01-15T09:24:01.456Z",
  "level": "ERROR",
  "service": "proxy-gateway",
  "trace_id": "550e8400-e29b-41d4-a716-446655440001",
  "error": "rate_limit_exceeded",
  "error_detail": "OpenAI API rate limit hit: 60 requests/min",
  "platform": "openai",
  "key_id": "key-yyy-789",
  "latency_ms": 50,
  "status_code": 429,
  "stack": "..."
}
```

**Python 服务 —— structlog 输出 JSON**：

```python
# api-service/app/core/logging.py
import structlog
import logging

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
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

# 使用示例
logger = structlog.get_logger()

# 请求日志（中间件自动附加）
logger.info(
    "request_completed",
    request_id="req-abc-123",
    user_id="user-xxx",
    method="POST",
    path="/api/v1/keys",
    duration_ms=45.2,
    status_code=201,
)

# 业务日志
logger.info(
    "key_created",
    user_id="user-xxx",
    key_id="key-new-123",
    platform="anthropic",
    original_credits="10000",
)

# 错误日志
logger.error(
    "billing_mismatch_detected",
    user_id="user-yyy",
    order_id="order-zzz",
    expected_amount="150.50",
    actual_amount="150.00",
    difference="0.50",
    platform="openai",
)
```

**前端 —— 日志策略**：

```typescript
// utils/logger.ts
const isDev = import.meta.env.DEV;
const isProd = import.meta.env.PROD;

export const logger = {
  debug: (...args: unknown[]) => {
    if (isDev) console.debug('[DEBUG]', ...args);
  },
  info: (...args: unknown[]) => {
    if (isDev) console.info('[INFO]', ...args);
  },
  warn: (...args: unknown[]) => {
    if (isDev) console.warn('[WARN]', ...args);
    if (isProd) reportToSentry('warning', args);
  },
  error: (...args: unknown[]) => {
    if (isDev) console.error('[ERROR]', ...args);
    if (isProd) reportToSentry('error', args);
  },
};

// 生产环境上报 Sentry
function reportToSentry(level: 'warning' | 'error', args: unknown[]) {
  // Sentry.captureException / Sentry.captureMessage
}

// 全局错误捕获
window.addEventListener('error', (event) => {
  logger.error('Uncaught error:', event.error);
});

window.addEventListener('unhandledrejection', (event) => {
  logger.error('Unhandled promise rejection:', event.reason);
});
```

### 5.3 Grafana Dashboard 设计

#### Dashboard 1：系统总览（System Overview）

```yaml
Dashboard: TokenMarket - 系统总览
Refresh: 5s
Panels:
  - Panel: 实时 QPS
    Type: Stat
    Query: sum(rate(http_requests_total[1m]))
    
  - Panel: 平均延迟 / P99 延迟
    Type: Graph
    Query: 
      - avg(http_request_duration_seconds)
      - histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
    
  - Panel: 错误率
    Type: Graph
    Query: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])
    Threshold: > 1% 红色
    
  - Panel: 各平台可用 Key 数
    Type: Bar Gauge
    Query: key_pool_available{platform=~"openai|anthropic|google|deepseek"}
    Threshold: < 5 红色, < 10 黄色
    
  - Panel: 活跃连接数
    Type: Graph
    Query: proxy_active_connections
    
  - Panel: 近 1 小时请求趋势
    Type: Graph
    Query: sum(rate(http_requests_total[1m])) by (platform)
```

#### Dashboard 2：业务指标（Business Metrics）

```yaml
Dashboard: TokenMarket - 业务指标
Refresh: 30s
Panels:
  - Panel: GMV (今日/本周/本月)
    Type: Stat
    Query:
      - 今日: sum(order_amount{status="completed"}) > 0
      - 本周: sum(order_amount{status="completed"}) > 0
    
  - Panel: 活跃买家数 / 活跃卖家数
    Type: Graph
    Query:
      - buyers: count(count by (user_id) (buyer_activity[1d]))
      - sellers: count(count by (user_id) (seller_activity[1d]))
    
  - Panel: 撮合成功率
    Type: Gauge
    Query: sum(match_success) / sum(match_total) * 100
    Threshold: < 80% 红色, < 90% 黄色
    
  - Panel: 各平台收入占比
    Type: Pie Chart
    Query: sum(order_amount) by (platform)
    
  - Panel: Top 10 卖家收入
    Type: Table
    Query: topk(10, sum(seller_revenue) by (seller_id))
    
  - Panel: Key 到期预警
    Type: Table
    Query: key_expires_in_hours < 48
```

#### Dashboard 3：资源监控（Resource Monitor）

```yaml
Dashboard: TokenMarket - 资源监控
Refresh: 10s
Panels:
  - Panel: CPU 使用率（各服务）
    Type: Graph
    Query: rate(container_cpu_usage_seconds_total{name=~"tm-.*"}[1m])
    
  - Panel: 内存使用量
    Type: Graph
    Query: container_memory_usage_bytes{name=~"tm-.*"}
    
  - Panel: DB 连接数
    Type: Stat
    Query: pg_stat_activity_count
    Threshold: > 80 黄色, > 95 红色
    
  - Panel: Redis 内存使用
    Type: Graph
    Query: redis_memory_used_bytes
    
  - Panel: 磁盘使用率
    Type: Gauge
    Query: (node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes
    Threshold: > 80% 黄色, > 90% 红色
    
  - Panel: 网络 I/O
    Type: Graph
    Query: rate(container_network_receive_bytes_total[1m])
```

#### Dashboard 4：告警面板（Alert Status）

```yaml
Dashboard: TokenMarket - 告警面板
Refresh: 5s
Panels:
  - Panel: 活跃告警列表
    Type: Table
    Source: Alertmanager API
    Columns: [告警名, 级别, 服务, 开始时间, 摘要]
    
  - Panel: P0 告警计数
    Type: Stat
    Query: count(alertmanager_alerts{severity="p0"})
    Color: > 0 红色, = 0 绿色
    
  - Panel: P1 告警计数
    Type: Stat
    Query: count(alertmanager_alerts{severity="p1"})
    Color: > 0 橙色, = 0 绿色
    
  - Panel: 告警趋势（24h）
    Type: Graph
    Query: count(alertmanager_alerts) by (severity)
    
  - Panel: 异常交易列表
    Type: Table
    Query: billing_mismatch_count > 0 or key_revoked_count > 0
    
  - Panel: 服务可用性
    Type: Graph
    Query: up{job=~"proxy-gateway|api-service|billing-service"}
```

### 5.4 告警规则（Prometheus Alertmanager）

```yaml
# monitoring/prometheus/alert-rules.yml
groups:
  - name: tokenmarket-alerts
    rules:
      # ========== P0 告警 ==========
      - alert: ServiceDown
        expr: up{job=~"proxy-gateway|api-service|billing-service|admin-service"} == 0
        for: 1m
        labels:
          severity: p0
        annotations:
          summary: "服务 {{ $labels.job }} 不可用"
          description: "{{ $labels.instance }} 已连续 1 分钟无响应"
          
      - alert: KeyPoolLow
        expr: key_pool_available < 5
        for: 30s
        labels:
          severity: p0
        annotations:
          summary: "平台 {{ $labels.platform }} 可用 Key 不足"
          description: "当前可用 Key 数: {{ $value }}，低于阈值 5"
          
      - alert: BillingMismatch
        expr: billing_mismatch_total > 0
        for: 0s
        labels:
          severity: p0
        annotations:
          summary: "发现对账差异"
          description: "差异金额不为零，请立即核查"
          
      - alert: DatabaseConnectionExhausted
        expr: pg_stat_activity_count > 90
        for: 1m
        labels:
          severity: p0
        annotations:
          summary: "数据库连接数接近上限"
          description: "当前连接数: {{ $value }}"
          
      # ========== P1 告警 ==========
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 5m
        labels:
          severity: p1
        annotations:
          summary: "服务错误率过高"
          description: "{{ $labels.job }} 5xx 错误率: {{ $value | humanizePercentage }}"
          
      - alert: HighLatency
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 3
        for: 5m
        labels:
          severity: p1
        annotations:
          summary: "服务延迟过高"
          description: "P99 延迟: {{ $value }}s"
          
      - alert: HighCPUUsage
        expr: rate(container_cpu_usage_seconds_total{name=~"tm-.*"}[5m]) > 0.8
        for: 10m
        labels:
          severity: p1
        annotations:
          summary: "{{ $labels.name }} CPU 使用率过高"
          description: "CPU 使用率: {{ $value | humanizePercentage }}"
          
      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes{name=~"tm-.*"} / container_spec_memory_limit_bytes > 0.85
        for: 10m
        labels:
          severity: p1
        annotations:
          summary: "{{ $labels.name }} 内存使用率过高"
          description: "内存使用率: {{ $value | humanizePercentage }}"
          
      # ========== P2 告警（提醒） ==========
      - alert: KeyExpiringSoon
        expr: key_expires_in_hours < 48
        for: 1h
        labels:
          severity: p2
        annotations:
          summary: "Key 即将过期"
          description: "Key {{ $labels.key_id }} 将在 {{ $value }} 小时后过期"
          
      - alert: DiskSpaceLow
        expr: (node_filesystem_size_bytes - node_filesystem_avail_bytes) / node_filesystem_size_bytes > 0.8
        for: 5m
        labels:
          severity: p2
        annotations:
          summary: "磁盘空间不足"
          description: "使用率: {{ $value | humanizePercentage }}"
```

**Alertmanager 路由配置**：

```yaml
# monitoring/alertmanager.yml
global:
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alert@tokenmarket.io'
  smtp_auth_username: 'alert@tokenmarket.io'
  smtp_auth_password: '${SMTP_PASSWORD}'

templates:
  - '/etc/alertmanager/templates/*.tmpl'

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    # P0 告警：立即通知，邮件 + 微信
    - match:
        severity: p0
      receiver: 'p0-critical'
      group_wait: 0s
      repeat_interval: 15m
      
    # P1 告警：邮件通知
    - match:
        severity: p1
      receiver: 'p1-warning'
      group_wait: 30s
      repeat_interval: 1h
      
    # P2 告警：仅邮件，工作时间通知
    - match:
        severity: p2
      receiver: 'p2-notice'
      group_wait: 1m
      repeat_interval: 4h

receivers:
  - name: 'default'
    email_configs:
      - to: 'dev@tokenmarket.io'
        
  - name: 'p0-critical'
    email_configs:
      - to: 'dev@tokenmarket.io'
        headers:
          Subject: '[P0-紧急] {{ .GroupLabels.alertname }}'
    webhook_configs:
      - url: 'http://wechat-webhook:8080/send'
        send_resolved: true
        
  - name: 'p1-warning'
    email_configs:
      - to: 'dev@tokenmarket.io'
        headers:
          Subject: '[P1-警告] {{ .GroupLabels.alertname }}'
          
  - name: 'p2-notice'
    email_configs:
      - to: 'dev@tokenmarket.io'
        headers:
          Subject: '[P2-提醒] {{ .GroupLabels.alertname }}'

inhibit_rules:
  # 服务宕机时，抑制该服务的其他告警
  - source_match:
      severity: 'p0'
    target_match:
      severity: 'p1'
    equal: ['instance']
```

---

## 6. 开发管理 Excel 模板设计

### 6.1 开发任务跟踪表

| 任务ID | 模块 | 功能描述 | 优先级 | 预计工时(小时) | 实际工时(小时) | 状态 | 依赖任务 | 版本目标 | 完成日期 | 备注 |
|--------|------|----------|--------|----------------|----------------|------|----------|----------|----------|------|
| TM-001 | proxy-gateway | 搭建 Go 代理网关框架（HTTP 转发 + 中间件链） | P0 | 8 | 10 | 已完成 | — | V0.1 | 2025-01-10 | 比预计多2h，Go Context 传递踩坑 |
| TM-002 | api-service | 用户注册/登录 API（JWT + bcrypt） | P0 | 6 | 5 | 已完成 | TM-001 | V0.1 | 2025-01-11 | FastAPI 依赖注入很顺畅 |
| TM-003 | api-service | Key 创建与查询 API（CRUD + 脱敏） | P0 | 6 | 7 | 已完成 | TM-002 | V0.1 | 2025-01-12 | 脱敏逻辑需要前后对齐 |
| TM-004 | billing-service | 额度计算与扣费引擎（预扣 + 结算） | P0 | 10 | — | 进行中 | TM-003 | V0.1 | — | 需要等撮合逻辑完成 |
| TM-005 | frontend | 前端项目初始化（Vite + React + Tailwind） | P0 | 4 | 4 | 已完成 | — | V0.1 | 2025-01-10 | — |
| TM-006 | frontend | 登录/注册页面 + API 对接 | P0 | 6 | — | 待办 | TM-002,TM-005 | V0.1 | — | — |
| TM-007 | proxy-gateway | AI 平台请求转发与响应适配（OpenAI/Anthropic） | P0 | 12 | — | 待办 | TM-001 | V0.1 | — | 需要研究各平台 API 差异 |
| TM-008 | shared | Docker Compose 本地开发环境搭建 | P1 | 4 | 3 | 已完成 | — | V0.1 | 2025-01-09 | Redpanda 比 Kafka 轻量 |
| TM-009 | admin-service | 管理后台用户/Key/订单查询 API | P1 | 8 | — | 待办 | TM-003 | V0.2 | — | — |
| TM-010 | frontend | 卖家端 Dashboard 工作台 | P1 | 8 | — | 待办 | TM-006 | V0.2 | — | — |

### 6.2 Bug 跟踪表

| BugID | 所属模块 | 严重级别 | 标题 | 复现步骤 | 期望结果 | 实际结果 | 状态 | 发现日期 | 修复日期 | 回归次数 |
|-------|----------|----------|------|----------|----------|----------|------|----------|----------|----------|
| BUG-001 | proxy-gateway | P1 | 并发请求下 Key 额度超扣 | 1. 创建额度 100 的 Key<br>2. 同时发起 10 个请求各扣 20 | 前 5 个请求成功，后 5 个失败 | 10 个请求全部成功，额度变成 -100 | 已关闭 | 2025-01-13 | 2025-01-14 | 0 |
| BUG-002 | frontend | P2 | 登录页在移动端显示错位 | 1. 使用手机浏览器访问<br>2. 输入账号密码 | 表单居中，按钮正常显示 | 输入框超出屏幕，登录按钮被遮挡 | 已关闭 | 2025-01-14 | 2025-01-14 | 0 |
| BUG-003 | api-service | P0 | 数据库连接泄露导致服务不可用 | 1. 持续请求 API 1 小时<br>2. 观察 DB 连接数 | 连接数稳定在 20 以内 | 连接数持续增长至 100 上限，后续请求全部超时 | 修复中 | 2025-01-15 | — | — |
| BUG-004 | billing-service | P1 | 对账差异计算精度丢失 | 1. 创建订单金额 0.1<br>2. 完成扣费后查对账 | 对账差异为 0 | 差异显示为 1.110223e-16 | 待验证 | 2025-01-15 | 2025-01-15 | 0 |
| BUG-005 | shared | P3 | 开发环境日志输出未区分服务来源 | 1. 启动 docker-compose<br>2. 查看日志 | 日志前缀包含服务名 | 所有服务日志混在一起，无法区分 | 新建 | 2025-01-15 | — | — |

### 6.3 版本发布记录表

| 版本号 | 发布日期 | 变更列表 | 已知问题 | 回滚方案 | 发布人 |
|--------|----------|----------|----------|----------|--------|
| V0.1.0 | 2025-01-20 | TM-001, TM-002, TM-003, TM-005, TM-008 | 1. 仅支持 OpenAI 平台<br>2. 无支付功能，仅内部测试<br>3. 前端响应式未完全适配 | 执行 `make deploy-prod VERSION=V0.0.9` 回滚上一版本镜像 | token |
| V0.1.1 | 2025-01-27 | TM-004, TM-006, TM-007, BUG-001, BUG-002 | 1. 并发场景下偶现 500 错误（待排查）<br>2. 管理后台未上线 | 执行 `make deploy-prod VERSION=V0.1.0` 回滚 | token |
| V0.2.0 | 2025-02-10 | TM-009, TM-010, 新增 Anthropic/Google 支持 | 1. Google Gemini 流式响应偶现中断<br>2. 账单导出 Excel 格式待优化 | 执行 `make deploy-prod VERSION=V0.1.1` 回滚 | token |
| V0.2.1 | 2025-02-17 | BUG-003 修复（连接池优化）, BUG-004 修复（Decimal 精度） | 暂无 | 执行 `make deploy-prod VERSION=V0.2.0` 回滚 | token |
| — | — | — | — | — | — |

---

## 7. 环境变量模板

```bash
# ============================================================
# TokenMarket 环境变量模板 (.env.example)
# 使用方法：复制为 .env 并填入实际值
# ============================================================

# ========== 基础配置 ==========
# 运行环境: development | testing | production
TM_ENV=development

# 服务版本号（自动注入，无需手动修改）
TM_VERSION=dev

# 时区
TZ=Asia/Shanghai

# ========== 数据库 ==========
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_USER=tokenmarket
DB_PASSWORD=change_me_in_production
DB_NAME=tokenmarket
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# 数据库 URL（优先使用，若设置则覆盖上面分项）
# DATABASE_URL=postgresql://user:pass@host:port/db

# ========== Redis ==========
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# ========== Kafka / Redpanda ==========
KAFKA_BROKERS=localhost:9092
KAFKA_TOPIC_BILLING=billing-events
KAFKA_TOPIC_AUDIT=audit-logs
KAFKA_CONSUMER_GROUP=tokenmarket-group

# ========== JWT 认证 ==========
JWT_SECRET_KEY=change_this_to_a_32_char_random_string
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ========== API 配置 ==========
# Python FastAPI
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4
API_RELOAD=false

# Go 代理网关
PROXY_HOST=0.0.0.0
PROXY_PORT=8080
PROXY_WORKERS=0  # 0 = CPU 核心数

# ========== AI 平台 API Key（卖家池） ==========
# ⚠️ 生产环境使用 Secret Manager，不要直接写在这里
OPENAI_API_KEY_BASE=sk-proj-...
ANTHROPIC_API_KEY_BASE=sk-ant-...
GOOGLE_API_KEY_BASE=AIza...
DEEPSEEK_API_KEY_BASE=sk-...

# ========== 计费配置 ==========
# 最低充值金额（元）
MIN_RECHARGE_AMOUNT=10.00

# 平台手续费率（%）
PLATFORM_FEE_RATE=5.0

# 信用额度上限（新用户默认可欠费额度）
DEFAULT_CREDIT_LIMIT=0.00

# ========== 前端配置 ==========
# 构建时注入
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
VITE_SENTRY_DSN=  # 生产环境填写 Sentry DSN

# ========== 监控与日志 ==========
# Prometheus
PROMETHEUS_PORT=9090

# Grafana
GRAFANA_USER=admin
GRAFANA_PASSWORD=change_me_in_production

# Loki
LOKI_URL=http://localhost:3100

# Sentry（前端错误上报）
SENTRY_DSN=
SENTRY_ENVIRONMENT=development

# ========== 邮件通知 ==========
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=noreply@tokenmarket.io
SMTP_PASSWORD=
SMTP_TLS=true

# 告警通知邮箱
ALERT_EMAIL=dev@tokenmarket.io

# 微信 Webhook（用于 P0 告警）
WECHAT_WEBHOOK_URL=

# ========== 对象存储（可选） ==========
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=tokenmarket
MINIO_USE_SSL=false

# ========== 开发专用 ==========
# 是否开启 SQL 日志打印
SQL_ECHO=false

# 是否开启详细请求日志
DEBUG_REQUEST_LOG=true

# Mock 数据模式（前端开发用）
VITE_MOCK_API=false
```

---

## 附录：快速参考卡

### 常用命令速查

```bash
# 开发
make dev              # 启动中间件
make dev-down         # 停止中间件
cd frontend && npm run dev      # 启动前端
cd api-service && uvicorn app.main:app --reload   # 启动后端

# 部署
make build            # 构建镜像
make deploy-prod      # 生产部署
make test-up          # 启动测试环境

# 数据库
make migrate          # 执行迁移
make migrate-down     # 回滚
make migrate-create NAME=xxx   # 创建新迁移

# 质量
make test             # 运行全部测试
make lint             # 代码检查
make fmt              # 格式化

# 监控
docker logs -f tm-prometheus    # Prometheus 日志
docker logs -f tm-grafana       # Grafana 日志
```

### 端口映射参考

| 服务 | 开发端口 | 说明 |
|------|----------|------|
| PostgreSQL | 5432 | 主数据库 |
| Redis | 6379 | 缓存/队列 |
| Redpanda | 9092 | 消息队列 |
| API 服务 | 8000 | Python FastAPI |
| 代理网关 | 8080 | Go 网关 |
| Grafana | 3000 | 监控面板 |
| Prometheus | 9090 | 指标采集 |
| Loki | 3100 | 日志聚合 |
| MinIO | 9000/9001 | 对象存储 |

---

> **文档版本**: V1.0
> **最后更新**: 2025-01
> **适用范围**: TokenMarket V0.1-V0.2 快速原型阶段
