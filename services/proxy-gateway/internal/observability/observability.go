// Package observability provides minimal logging and metrics helpers for the
// SF01 gateway scaffold. It contains no business logic.
package observability

import (
	"log/slog"
	"os"
)

// NewLogger creates a structured JSON logger that writes to stderr.
func NewLogger() *slog.Logger {
	return slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: slog.LevelInfo}))
}
