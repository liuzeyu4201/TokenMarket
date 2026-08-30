package httpserver

import (
	"github.com/gin-gonic/gin"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/passthrough"
)

// PassthroughDeps wires the SF18 native kernel onto the public listener.
type PassthroughDeps struct {
	Kernel       *passthrough.Kernel
	ProjectMode  string
	PreviewOptIn bool
}

func (s *Server) registerPassthrough(d PassthroughDeps) {
	if d.Kernel == nil {
		return
	}
	s.passthrough = &d
	h := s.handleNative(d)
	s.engine.Any("/openai/*path", h)
	s.engine.Any("/anthropic/*path", h)
	s.engine.Any("/vertex/*path", h)
}

func (s *Server) handleNative(d PassthroughDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		mode := d.ProjectMode
		if mode == "" {
			mode = c.GetHeader("X-TokenMarket-Project-Mode")
		}
		preview := d.PreviewOptIn || c.GetHeader("X-TokenMarket-Preview") == "1"
		d.Kernel.ServeHTTP(c.Writer, c.Request, mode, preview)
		c.Abort()
	}
}

func (s *Server) tryNative(c *gin.Context) bool {
	if s.passthrough == nil || s.passthrough.Kernel == nil {
		return false
	}
	_, _, code := passthrough.Resolve(c.Request, s.passthrough.Kernel.Catalog)
	if code != "" {
		return false
	}
	s.handleNative(*s.passthrough)(c)
	return true
}

func nativeOrNotFound(s *Server) gin.HandlerFunc {
	return func(c *gin.Context) {
		if s.tryNative(c) {
			return
		}
		s.notFound(c)
	}
}

func (s *Server) hasNativeRoute() bool {
	return s != nil && s.passthrough != nil && s.passthrough.Kernel != nil
}
