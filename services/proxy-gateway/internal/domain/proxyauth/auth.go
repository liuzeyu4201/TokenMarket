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
	KeyID        string
	BuyerID      string
	Platform     string
	Status       string
	ProjectID    string
	ProjectMode  string
	PreviewOptIn bool
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
	Pepper  []byte
	Store   Store
	Limiter *AdmissionLimiter
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
	if len(rest) < 32 || len(rest) > 256 {
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
	rec, st := a.AuthenticateStatus(authorization)
	return rec, st == AuthOK
}

func (a Authenticator) AuthenticateStatus(authorization string) (Record, AuthStatus) {
	sec := ParseBearer(authorization)
	if sec == "" || !ValidProxySecret(sec) {
		return Record{}, AuthInvalid
	}
	if a.Store == nil {
		return Record{}, AuthInvalid
	}
	hash := HashSecret(a.Pepper, sec)
	if a.Limiter != nil && a.Limiter.CachedHit(hash) {
		rec, ok := a.lookup(hash)
		if ok && rec.Status == "active" {
			return rec, AuthOK
		}
		a.Limiter.RememberMiss(hash)
		return Record{}, AuthInvalid
	}
	if a.Limiter != nil && a.Limiter.CachedMiss(hash) {
		return Record{}, AuthInvalid
	}

	// Uncached secrets consume the miss bucket. Previously authenticated
	// buyers are served from the positive cache and retain capacity.
	if a.Limiter != nil && !a.Limiter.AllowLookup() {
		return Record{}, AuthOverload
	}
	if a.Limiter != nil {
		defer a.Limiter.FinishLookup()
	}

	if rs, ok := a.Store.(ResultStore); ok {
		rec, st := rs.LookupResult(hash)
		switch st {
		case LookupUnavailable:
			return Record{}, AuthInvalid
		case LookupMiss:
			if a.Limiter != nil {
				a.Limiter.RememberMiss(hash)
			}
			return Record{}, AuthInvalid
		default:
			if rec.Status != "active" {
				return Record{}, AuthInvalid
			}
			if a.Limiter != nil {
				a.Limiter.RememberHit(hash)
			}
			return rec, AuthOK
		}
	}
	rec, ok := a.Store.Lookup(hash)
	if !ok || rec.Status != "active" {
		if a.Limiter != nil && !ok {
			a.Limiter.RememberMiss(hash)
		}
		return Record{}, AuthInvalid
	}
	if a.Limiter != nil {
		a.Limiter.RememberHit(hash)
	}
	return rec, AuthOK
}

func (a Authenticator) lookup(hash string) (Record, bool) {
	if rs, ok := a.Store.(ResultStore); ok {
		rec, st := rs.LookupResult(hash)
		return rec, st == LookupHit
	}
	return a.Store.Lookup(hash)
}
