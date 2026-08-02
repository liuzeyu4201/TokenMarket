// Package volcano 实现火山方舟数据面 models 探活与额度端口。
package volcano

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

// ModelsResult models 调用结果。
type ModelsResult struct {
	ModelIDs      []string
	Category      providervalid.ErrorCategory
	RetryAfterSec int
	HTTPStatus    int
	AuthOK        bool // HTTP 200 且 body 可解析
}

// ModelsClient 上游 GET /models。
type ModelsClient struct {
	BaseURL      string
	HTTPClient   *http.Client
	DefaultRetry int
	MaxRetry     int
	MaxAttempts  int // 含首次；瞬时错误最多再试 MaxAttempts-1
}

// NewModelsClient 构造客户端。
func NewModelsClient(baseURL string, defaultRetry, maxRetry int) *ModelsClient {
	return &ModelsClient{
		BaseURL: strings.TrimRight(baseURL, "/"),
		HTTPClient: &http.Client{
			// 单次请求超时由 context 控制；Transport 默认
			Timeout: 0,
		},
		DefaultRetry: defaultRetry,
		MaxRetry:     maxRetry,
		MaxAttempts:  2,
	}
}

// ListModels 调用 GET {base}/models。
func (c *ModelsClient) ListModels(ctx context.Context, apiKey string) ModelsResult {
	if c.MaxAttempts < 1 {
		c.MaxAttempts = 1
	}
	var last ModelsResult
	for attempt := 1; attempt <= c.MaxAttempts; attempt++ {
		last = c.listModelsOnce(ctx, apiKey)
		if last.Category != providervalid.CategoryTemporaryUnavailable {
			return last
		}
		// 仅瞬时网络类重试；不重试 4xx/429/timeout 已分类
		if attempt == c.MaxAttempts {
			break
		}
		if ctx.Err() != nil {
			return ModelsResult{Category: providervalid.ClassifyTransportError(ctx.Err())}
		}
	}
	return last
}

func (c *ModelsClient) listModelsOnce(ctx context.Context, apiKey string) ModelsResult {
	url := c.BaseURL + "/models"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return ModelsResult{Category: providervalid.CategoryTemporaryUnavailable}
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Accept", "application/json")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return ModelsResult{Category: providervalid.ClassifyTransportError(err)}
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if err != nil {
		return ModelsResult{
			HTTPStatus: resp.StatusCode,
			Category:   providervalid.CategoryTemporaryUnavailable,
		}
	}

	if resp.StatusCode != http.StatusOK {
		cat := providervalid.ClassifyHTTPStatus(resp.StatusCode)
		ra := 0
		if cat == providervalid.CategoryRateLimited {
			ra = providervalid.ParseRetryAfter(resp.Header.Get("Retry-After"), c.DefaultRetry, c.MaxRetry)
		}
		return ModelsResult{
			HTTPStatus:    resp.StatusCode,
			Category:      cat,
			RetryAfterSec: ra,
		}
	}

	ids, perr := parseModelsBody(body)
	if perr != nil {
		return ModelsResult{
			HTTPStatus: resp.StatusCode,
			Category:   providervalid.CategoryInvalidResponse,
		}
	}
	return ModelsResult{
		ModelIDs:   ids,
		HTTPStatus: resp.StatusCode,
		Category:   "", // 成功解析，由编排决定后续
		AuthOK:     true,
	}
}

type modelsEnvelope struct {
	Data []struct {
		ID string `json:"id"`
	} `json:"data"`
}

func parseModelsBody(body []byte) ([]string, error) {
	var env modelsEnvelope
	if err := json.Unmarshal(body, &env); err != nil {
		return nil, err
	}
	// data 必须是数组（json null 会失败；缺省为 nil slice 视为空列表 OK）
	if env.Data == nil && !jsonHasDataArray(body) {
		// 允许 "data": []
		var raw map[string]json.RawMessage
		if err := json.Unmarshal(body, &raw); err != nil {
			return nil, err
		}
		d, ok := raw["data"]
		if !ok {
			return nil, fmt.Errorf("missing data")
		}
		var arr []json.RawMessage
		if err := json.Unmarshal(d, &arr); err != nil {
			return nil, fmt.Errorf("data not array")
		}
	}
	ids := make([]string, 0, len(env.Data))
	for _, m := range env.Data {
		if strings.TrimSpace(m.ID) != "" {
			ids = append(ids, m.ID)
		}
	}
	return ids, nil
}

func jsonHasDataArray(body []byte) bool {
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(body, &raw); err != nil {
		return false
	}
	d, ok := raw["data"]
	if !ok {
		return false
	}
	var arr []json.RawMessage
	return json.Unmarshal(d, &arr) == nil
}

// Sleep 可测钩子（重试间隔）；默认 no-op 小睡由 context 控制。
var Sleep = func(ctx context.Context, d time.Duration) {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
	case <-t.C:
	}
}
