package proxyauth

import (
	"encoding/hex"
	"errors"
	"strings"
)

const minSharedSecretBytes = 32

var (
	ErrSecretMissing    = errors.New("shared secret missing")
	ErrSecretMalformed  = errors.New("shared secret malformed")
	ErrSecretUndersized = errors.New("shared secret undersized")
)

// LoadSharedSecret fails closed: no process-local random keys and no zero-pad.
func LoadSharedSecret(raw string) ([]byte, error) {
	text := strings.TrimSpace(raw)
	if text == "" {
		return nil, ErrSecretMissing
	}
	if isHex(text) {
		if len(text)%2 != 0 {
			return nil, ErrSecretMalformed
		}
		decoded, err := hex.DecodeString(text)
		if err != nil {
			return nil, ErrSecretMalformed
		}
		if len(decoded) < minSharedSecretBytes {
			return nil, ErrSecretUndersized
		}
		return decoded, nil
	}
	encoded := []byte(text)
	if len(encoded) < minSharedSecretBytes {
		return nil, ErrSecretUndersized
	}
	return encoded, nil
}

func isHex(s string) bool {
	if s == "" {
		return false
	}
	for _, c := range s {
		switch {
		case c >= '0' && c <= '9', c >= 'a' && c <= 'f', c >= 'A' && c <= 'F':
		default:
			return false
		}
	}
	return true
}
