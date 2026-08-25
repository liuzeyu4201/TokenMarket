// Package apisvc 调用 API Service 内部接口（Key 池、认证查找、用量、健康写回）。
package apisvc

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
)

// Client API Service 内部 HTTP。
type Client struct {
	BaseURL string
	Token   string
	HTTP    *http.Client
}

func New(baseURL, token string) *Client {
	return &Client{
		BaseURL: strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		Token:   token,
		HTTP:    &http.Client{Timeout: 2 * time.Second},
	}
}

func (c *Client) enabled() bool {
	return c != nil && c.BaseURL != "" && c.Token != ""
}

func (c *Client) do(ctx context.Context, method, path string, body any) (*http.Response, error) {
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, rdr)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Internal-Token", c.Token)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	return c.HTTP.Do(req)
}

type routableKey struct {
	ID       string `json:"id"`
	SellerID string `json:"seller_id"`
	APIKey   string `json:"api_key"`
	Admin    string `json:"administrative_state"`
	Health   string `json:"health_state"`
	Platform string `json:"platform"`
}

type envelope struct {
	Code string          `json:"code"`
	Data json.RawMessage `json:"data"`
}

// List 实现 keypool.Source。
func (c *Client) List(ctx context.Context) ([]keypool.SellerKey, error) {
	if !c.enabled() {
		return nil, fmt.Errorf("api client disabled")
	}
	resp, err := c.do(ctx, http.MethodGet, "/internal/v1/seller-keys/routable", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("list routable status %d", resp.StatusCode)
	}
	var env envelope
	if err := json.NewDecoder(io.LimitReader(resp.Body, 1<<20)).Decode(&env); err != nil {
		return nil, err
	}
	var keys []routableKey
	if err := json.Unmarshal(env.Data, &keys); err != nil {
		var wrap struct {
			Keys []routableKey `json:"keys"`
		}
		if err2 := json.Unmarshal(env.Data, &wrap); err2 != nil {
			return nil, err
		}
		keys = wrap.Keys
	}
	out := make([]keypool.SellerKey, 0, len(keys))
	for _, k := range keys {
		plat := k.Platform
		if plat == "" {
			plat = "volcano"
		}
		out = append(out, keypool.SellerKey{
			ID: k.ID, SellerID: k.SellerID, APIKey: k.APIKey,
			Admin: k.Admin, Health: k.Health, Platform: plat,
		})
	}
	return out, nil
}

type authRec struct {
	KeyID    string `json:"key_id"`
	BuyerID  string `json:"buyer_id"`
	Platform string `json:"platform"`
	Status   string `json:"status"`
}

// Lookup 实现 proxyauth.Store。失败关闭：错误视为未命中。
func (c *Client) Lookup(hashHex string) (proxyauth.Record, bool) {
	if !c.enabled() || hashHex == "" {
		return proxyauth.Record{}, false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	q := "/internal/v1/proxy-keys/by-hash?hash=" + url.QueryEscape(hashHex)
	resp, err := c.do(ctx, http.MethodGet, q, nil)
	if err != nil {
		return proxyauth.Record{}, false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return proxyauth.Record{}, false
	}
	var env envelope
	if json.NewDecoder(io.LimitReader(resp.Body, 65536)).Decode(&env) != nil {
		return proxyauth.Record{}, false
	}
	var rec authRec
	if json.Unmarshal(env.Data, &rec) != nil {
		return proxyauth.Record{}, false
	}
	if rec.Status != "active" {
		return proxyauth.Record{}, false
	}
	return proxyauth.Record{KeyID: rec.KeyID, BuyerID: rec.BuyerID, Platform: rec.Platform, Status: rec.Status}, true
}

type usageBody struct {
	RequestID        string `json:"request_id"`
	ProxyKeyID       string `json:"proxy_key_id"`
	APIKeyID         string `json:"api_key_id"`
	BuyerID          string `json:"buyer_id"`
	SellerID         string `json:"seller_id"`
	Platform         string `json:"platform"`
	Model            string `json:"model"`
	PromptTokens     *int   `json:"prompt_tokens"`
	CompletionTokens *int   `json:"completion_tokens"`
	TotalTokens      *int   `json:"total_tokens"`
	UsageSource      string `json:"usage_source"`
	Partial          bool   `json:"partial"`
	LatencyMS        int64  `json:"latency_ms"`
	StatusCode       int    `json:"status_code"`
	EndReason        string `json:"end_reason"`
}

// Observe 实现 usageobs.Sink。用独立超时，避免取消的请求上下文丢掉计量。
func (c *Client) Observe(ctx context.Context, obs usageobs.Observation) error {
	if !c.enabled() {
		return fmt.Errorf("api client disabled")
	}
	_ = ctx
	cctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	resp, err := c.do(cctx, http.MethodPost, "/internal/v1/usage-observations", usageBody{
		RequestID: obs.RequestID, ProxyKeyID: obs.ProxyKeyID, APIKeyID: obs.APIKeyID,
		BuyerID: obs.BuyerID, SellerID: obs.SellerID, Platform: obs.Platform, Model: obs.Model,
		PromptTokens: obs.PromptTokens, CompletionTokens: obs.CompletionTokens, TotalTokens: obs.TotalTokens,
		UsageSource: obs.UsageSource, Partial: obs.Partial, LatencyMS: obs.LatencyMS,
		StatusCode: obs.StatusCode, EndReason: obs.EndReason,
	})
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("usage persist status %d", resp.StatusCode)
	}
	return nil
}

// PatchHealth 实现 keyhealth.HealthSink。
func (c *Client) PatchHealth(ctx context.Context, id, health string) error {
	if !c.enabled() {
		return nil
	}
	resp, err := c.do(ctx, http.MethodPost, "/internal/v1/seller-keys/"+url.PathEscape(id)+"/health", map[string]string{"health_state": health})
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("health patch status %d", resp.StatusCode)
	}
	return nil
}

// CompositeStore 先查静态 Map，未命中再查 API（本地夹具 + 事实源）。
type CompositeStore struct {
	Static proxyauth.Store
	Remote proxyauth.Store
}

func (s CompositeStore) Lookup(hashHex string) (proxyauth.Record, bool) {
	if s.Static != nil {
		if rec, ok := s.Static.Lookup(hashHex); ok {
			return rec, true
		}
	}
	if s.Remote != nil {
		return s.Remote.Lookup(hashHex)
	}
	return proxyauth.Record{}, false
}

// FanoutSink 内存幂等 + 远程持久化。远程失败不阻断调用方（由 DurableSink 保留文件）。
type FanoutSink struct {
	Mem    *usageobs.MemorySink
	Remote usageobs.Sink
}

func (f FanoutSink) Observe(ctx context.Context, obs usageobs.Observation) error {
	if f.Mem != nil {
		_ = f.Mem.Observe(ctx, obs)
	}
	if f.Remote != nil {
		return f.Remote.Observe(ctx, obs)
	}
	return nil
}
