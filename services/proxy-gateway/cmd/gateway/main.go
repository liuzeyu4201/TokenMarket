package main

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keyhealth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/passthrough"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/runtimesnap"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/apisvc"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func main() {
	logger := observability.NewLogger()

	cfg, err := providervalid.LoadConfigFromEnv()
	if err != nil {
		logger.Error("invalid provider validate config", "error", err)
		os.Exit(1)
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	publicAddr := providervalid.PublicListenAddr(port)

	var validateDeps *httpserver.ValidateDeps
	if cfg.InternalEnabled {
		v := application.NewValidator(cfg)
		v.Logger = logger
		validateDeps = &httpserver.ValidateDeps{
			Enabled:   true,
			Token:     cfg.InternalToken,
			Validator: v,
		}
	}

	isolate := cfg.MustIsolateInternalListener()
	mountOnPublic := cfg.InternalEnabled && !isolate

	chatCfg, err := chatcompat.LoadConfigFromEnv()
	if err != nil {
		logger.Error("invalid chat adapter config", "error", err)
		os.Exit(1)
	}
	chat := application.NewChatService(chatCfg)
	chat.Logger = logger

	pepper, err := proxyauth.LoadSharedSecret(os.Getenv("PROXY_AUTH_PEPPER"))
	if err != nil {
		logger.Error("PROXY_AUTH_PEPPER rejected", "error", err)
		os.Exit(1)
	}
	staticAuth := proxyauth.MapStore{Records: parseProxyAuthEnv(pepper, os.Getenv("PROXY_STATIC_PROXY_KEYS"))}
	apiClient := apisvc.New(os.Getenv("API_INTERNAL_BASE_URL"), os.Getenv("INTERNAL_GATEWAY_TOKEN"))
	var authStore proxyauth.Store = staticAuth
	if strings.TrimSpace(os.Getenv("API_INTERNAL_BASE_URL")) != "" && strings.TrimSpace(os.Getenv("INTERNAL_GATEWAY_TOKEN")) != "" {
		authStore = apisvc.CompositeStore{Static: staticAuth, Remote: apiClient}
	}
	authLimiter := proxyauth.NewAdmissionLimiter(32, 16, 32)
	staticKeys := parseSellerKeysEnv(os.Getenv("PROXY_STATIC_SELLER_KEYS"))
	var src keypool.Source = keypool.StaticSource{Keys: staticKeys}
	if strings.TrimSpace(os.Getenv("API_INTERNAL_BASE_URL")) != "" && strings.TrimSpace(os.Getenv("INTERNAL_GATEWAY_TOKEN")) != "" {
		src = apiClient
	}
	pool := keypool.NewFromSource(src, envInt("PROXY_KEY_MAX_INFLIGHT", 32))
	if err := pool.Refresh(context.Background()); err != nil {
		logger.Error("key pool refresh failed", "error", err)
		if len(staticKeys) > 0 {
			pool = keypool.New(staticKeys, envInt("PROXY_KEY_MAX_INFLIGHT", 32))
		}
	}

	memUsage := usageobs.NewMemorySink()
	var usageSink usageobs.Sink = memUsage
	if strings.TrimSpace(os.Getenv("API_INTERNAL_BASE_URL")) != "" && strings.TrimSpace(os.Getenv("INTERNAL_GATEWAY_TOKEN")) != "" {
		dur := &usageobs.DurableSink{
			Dir:  firstNonEmpty(os.Getenv("PROXY_USAGE_WAL_DIR"), ""),
			Next: apisvc.FanoutSink{Mem: memUsage, Remote: apiClient},
		}
		go dur.RunReplay(context.Background())
		usageSink = dur
	}

	catalog, err := endpcatalog.MustLoadFromEnv()
	if err != nil {
		logger.Error("endpoint catalog load failed", "error", err)
		os.Exit(1)
	}
	logger.Info("endpoint catalog loaded",
		"catalog_major", catalog.CatalogMajor,
		"catalog_minor", catalog.CatalogMinor,
		"freeze_date", catalog.FreezeDate,
		"record_count", len(catalog.Records),
	)
	var snapHolder runtimesnap.Holder
	snap, err := snapHolder.Swap("boot", catalog)
	if err != nil {
		logger.Error("runtime snapshot rejected", "error", err)
		os.Exit(1)
	}
	logger.Info("runtime snapshot published",
		"snapshot_id", snap.ID,
		"generation", snap.Generation,
		"catalog_major", snap.CatalogMajor,
	)
	catalogReady := true

	httpMetrics := observability.DefaultProxyHTTPMetrics()
	inventory := observability.DefaultKeyInventoryMetrics()
	publishInventory(inventory, pool)

	proxyEnabled := os.Getenv("PROXY_ENABLED") != "0"
	var proxyDeps *httpserver.ProxyDeps
	if proxyEnabled {
		proxyDeps = &httpserver.ProxyDeps{
			Enabled:   true,
			Auth:      proxyauth.Authenticator{Pepper: pepper, Store: authStore, Limiter: authLimiter},
			Pool:      pool,
			Chat:      chat,
			Usage:     usageSink,
			Metrics:   httpMetrics,
			WriteIdle: httpserver.DefaultSSEWriteIdle,
		}
	}

	snapStore := passthrough.NewMemoryStore()
	loadNativeSnapshots(snapStore, os.Getenv("PROXY_NATIVE_SNAPSHOTS"))
	nativeKernel := &passthrough.Kernel{
		Catalog:  catalog,
		Selector: passthrough.RoutingSelector{},
	}
	var nativeAuth proxyauth.Authenticator
	if proxyDeps != nil {
		nativeAuth = proxyDeps.Auth
	} else {
		nativeAuth = proxyauth.Authenticator{Pepper: pepper, Store: authStore, Limiter: authLimiter}
	}
	publicSrv, err := httpserver.NewServer(httpserver.Config{
		Service:       "proxy-gateway",
		Version:       "0.1.0",
		Logger:        logger,
		Validate:      validateDeps,
		MountValidate: mountOnPublic,
		Proxy:         proxyDeps,
		Passthrough: &httpserver.PassthroughDeps{
			Kernel:    nativeKernel,
			Auth:      nativeAuth,
			Snapshots: snapStore,
		},
		CatalogReady: &catalogReady,
	})
	if err != nil {
		logger.Error("failed to create public server", "error", err)
		os.Exit(1)
	}

	if isolate {
		internalAddr := providervalid.InternalListenAddr(cfg.InternalBind, cfg.InternalPort, port)
		internalSrv, err := httpserver.NewInternalValidateServer(httpserver.Config{
			Service:  "proxy-gateway",
			Version:  "0.1.0",
			Logger:   logger,
			Validate: validateDeps,
		})
		if err != nil {
			logger.Error("failed to create internal validate server", "error", err)
			os.Exit(1)
		}
		go func() {
			logger.Info("starting internal provider validate listener (C1 isolated)",
				"addr", internalAddr,
				"app_env", cfg.AppEnv,
			)
			if err := http.ListenAndServe(internalAddr, internalSrv.Handler()); err != nil {
				logger.Error("internal validate server exited", "error", err)
				os.Exit(1)
			}
		}()
	} else if cfg.InternalEnabled {
		logger.Info("internal provider validate mounted on public listener (local/dev only)",
			"app_env", cfg.AppEnv,
			"bind", cfg.InternalBind,
		)
	}

	go func() {
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for range ticker.C {
			if err := pool.Refresh(context.Background()); err != nil {
				logger.Error("key pool refresh failed", "error", err)
			}
			publishInventory(inventory, pool)
		}
	}()

	go func() {
		var api keyhealth.HealthSink
		if strings.TrimSpace(os.Getenv("API_INTERNAL_BASE_URL")) != "" && strings.TrimSpace(os.Getenv("INTERNAL_GATEWAY_TOKEN")) != "" {
			api = apiClient
		}
		sch := &keyhealth.Scheduler{
			Interval: 30 * time.Second,
			Store:    keyhealth.PoolStore{Pool: pool, API: api},
			Probe: func(ctx context.Context, apiKey string) providervalid.ErrorCategory {
				res := application.NewValidator(cfg).ValidateCredential(ctx, providervalid.CredentialValidationRequest{
					Platform: "volcano", APIKey: apiKey, RequestID: "health",
				})
				return res.ErrorCategory
			},
			OnProbe: func(platform, result string) {
				httpMetrics.Health(platform, result)
			},
		}
		sch.Run(context.Background())
	}()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	logger.Info("starting proxy-gateway public listener",
		"addr", publicAddr,
		"validate_on_public", mountOnPublic,
		"proxy_enabled", proxyEnabled,
	)
	if err := listenServe(ctx, publicAddr, publicSrv.Handler()); err != nil {
		logger.Error("server exited", "error", err)
		os.Exit(1)
	}
}

