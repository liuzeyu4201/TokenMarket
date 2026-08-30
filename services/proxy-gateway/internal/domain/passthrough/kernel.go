package passthrough

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/affinity"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/pricelock"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageparse"
)

// Limits bound body size and upstream wait.
type Limits struct {
	MaxRequestBytes  int64
	MaxResponseBytes int64
	UpstreamTimeout  time.Duration
	IdleTimeout      time.Duration
	UploadTimeout    time.Duration
}

func (l Limits) withDefaults() Limits {
	if l.MaxRequestBytes <= 0 {
		l.MaxRequestBytes = 8 << 20
	}
	if l.MaxResponseBytes <= 0 {
		l.MaxResponseBytes = 32 << 20
	}
	if l.UpstreamTimeout <= 0 {
		l.UpstreamTimeout = 30 * time.Second
	}
	if l.IdleTimeout <= 0 {
		l.IdleTimeout = 30 * time.Second
	}
	if l.UploadTimeout <= 0 {
		l.UploadTimeout = 60 * time.Second
	}
	return l
}

// Kernel is the same-protocol passthrough engine.
type Kernel struct {
	Catalog   *endpcatalog.Catalog
	Selector  Selector
	Limits    Limits
	Transport http.RoundTripper
	Now       func() time.Time
	Affinity  affinity.Store
	Usage     usageobs.Sink
	Capture   usageparse.Recorder
	PriceLock *pricelock.Locker
}

func (k *Kernel) selector() Selector {
	if k.Selector != nil {
		return k.Selector
	}
	return FailClosedSelector{}
}

func (k *Kernel) transport() http.RoundTripper {
	if k.Transport != nil {
		return k.Transport
	}
	return http.DefaultTransport
}

func (k *Kernel) now() time.Time {
	if k.Now != nil {
		return k.Now()
	}
	return time.Now().UTC()
}

func admitMethod(r *http.Request, cat *endpcatalog.Catalog, proto, path string) string {
	if websocketUpgrade(r) && endpcatalog.Match(cat, proto, "WEBSOCKET", path) != nil {
		return "WEBSOCKET"
	}
	return r.Method
}

