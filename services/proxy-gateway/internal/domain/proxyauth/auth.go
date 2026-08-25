// Package proxyauth 校验买家代理 Key（SF11）。V0.1：pepper HMAC 查找。
package proxyauth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// Record 已签发代理 Key 元数据。
type Record struct {
	KeyID    string
	BuyerID  string
	Platform string
	Status   string
}

// Store 查找哈希。
type Store interface {
	Lookup(hashHex string) (Record, bool)
}

// MapStore 进程内哈希表（静态夹具）。
type MapStore struct {
	Records map[string]Record
}

func (m MapStore) Lookup(hashHex string) (Record, bool) {
	if m.Records == nil {
		return Record{}, false
	}
	r, ok := m.Records[hashHex]
	return r, ok
}

// Authenticator Bearer 认证。
type Authenticator struct {
	Pepper []byte
	Store  Store
}

func HashSecret(pepper []byte, secret string) string {
	mac := hmac.New(sha256.New, pepper)
	_, _ = mac.Write([]byte(secret))
	return hex.EncodeToString(mac.Sum(nil))
}

// ValidProxySecret 校验 tmk- 前缀与 ≥128 bit 随机部分（hex 至少 32 字符）。
func ValidProxySecret(secret string) bool {
	if !strings.HasPrefix(secret, "tmk-") {
		return false
	}
	rest := secret[4:]
	if len(rest) < 32 {
		return false
	}
	for _, c := range rest {
		switch {
		case c >= '0' && c <= '9', c >= 'a' && c <= 'f', c >= 'A' && c <= 'F':
		default:
			return false
		}
	}
	return true
}

func ParseBearer(header string) string {
	h := strings.TrimSpace(header)
	if len(h) < 8 || !strings.EqualFold(h[:7], "bearer ") {
		return ""
	}
	return strings.TrimSpace(h[7:])
}

func (a Authenticator) Authenticate(authorization string) (Record, bool) {
	sec := ParseBearer(authorization)
	if sec == "" || !ValidProxySecret(sec) {
		return Record{}, false
	}
	if a.Store == nil {
		return Record{}, false
	}
	rec, ok := a.Store.Lookup(HashSecret(a.Pepper, sec))
	if !ok || rec.Status != "active" {
		return Record{}, false
	}
	return rec, true
}
