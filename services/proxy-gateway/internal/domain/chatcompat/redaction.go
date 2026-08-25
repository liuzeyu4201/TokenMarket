package chatcompat

import "github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"

// CredentialRef 不可逆短引用。
func CredentialRef(apiKey, secret string) string {
	return providervalid.CredentialRef(apiKey, secret)
}

// RedactString 脱敏完整 Key。
func RedactString(s, apiKey string) string {
	return providervalid.RedactString(s, apiKey)
}

// ContainsSecret 是否含完整密钥。
func ContainsSecret(haystack, secret string) bool {
	return providervalid.ContainsSecret(haystack, secret)
}

// RedactBody 同时去掉 Key 与超长正文片段（日志用）。
func RedactBody(s, apiKey string) string {
	s = RedactString(s, apiKey)
	if len(s) > 512 {
		return s[:512] + "[truncated]"
	}
	return s
}