func listenServe(ctx context.Context, addr string, h http.Handler) error {
	srv := httpserver.NewPublicHTTPServer(addr, h)
	errc := make(chan error, 1)
	go func() { errc <- srv.ListenAndServe() }()
	select {
	case err := <-errc:
		if err == http.ErrServerClosed {
			return nil
		}
		return err
	case <-ctx.Done():
		shctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = srv.Shutdown(shctx)
		err := <-errc
		if err == http.ErrServerClosed || err == nil {
			return nil
		}
		return err
	}
}

func publishInventory(inv *observability.KeyInventoryMetrics, pool *keypool.Pool) {
	if inv == nil || pool == nil {
		return
	}
	snap := pool.Snapshot()
	rows := make([]observability.KeyStatus, 0, len(snap))
	for _, k := range snap {
		rows = append(rows, observability.KeyStatus{Admin: k.Admin, Health: k.Health})
	}
	inv.Publish("volcano", rows)
}

func firstNonEmpty(v, def string) string {
	if strings.TrimSpace(v) == "" {
		return def
	}
	return strings.TrimSpace(v)
}

func envInt(k string, def int) int {
	return envIntFrom(os.Getenv(k), def)
}

func envIntFrom(s string, def int) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return def
	}
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			return def
		}
		n = n*10 + int(c-'0')
	}
	return n
}