// ServeHTTP admits the request via the catalog then copies bytes to upstream.
func (k *Kernel) ServeHTTP(w http.ResponseWriter, r *http.Request, projectMode string, previewOptIn bool) {
	lim := k.Limits.withDefaults()
	proto, path, code := Resolve(r, k.Catalog)
	if code != "" {
		writePlatform(w, r, http.StatusBadRequest, code, "无法确定原生协议")
		return
	}
	method := admitMethod(r, k.Catalog, proto, path)
	dec := endpcatalog.Admit(k.Catalog, endpcatalog.AdmitInput{
		Provider:     proto,
		Method:       method,
		Path:         path,
		ProjectMode:  projectMode,
		PreviewOptIn: previewOptIn,
	})
	if !dec.Allow {
		writePlatform(w, r, statusFor(dec.Code), dec.Code, "目录拒绝该端点")
		return
	}
	rec := dec.Record
	endpointID := ""
	transportName := ""
	affinityKind := ""
	metering := ""
	if rec != nil {
		endpointID = rec.ID
		transportName = rec.Transport
		affinityKind = rec.Affinity
		metering = rec.MeteringSource
	}
	isWS := transportName == "websocket"
	projectID := r.Header.Get("X-TokenMarket-Project-ID")
	if k.PriceLock != nil {
		if reqID := r.Header.Get("X-Request-ID"); reqID != "" {
			_, _ = k.PriceLock.Lock(reqID)
		}
	}

	var pinConn string
	if affinityKind == "resource_id" {
		vars := endpcatalog.PathVars(rec.PathTemplate, path)
		if rid := endpcatalog.ResourceID(vars); rid != "" {
			b, err := k.lookupAffinity(proto, rid)
			if err != nil {
				if errors.Is(err, affinity.ErrConflict) {
					writePlatform(w, r, http.StatusConflict, CodeAffinityConflict, "资源已绑定其它连接")
					return
				}
				writePlatform(w, r, http.StatusNotFound, CodeAffinityNotFound, "资源未绑定连接")
				return
			}
			pinConn = b.ConnectionID
		}
	}

	var up Upstream
	var err error
	if pinConn != "" {
		up, err = k.selector().SelectConnection(r.Context(), pinConn)
	} else {
		up, err = k.selector().Select(r.Context(), proto, endpointID)
	}
	if err != nil {
		if err == errDedicatedUnavailable {
			writePlatform(w, r, http.StatusServiceUnavailable, CodeDedicatedUnavailable, "专享连接不可用")
			return
		}
		writePlatform(w, r, http.StatusServiceUnavailable, CodeNoUpstream, "暂无可用上游连接")
		return
	}
	base, err := url.Parse(up.BaseURL)
	if err != nil || base.Scheme == "" || base.Host == "" {
		writePlatform(w, r, http.StatusServiceUnavailable, CodeNoUpstream, "暂无可用上游连接")
		return
	}
	if r.ContentLength > lim.MaxRequestBytes {
		writePlatform(w, r, http.StatusRequestEntityTooLarge, CodeTooLarge, "请求体超过上限")
		return
	}
	if r.Body != nil {
		body := http.MaxBytesReader(w, r.Body, lim.MaxRequestBytes)
		if transportName == "multipart" || transportName == "binary" {
			body = &deadlineReadCloser{ReadCloser: body, deadline: time.Now().Add(lim.UploadTimeout)}
		}
		r.Body = body
	}
	ctx := r.Context()
	timeout := lim.UpstreamTimeout
	if (transportName == "multipart" || transportName == "binary") && lim.UploadTimeout > 0 && (timeout == 0 || lim.UploadTimeout < timeout) {
		timeout = lim.UploadTimeout
	}
	if timeout > 0 && transportName != "websocket" && transportName != "sse" {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, timeout)
		defer cancel()
		r = r.WithContext(ctx)
	} else if timeout > 0 && transportName == "sse" {
		// SSE uses idle write timeout instead of a hard upstream deadline so
		// events can flow longer than the default request timeout.
		r = r.WithContext(ctx)
	}

	idle := time.Duration(0)
	flushEach := false
	if transportName == "sse" {
		idle = lim.IdleTimeout
		flushEach = true
	}

	register := affinityKind == "resource_id" && pinConn == "" && k.Affinity != nil && up.ConnectionID != ""
	pw := &streamWriter{ResponseWriter: w, idle: idle, flush: flushEach}
	rid := r.Header.Get("X-Request-ID")

	proxy := &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.Out = pr.Out.WithContext(pr.In.Context())
			out := pr.Out
			out.URL.Scheme = base.Scheme
			out.URL.Host = base.Host
			out.URL.Path = path
			out.URL.RawPath = ""
			out.URL.RawQuery = pr.In.URL.RawQuery
			out.Host = base.Host
			stripDenied(out.Header, inboundStripSet(isWS))
			applyUpstreamAuth(out.Header, proto, up.Credential)
		},
		Transport:     k.transport(),
		FlushInterval: flushInterval(transportName),
		ModifyResponse: func(resp *http.Response) error {
			stripDenied(resp.Header, outboundDenied)
			if rid != "" {
				resp.Header.Set("X-Request-ID", rid)
			}
			if cl := resp.ContentLength; cl > 0 && lim.MaxResponseBytes > 0 && cl > lim.MaxResponseBytes {
				return errTooLarge
			}
			body := resp.Body
			if register && resp.StatusCode < 300 && body != nil {
				connID := up.ConnectionID
				ep := endpointID
				pr := proto
				pj := projectID
				body = newIDTee(body, func(id string) {
					_ = k.Affinity.Put(affinity.Binding{
						Protocol:     pr,
						ResourceID:   id,
						ConnectionID: connID,
						ProjectID:    pj,
						EndpointID:   ep,
					})
				})
			}
			if k.Capture != nil && resp.StatusCode < 300 && body != nil {
				ct := resp.Header.Get("Content-Type")
				body = newUsageTee(body, ct, proto, metering, rid, projectID, endpointID, k.Capture)
			}
			resp.Body = body
			return nil
		},
		ErrorHandler: func(rw http.ResponseWriter, req *http.Request, e error) {
			k.observeEnd(rid, statusFromErr(e), endReason(e))
			if errors.Is(e, context.Canceled) || errors.Is(req.Context().Err(), context.Canceled) {
				writePlatform(rw, req, 499, CodeCanceled, "客户端已取消")
				return
			}
			if errors.Is(e, errSlowConsumer) {
				writePlatform(rw, req, http.StatusGatewayTimeout, CodeSlowConsumer, "客户端消费过慢")
				return
			}
			if errors.Is(e, context.DeadlineExceeded) || errors.Is(req.Context().Err(), context.DeadlineExceeded) || errors.Is(e, errUploadTimeout) {
				writePlatform(rw, req, http.StatusGatewayTimeout, CodeTimeout, "上游超时")
				return
			}
			if isMaxBytes(e) {
				writePlatform(rw, req, http.StatusRequestEntityTooLarge, CodeTooLarge, "请求体超过上限")
				return
			}
			writePlatform(rw, req, http.StatusBadGateway, CodeTimeout, "上游传输失败")
		},
	}
	proxy.ServeHTTP(pw, r)
	status := pw.status
	if status == 0 {
		status = http.StatusOK
	}
	k.observeEnd(rid, status, "complete")
}

