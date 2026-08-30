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

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

// Limits bound body size and upstream wait.
type Limits struct {
	MaxRequestBytes  int64
	MaxResponseBytes int64
	UpstreamTimeout  time.Duration
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
	return l
}

// Kernel is the same-protocol passthrough engine.
type Kernel struct {
	Catalog   *endpcatalog.Catalog
	Selector  Selector
	Limits    Limits
	Transport http.RoundTripper
	Now       func() time.Time
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

// ServeHTTP admits the request via the catalog then copies bytes to upstream.
func (k *Kernel) ServeHTTP(w http.ResponseWriter, r *http.Request, projectMode string, previewOptIn bool) {
	lim := k.Limits.withDefaults()
	proto, path, code := Resolve(r, k.Catalog)
	if code != "" {
		writePlatform(w, r, http.StatusBadRequest, code, "无法确定原生协议")
		return
	}
	dec := endpcatalog.Admit(k.Catalog, endpcatalog.AdmitInput{
		Provider:     proto,
		Method:       r.Method,
		Path:         path,
		ProjectMode:  projectMode,
		PreviewOptIn: previewOptIn,
	})
	if !dec.Allow {
		writePlatform(w, r, statusFor(dec.Code), dec.Code, "目录拒绝该端点")
		return
	}
	endpointID := ""
	if dec.Record != nil {
		endpointID = dec.Record.ID
	}
	up, err := k.selector().Select(r.Context(), proto, endpointID)
	if err != nil {
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
		r.Body = http.MaxBytesReader(w, r.Body, lim.MaxRequestBytes)
	}
	ctx := r.Context()
	if lim.UpstreamTimeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, lim.UpstreamTimeout)
		defer cancel()
		r = r.WithContext(ctx)
	}
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
			stripDenied(out.Header, inboundDenied)
			applyUpstreamAuth(out.Header, proto, up.Credential)
		},
		Transport:     k.transport(),
		FlushInterval: 50 * time.Millisecond,
		ModifyResponse: func(resp *http.Response) error {
			stripDenied(resp.Header, outboundDenied)
			rid := r.Header.Get("X-Request-ID")
			if rid != "" {
				resp.Header.Set("X-Request-ID", rid)
			}
			if cl := resp.ContentLength; cl > 0 && lim.MaxResponseBytes > 0 && cl > lim.MaxResponseBytes {
				return errTooLarge
			}
			return nil
		},
		ErrorHandler: func(rw http.ResponseWriter, req *http.Request, e error) {
			if errors.Is(e, context.Canceled) || errors.Is(req.Context().Err(), context.Canceled) {
				writePlatform(rw, req, 499, CodeCanceled, "客户端已取消")
				return
			}
			if errors.Is(e, context.DeadlineExceeded) || errors.Is(req.Context().Err(), context.DeadlineExceeded) {
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
	proxy.ServeHTTP(w, r)
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
