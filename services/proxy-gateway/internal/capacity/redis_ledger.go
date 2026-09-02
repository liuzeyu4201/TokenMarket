package capacity

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"strings"
	"time"
)

// RedisCachedLedger write-through caches in-flight reservations. Redis is not SoR:
// Lookup still consults the inner ledger after a cache miss (restart).
type RedisCachedLedger struct {
	Inner *MemLedger
	Addr  string
}

func (l *RedisCachedLedger) Reserve(ctx context.Context, requestID, projectID, keyID string, amount int64) error {
	if err := l.Inner.Reserve(ctx, requestID, projectID, keyID, amount); err != nil {
		return err
	}
	_, _ = redisDo(l.Addr, "SET", "res:"+requestID, "1")
	return nil
}

func (l *RedisCachedLedger) Abort(ctx context.Context, requestID string) error {
	_, _ = redisDo(l.Addr, "DEL", "res:"+requestID)
	return l.Inner.Abort(ctx, requestID)
}

func (l *RedisCachedLedger) Settle(requestID string) {
	l.Inner.Settle(requestID)
	_, _ = redisDo(l.Addr, "DEL", "res:"+requestID)
}

func redisDo(addr string, args ...string) (string, error) {
	if addr == "" {
		return "", fmt.Errorf("redis addr empty")
	}
	conn, err := net.DialTimeout("tcp", addr, 800*time.Millisecond)
	if err != nil {
		return "", err
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(800 * time.Millisecond))
	var b strings.Builder
	fmt.Fprintf(&b, "*%d\r\n", len(args))
	for _, a := range args {
		fmt.Fprintf(&b, "$%d\r\n%s\r\n", len(a), a)
	}
	if _, err := conn.Write([]byte(b.String())); err != nil {
		return "", err
	}
	r := bufio.NewReader(conn)
	line, err := r.ReadString('\n')
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(line), nil
}