func (k *Kernel) lookupAffinity(proto, resourceID string) (affinity.Binding, error) {
	if k.Affinity == nil {
		return affinity.Binding{}, affinity.ErrNotFound
	}
	return k.Affinity.Get(proto, resourceID)
}

func (k *Kernel) observeEnd(requestID string, status int, reason string) {
	if k == nil || k.Usage == nil || requestID == "" {
		return
	}
	_ = k.Usage.Observe(context.Background(), usageobs.Observation{
		RequestID:   requestID,
		StatusCode:  status,
		EndReason:   reason,
		UsageSource: "passthrough",
	})
}

func flushInterval(transport string) time.Duration {
	if transport == "sse" {
		return -1
	}
	return 50 * time.Millisecond
}

func statusFromErr(e error) int {
	switch {
	case errors.Is(e, context.Canceled):
		return 499
	case errors.Is(e, errSlowConsumer):
		return http.StatusGatewayTimeout
	case isMaxBytes(e):
		return http.StatusRequestEntityTooLarge
	default:
		return http.StatusGatewayTimeout
	}
}

func endReason(e error) string {
	switch {
	case errors.Is(e, context.Canceled):
		return "canceled"
	case errors.Is(e, errSlowConsumer):
		return "slow_consumer"
	default:
		return "error"
	}
}

var errTooLarge = errors.New(CodeTooLarge)

func isMaxBytes(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, errTooLarge) {
		return true
	}
	s := err.Error()
	return strings.Contains(s, "MaxBytesReader") || strings.Contains(s, "http: request body too large")
}

func statusFor(code string) int {
	switch code {
	case endpcatalog.CodeNotCataloged:
		return http.StatusNotFound
	case endpcatalog.CodeControlPlane, endpcatalog.CodePreview, endpcatalog.CodeDedicatedRequired:
		return http.StatusForbidden
	default:
		return http.StatusBadRequest
	}
}

func writePlatform(w http.ResponseWriter, r *http.Request, status int, code, message string) {
	rid := r.Header.Get("X-Request-ID")
	if rid == "" {
		rid = strconv.FormatInt(time.Now().UnixNano(), 36)
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Request-ID", rid)
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"code":       code,
		"message":    message,
		"data":       nil,
		"request_id": rid,
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	})
}
