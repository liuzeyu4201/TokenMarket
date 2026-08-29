package httpserver

import (
	"net/http"
	"time"
)

const (
	DefaultReadHeaderTimeout = 5 * time.Second
	DefaultIdleTimeout       = 60 * time.Second
	DefaultReadTimeout       = 15 * time.Second
	DefaultMaxHeaderBytes    = 16 << 10
	DefaultSSEWriteIdle      = 15 * time.Second
	DefaultBodyReadTimeout   = 15 * time.Second
)

// NewPublicHTTPServer constructs the public listener with finite progress deadlines.
func NewPublicHTTPServer(addr string, handler http.Handler) *http.Server {
	return NewPublicHTTPServerTimeouts(addr, handler, DefaultReadHeaderTimeout, DefaultIdleTimeout)
}

func NewPublicHTTPServerTimeouts(addr string, handler http.Handler, header, idle time.Duration) *http.Server {
	return NewPublicHTTPServerReadTimeouts(addr, handler, header, idle, DefaultReadTimeout)
}

func NewPublicHTTPServerReadTimeouts(addr string, handler http.Handler, header, idle, read time.Duration) *http.Server {
	if header <= 0 {
		header = DefaultReadHeaderTimeout
	}
	if idle <= 0 {
		idle = DefaultIdleTimeout
	}
	if read <= 0 {
		read = DefaultReadTimeout
	}
	if read < header {
		read = header
	}
	return &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: header,
		ReadTimeout:       read,
		IdleTimeout:       idle,
		MaxHeaderBytes:    DefaultMaxHeaderBytes,
	}
}