// PROXY_STATIC_PROXY_KEYS=tmk-secret|buyer-uuid[|projectId|mode|preview][,...]
func parseProxyAuthEnv(pepper []byte, raw string) map[string]proxyauth.Record {
	out := map[string]proxyauth.Record{}
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		sep := "|"
		if !strings.Contains(part, "|") {
			sep = ":"
		}
		kv := strings.Split(part, sep)
		if len(kv) < 2 {
			continue
		}
		sec, buyer := strings.TrimSpace(kv[0]), strings.TrimSpace(kv[1])
		if !proxyauth.ValidProxySecret(sec) {
			continue
		}
		h := proxyauth.HashSecret(pepper, sec)
		kid := h
		if len(kid) > 8 {
			kid = kid[:8]
		}
		rec := proxyauth.Record{KeyID: kid, BuyerID: buyer, Platform: "volcano", Status: "active"}
		if len(kv) >= 3 {
			rec.ProjectID = strings.TrimSpace(kv[2])
		}
		if len(kv) >= 4 {
			rec.ProjectMode = strings.TrimSpace(kv[3])
		}
		if len(kv) >= 5 {
			rec.PreviewOptIn = strings.TrimSpace(kv[4]) == "1"
		}
		out[h] = rec
	}
	return out
}

// PROXY_NATIVE_SNAPSHOTS=projectId|mode|preview|connId|protocol|baseURL|credential|sellerOwner[,...]
func loadNativeSnapshots(store *passthrough.MemoryStore, raw string) {
	if store == nil {
		return
	}
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		f := strings.Split(part, "|")
		if len(f) < 7 {
			continue
		}
		projectID := strings.TrimSpace(f[0])
		mode := strings.TrimSpace(f[1])
		preview := strings.TrimSpace(f[2]) == "1"
		connID := strings.TrimSpace(f[3])
		protocol := strings.TrimSpace(f[4])
		baseURL := strings.TrimSpace(f[5])
		cred := strings.TrimSpace(f[6])
		seller := ""
		if len(f) >= 8 {
			seller = strings.TrimSpace(f[7])
		}
		snap, _ := store.Lookup(projectID)
		snap.ProjectID = projectID
		snap.Mode = mode
		snap.PreviewOptIn = preview
		up := passthrough.Upstream{BaseURL: baseURL, Credential: cred, ConnectionID: connID}
		if snap.Upstreams == nil {
			snap.Upstreams = map[string]passthrough.Upstream{}
		}
		snap.Upstreams[connID] = up
		if mode == "dedicated" {
			snap.Dedicated = passthrough.DedicatedSnapshot{
				ConnectionID: connID,
				Status:       "active",
				Health:       "healthy",
				Up:           up,
			}
		} else {
			snap.Candidates = append(snap.Candidates, qualify.Candidate{
				ConnectionID:     connID,
				SellerOwnerID:    seller,
				Provider:         protocol,
				Protocol:         protocol,
				SupplyMode:       "shared",
				Lifecycle:        "listed",
				Health:           "healthy",
				DeclaredCapacity: 32,
				AdmitsNew:        true,
				PriceValid:       true,
			})
			if snap.Signals == nil {
				snap.Signals = map[string]score.Signals{}
			}
			snap.Signals[connID] = score.Signals{
				ConnectionID:    connID,
				Health:          "healthy",
				LatencyPresent:  true,
				LatencyMS:       50,
				CapacityPresent: true,
				Remaining:       32,
				Declared:        32,
				PricePresent:    true,
				SellerBPS:       10000,
			}
		}
		store.Put(snap)
	}
}

// PROXY_STATIC_SELLER_KEYS=id|sellerId|apiKey[|admin|health[|officialConcurrency]][,...]
func parseSellerKeysEnv(raw string) []keypool.SellerKey {
	var keys []keypool.SellerKey
	for _, part := range strings.Split(raw, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		f := strings.Split(part, "|")
		if len(f) < 3 {
			continue
		}
		admin, health := "active", "healthy"
		if len(f) >= 4 && strings.TrimSpace(f[3]) != "" {
			admin = strings.TrimSpace(f[3])
		}
		if len(f) >= 5 && strings.TrimSpace(f[4]) != "" {
			health = strings.TrimSpace(f[4])
		}
		official := 0
		if len(f) >= 6 {
			official = envIntFrom(strings.TrimSpace(f[5]), 0)
		}
		maxIF := 0
		if official > 0 {
			maxIF = keypool.AllocableConcurrency(official)
		}
		keys = append(keys, keypool.SellerKey{
			ID: f[0], SellerID: f[1], APIKey: f[2],
			Admin: admin, Health: health, Platform: "volcano",
			OfficialConcurrency: official, MaxInflight: maxIF,
		})
	}
	return keys
}
