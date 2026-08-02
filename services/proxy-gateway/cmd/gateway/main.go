package main

import (
	"net/http"
	"os"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
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

	// C1: 非 local 启用内部验证时，validate 不挂公网 listener，改独立回环监听。
	isolate := cfg.MustIsolateInternalListener()
	mountOnPublic := cfg.InternalEnabled && !isolate

	publicSrv, err := httpserver.NewServer(httpserver.Config{
		Service:       "proxy-gateway",
		Version:       "0.1.0",
		Logger:        logger,
		Validate:      validateDeps,
		MountValidate: mountOnPublic,
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

	logger.Info("starting proxy-gateway public listener",
		"addr", publicAddr,
		"validate_on_public", mountOnPublic,
	)
	if err := http.ListenAndServe(publicAddr, publicSrv.Handler()); err != nil {
		logger.Error("server exited", "error", err)
		os.Exit(1)
	}
}
