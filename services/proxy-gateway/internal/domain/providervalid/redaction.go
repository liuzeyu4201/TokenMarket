package providervalid

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// CredentialRef 对 api_key 做 HMAC-SHA256 短引用（不可逆），用于闸门分桶与遥测。
func CredentialRef(apiKey, secret string) string {
	if secret == "" {
		secret = "providervalid-dev-only-gate-secret"
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write([]byte(apiKey))
	sum := mac.Sum(nil)
	return hex.EncodeToString(sum[:8])
}

// ContainsSecret 粗检字符串是否含完整 key（用于日志/错误负向测试）。
func ContainsSecret(haystack, secret string) bool {
	if secret == "" || len(secret) < 8 {
		return false
	}
	return strings.Contains(haystack, secret)
}

// RedactString 若文本含 key 则替换为占位。
func RedactString(s, apiKey string) string {
	if apiKey == "" || !strings.Contains(s, apiKey) {
		return s
	}
	return strings.ReplaceAll(s, apiKey, "[REDACTED_CREDENTIAL]")
}
