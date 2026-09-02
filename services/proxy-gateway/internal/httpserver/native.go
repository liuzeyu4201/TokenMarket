package httpserver

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/passthrough"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
)

// PassthroughDeps wires the SF18 native kernel onto the public listener.
type PassthroughDeps struct {
	Kernel    *passthrough.Kernel
	Auth      proxyauth.Authenticator
	Snapshots passthrough.SnapshotStore
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
		rec, st := d.Auth.AuthenticateStatus(c.GetHeader("Authorization"))
		if st != proxyauth.AuthOK {
			code := http.StatusUnauthorized
			msg := "代理 Key 无效"
			biz := "INVALID_API_KEY"
			if st == proxyauth.AuthOverload {
				code = http.StatusTooManyRequests
				msg = "认证过载，请稍后重试"
				biz = "AUTH_OVERLOAD"
			}
			passthrough.WriteError(c.Writer, c.Request, code, biz, msg)
			c.Abort()
			return
		}
		projectID := rec.ProjectID
		snap, ok := lookupSnapshot(d.Snapshots, projectID)
		if !ok {
			passthrough.WriteError(c.Writer, c.Request, http.StatusServiceUnavailable, passthrough.CodeNoUpstream, "暂无可用上游连接")
			c.Abort()
			return
		}
		if rec.ProjectMode != "" {
			snap.Mode = rec.ProjectMode
		}
		snap.PreviewOptIn = rec.PreviewOptIn
		if snap.BuyerOwnerID == "" {
			snap.BuyerOwnerID = rec.BuyerID
		}
		if snap.ProjectID == "" {
			snap.ProjectID = projectID
		}
		req := c.Request.WithContext(passthrough.WithSnapshot(c.Request.Context(), snap))
		d.Kernel.ServeHTTP(c.Writer, req, snap.Mode, snap.PreviewOptIn)
		c.Abort()
	}
}

func lookupSnapshot(store passthrough.SnapshotStore, projectID string) (passthrough.ProjectSnapshot, bool) {
	if store == nil || projectID == "" {
		return passthrough.ProjectSnapshot{}, false
	}
	return store.Lookup(projectID)
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
