package main

import (
	"context"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
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

	pepper := []byte(firstNonEmpty(os.Getenv("PROXY_AUTH_PEPPER"), "dev-only-proxy-pepper-not-for-prod"))
	staticAuth := proxyauth.MapStore{Records: parseProxyAuthEnv(pepper, os.Getenv("PROXY_STATIC_PROXY_KEYS"))}
	apiClient := apisvc.New(os.Getenv("API_INTERNAL_BASE_URL"), os.Getenv("INTERNAL_GATEWAY_TOKEN"))
	var authStore proxyauth.Store = staticAuth
	if strings.TrimSpace(os.Getenv("API_INTERNAL_BASE_URL")) != "" && strings.TrimSpace(os.Getenv("INTERNAL_GATEWAY_TOKEN")) != "" {
		authStore = apisvc.CompositeStore{Static: staticAuth, Remote: apiClient}
	}
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

	usageSink := usageobs.Sink(usageobs.NewMemorySink())

	httpMetrics := observability.DefaultProxyHTTPMetrics()

	proxyEnabled := os.Getenv("PROXY_ENABLED") != "0"
	var proxyDeps *httpserver.ProxyDeps
	if proxyEnabled {
		proxyDeps = &httpserver.ProxyDeps{
			Enabled: true,
			Auth:    proxyauth.Authenticator{Pepper: pepper, Store: authStore},
			Pool:    pool,
			Chat:    chat,
			Usage:   usageSink,
			Metrics: httpMetrics,
		}
	}

	publicSrv, err := httpserver.NewServer(httpserver.Config{
		Service:       "proxy-gateway",
		Version:       "0.1.0",
		Logger:        logger,
		Validate:      validateDeps,
		MountValidate: mountOnPublic,
		Proxy:         proxyDeps,
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
		}
	}()

	logger.Info("starting proxy-gateway public listener",
		"addr", publicAddr,
		"validate_on_public", mountOnPublic,
		"proxy_enabled", proxyEnabled,
	)
	if err := http.ListenAndServe(publicAddr, publicSrv.Handler()); err != nil {
		logger.Error("server exited", "error", err)
		os.Exit(1)
	}
}

func firstNonEmpty(v, def string) string {
	if strings.TrimSpace(v) == "" {
		return def
	}
	return strings.TrimSpace(v)
}

func envInt(k string, def int) int {
	s := strings.TrimSpace(os.Getenv(k))
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

// PROXY_STATIC_PROXY_KEYS=tmk-secret|buyer-uuid[,...]
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
		kv := strings.SplitN(part, sep, 2)
		if len(kv) != 2 {
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
		out[h] = proxyauth.Record{KeyID: kid, BuyerID: buyer, Platform: "volcano", Status: "active"}
	}
	return out
}

// PROXY_STATIC_SELLER_KEYS=id|sellerId|apiKey[|admin|health][,...]
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
		keys = append(keys, keypool.SellerKey{
			ID: f[0], SellerID: f[1], APIKey: f[2],
			Admin: admin, Health: health, Platform: "volcano",
		})
	}
	return keys
}
