package runtimesnap

import (
	"sync/atomic"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

// Snapshot 不可变运行快照（目录 + 世代）。切换时整体替换。
type Snapshot struct {
	ID           string
	Generation   uint64
	CatalogMajor int
	Catalog      *endpcatalog.Catalog
}

// Holder 原子发布快照。
type Holder struct {
	cur atomic.Pointer[Snapshot]
	gen atomic.Uint64
}

func (h *Holder) Current() *Snapshot {
	if h == nil {
		return nil
	}
	return h.cur.Load()
}

// Swap 发布新快照。catalog 必须已通过主版本校验。
func (h *Holder) Swap(id string, cat *endpcatalog.Catalog) (*Snapshot, error) {
	if cat == nil {
		return nil, &endpcatalog.LoadError{Code: endpcatalog.CodeLoadFailed, Message: "nil catalog"}
	}
	if err := endpcatalog.Validate(cat); err != nil {
		return nil, err
	}
	gen := h.gen.Add(1)
	snap := &Snapshot{
		ID:           id,
		Generation:   gen,
		CatalogMajor: cat.CatalogMajor,
		Catalog:      cat,
	}
	h.cur.Store(snap)
	return snap, nil
}

// Pin 返回进入时锁定的快照指针；切换后仍指向旧对象。
func (h *Holder) Pin() *Snapshot {
	return h.Current()
}
