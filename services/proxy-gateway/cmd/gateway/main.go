package main

import (
	"net/http"
	"os"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	logger := observability.NewLogger()
	srv, err := httpserver.NewServer(httpserver.Config{
		Service: "proxy-gateway",
		Version: "0.1.0",
		Logger:  logger,
	})
	if err != nil {
		logger.Error("failed to create server", "error", err)
		os.Exit(1)
	}

	logger.Info("starting proxy-gateway", "port", port)
	if err := http.ListenAndServe(":"+port, srv.Handler()); err != nil {
		logger.Error("server exited", "error", err)
		os.Exit(1)
	}
}
