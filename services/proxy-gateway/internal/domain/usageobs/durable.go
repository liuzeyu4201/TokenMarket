package usageobs

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
)

// DurableSink 先把观察写入本地 JSON 文件再投递 Next；成功后删除文件。
// 进程重启时可 Replay 补写。Dir 为空则退化为只调用 Next。
type DurableSink struct {
	Dir  string
	Next Sink
}

func (d *DurableSink) Observe(ctx context.Context, obs Observation) error {
	if d == nil {
		return nil
	}
	if d.Dir != "" && obs.RequestID != "" {
		if err := os.MkdirAll(d.Dir, 0o700); err == nil {
			b, err := json.Marshal(obs)
			if err == nil {
				_ = os.WriteFile(d.path(obs.RequestID), b, 0o600)
			}
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
