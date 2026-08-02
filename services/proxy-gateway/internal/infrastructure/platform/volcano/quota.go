package volcano

import (
	"context"
	"fmt"
)

// QuotaInfo 可信额度读结果。
type QuotaInfo struct {
	// Available false → 调用方应产出 quota_unavailable
	Available bool
	// Amount 精确十进制/整数字符串；仅 Available 时有意义
	Amount string
	Unit   string
}

// QuotaReader 额度读端口。
type QuotaReader interface {
	ReadQuota(ctx context.Context, apiKey string) (QuotaInfo, error)
}

// NoopQuotaReader V0.1 默认：无 Key 作用域官方额度 API。
type NoopQuotaReader struct{}

// ReadQuota 恒定不可用（不得返回金额 0）。
func (NoopQuotaReader) ReadQuota(ctx context.Context, apiKey string) (QuotaInfo, error) {
	_ = ctx
	_ = apiKey
	return QuotaInfo{Available: false}, nil
}

// StubQuotaReader 测试用可注入额度。
type StubQuotaReader struct {
	Info QuotaInfo
	Err  error
}

// ReadQuota 返回预设。
func (s StubQuotaReader) ReadQuota(ctx context.Context, apiKey string) (QuotaInfo, error) {
	_ = ctx
	_ = apiKey
	if s.Err != nil {
		return QuotaInfo{}, s.Err
	}
	return s.Info, nil
}

// NewPositiveStub 构造正额度 stub。
func NewPositiveStub(amount, unit string) StubQuotaReader {
	return StubQuotaReader{Info: QuotaInfo{Available: true, Amount: amount, Unit: unit}}
}

// NewZeroStub 构造官方明确零额度。
func NewZeroStub(unit string) StubQuotaReader {
	return StubQuotaReader{Info: QuotaInfo{Available: true, Amount: "0", Unit: unit}}
}

// ErrQuota 测试错误。
var ErrQuota = fmt.Errorf("quota read failed")
