package volcano

import (
	"bytes"
	"context"
	"errors"
	"io"
	"net/http"
	"strings"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

const DefaultMaxResponseBytes int64 = 2 << 20

var ErrResponseTooLarge = errors.New("provider response exceeds configured limit")

// ChatCallResult 一次非流式出站。
type ChatCallResult struct {
	Status     int
	Body       []byte
	RetryAfter string
	Headers    http.Header
	Err        error
}

// ChatClient 火山 Chat Completions。生成路径 MaxAttempts=1。
type ChatClient struct {
	BaseURL          string
	HTTPClient       *http.Client
	MaxAttempts      int
	MaxResponseBytes int64
}

func (c *ChatClient) maxResponse() int64 {
	if c != nil && c.MaxResponseBytes > 0 {
		return c.MaxResponseBytes
	}
	return DefaultMaxResponseBytes
}

func NewChatClient(baseURL string) *ChatClient {
	return &ChatClient{
		BaseURL:     strings.TrimRight(baseURL, "/"),
		HTTPClient:  &http.Client{Timeout: 0},
		MaxAttempts: 1,
	}
}

func (c *ChatClient) url() string {
	return c.BaseURL + "/chat/completions"
}

// PostJSON 非流式 POST。仅设置允许列表头。
func (c *ChatClient) PostJSON(ctx context.Context, apiKey string, body []byte, stream bool) ChatCallResult {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.url(), bytes.NewReader(body))
	if err != nil {
		return ChatCallResult{Err: err}
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")
	if stream {
		req.Header.Set("Accept", "text/event-stream")
	} else {
		req.Header.Set("Accept", "application/json")
	}
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return ChatCallResult{Err: err}
	}
	defer resp.Body.Close()
	limit := c.maxResponse()
	b, err := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	if err != nil {
		return ChatCallResult{Status: resp.StatusCode, Err: err, Headers: resp.Header}
	}
	if int64(len(b)) > limit {
		return ChatCallResult{Status: resp.StatusCode, Err: ErrResponseTooLarge, Headers: resp.Header}
	}
	return ChatCallResult{
		Status:     resp.StatusCode,
		Body:       b,
		RetryAfter: resp.Header.Get("Retry-After"),
		Headers:    resp.Header,
	}
}

// PostStream 打开流式响应。调用方负责 Close。不在此 ReadAll。
func (c *ChatClient) PostStream(ctx context.Context, apiKey string, body []byte) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.url(), bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	return c.HTTPClient.Do(req)
}

// OutboundHeaderNames 已设置的出站头名（测试）。
func OutboundAllowedHeaders() []string {
	return []string{"Authorization", "Content-Type", "Accept"}
}

func ClassifyCall(res ChatCallResult) chatcompat.ErrorCategory {
	if res.Err != nil {
		return chatcompat.ClassifyTransport(res.Err)
	}
	if res.Status == http.StatusOK {
		return ""
	}
	return chatcompat.ClassifyHTTP(res.Status, res.Body)
}
