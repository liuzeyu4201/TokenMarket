package usageobs

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

var (
	// ErrWAL is returned when a durable write cannot be completed.
	ErrWAL = errors.New("usage wal write failed")
	// ErrBackpressure is returned when the WAL quota is exhausted.
	ErrBackpressure = errors.New("usage wal quota exceeded")
)

const (
	defaultMaxBytes    int64 = 64 << 20
	defaultMaxFiles          = 10000
	defaultReplayEvery       = 2 * time.Second
)

// DurableSink 可选地把观察写入本地 JSON 再投递 Next。Dir 仅为可丢弃缓存，
// 不是账务事实源；Dir 为空则只调用 Next。启动不得依赖 Replay 本地文件。
type DurableSink struct {
	Dir         string
	Next        Sink
	MaxBytes    int64
	MaxFiles    int
	ReplayEvery time.Duration
	mkdirAll    func(string, os.FileMode) error
	writeFile   func(string, []byte, os.FileMode) error
	mu          sync.Mutex
}

func (d *DurableSink) mkdir(path string, mode os.FileMode) error {
	if d != nil && d.mkdirAll != nil {
		return d.mkdirAll(path, mode)
	}
	return os.MkdirAll(path, mode)
}

func (d *DurableSink) write(path string, data []byte, mode os.FileMode) error {
	if d != nil && d.writeFile != nil {
		return d.writeFile(path, data, mode)
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, mode); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func (d *DurableSink) maxBytes() int64 {
	if d.MaxBytes > 0 {
		return d.MaxBytes
	}
	return defaultMaxBytes
}

func (d *DurableSink) maxFiles() int {
	if d.MaxFiles > 0 {
		return d.MaxFiles
	}
	return defaultMaxFiles
}

func (d *DurableSink) quota() (files int, bytes int64, err error) {
	ents, err := os.ReadDir(d.Dir)
	if err != nil {
		if os.IsNotExist(err) {
			return 0, 0, nil
		}
		return 0, 0, err
	}
	for _, e := range ents {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		files++
		bytes += info.Size()
	}
	return files, bytes, nil
}

func (d *DurableSink) Observe(ctx context.Context, obs Observation) error {
	if d == nil {
		return nil
	}
	if d.Dir != "" && obs.RequestID != "" {
		if err := d.mkdir(d.Dir, 0o700); err != nil {
			return errors.Join(ErrWAL, err)
		}
		files, bytes, err := d.quota()
		if err != nil {
			return errors.Join(ErrWAL, err)
		}
		if files >= d.maxFiles() || bytes >= d.maxBytes() {
			return ErrBackpressure
		}
		b, err := json.Marshal(obs)
		if err != nil {
			return errors.Join(ErrWAL, err)
		}
		if err := d.write(d.path(obs.RequestID), b, 0o600); err != nil {
			return errors.Join(ErrWAL, err)
		}
	}
	if d.Next == nil {
		return nil
	}
	err := d.Next.Observe(ctx, obs)
	if err == nil && d.Dir != "" && obs.RequestID != "" {
		_ = os.Remove(d.path(obs.RequestID))
	}
	return err
}

func (d *DurableSink) path(id string) string {
	safe := strings.Map(func(r rune) rune {
		if r == '/' || r == '\\' || r == '.' {
			return '_'
		}
		return r
	}, id)
	return filepath.Join(d.Dir, safe+".json")
}

// Replay 投递目录中尚未确认的观察。
func (d *DurableSink) Replay(ctx context.Context) int {
	if d == nil || d.Dir == "" || d.Next == nil {
		return 0
	}
	ents, err := os.ReadDir(d.Dir)
	if err != nil {
		return 0
	}
	n := 0
	for _, e := range ents {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		b, err := os.ReadFile(filepath.Join(d.Dir, e.Name()))
		if err != nil {
			continue
		}
		var obs Observation
		if json.Unmarshal(b, &obs) != nil {
			continue
		}
		if d.Next.Observe(ctx, obs) == nil {
			_ = os.Remove(filepath.Join(d.Dir, e.Name()))
			n++
		}
	}
	return n
}

// RunReplay retries undelivered WAL files until ctx is cancelled.
func (d *DurableSink) RunReplay(ctx context.Context) {
	if d == nil || d.Dir == "" {
		return
	}
	every := d.ReplayEvery
	if every <= 0 {
		every = defaultReplayEvery
	}
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	d.Replay(ctx)
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			d.Replay(ctx)
		}
	}
}

// InjectFS is used by tests to force mkdir/write failures.
func (d *DurableSink) InjectFS(
	mkdir func(string, os.FileMode) error,
	write func(string, []byte, os.FileMode) error,
) {
	if d == nil {
		return
	}
	d.mu.Lock()
	d.mkdirAll = mkdir
	d.writeFile = write
	d.mu.Unlock()
}
