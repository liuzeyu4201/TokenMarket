// Package score ranks SF23-qualified connections on health, latency, capacity, and price.
package score

import (
	"encoding/json"
	"math/rand"
	"sort"
)

const ScoringVersion = "1.0.0"

// Policy is an immutable routing policy version.
type Policy struct {
	Version        string
	WeightHealth   int
	WeightLatency  int
	WeightCapacity int
	WeightPrice    int
	ExploreBPS     int // 0 = greedy argmax
}

func (p Policy) withDefaults() Policy {
	if p.Version == "" {
		p.Version = ScoringVersion
	}
	if p.WeightHealth == 0 && p.WeightLatency == 0 && p.WeightCapacity == 0 && p.WeightPrice == 0 {
		p.WeightHealth, p.WeightLatency, p.WeightCapacity, p.WeightPrice = 1, 1, 1, 1
	}
	return p
}

// EffectiveVersion is the policy version used for replay after defaults.
func (p Policy) EffectiveVersion() string {
	return p.withDefaults().Version
}

// Signals are observed inputs. Missing optional fields use conservative zeros.
type Signals struct {
	ConnectionID    string
	Health          string
	LatencyMS       int
	LatencyPresent  bool
	Remaining       int
	Declared        int
	CapacityPresent bool
	SellerBPS       int
	PricePresent    bool
}

// Row is one scored candidate.
type Row struct {
	ConnectionID string `json:"connection_id"`
	Health       int    `json:"health"`
	Latency      int    `json:"latency"`
	Capacity     int    `json:"capacity"`
	Price        int    `json:"price"`
	Total        int    `json:"total"`
	Reason       string `json:"reason,omitempty"`
}

func clamp(n int) int {
	if n < 0 {
		return 0
	}
	if n > 10000 {
		return 10000
	}
	return n
}

func healthFactor(s Signals) int {
	switch s.Health {
	case "healthy":
		return 10000
	case "degraded":
		return 5000
	default:
		return 0
	}
}

func latencyFactor(s Signals) int {
	if !s.LatencyPresent {
		return 0
	}
	return clamp(10000 - s.LatencyMS)
}

func capacityFactor(s Signals) int {
	if !s.CapacityPresent || s.Declared <= 0 || s.Remaining <= 0 {
		return 0
	}
	return clamp(s.Remaining * 10000 / s.Declared)
}

func priceFactor(s Signals) int {
	if !s.PricePresent {
		return 0
	}
	return clamp(20000 - s.SellerBPS)
}

func scoreOne(s Signals, p Policy) Row {
	h, l, c, pr := healthFactor(s), latencyFactor(s), capacityFactor(s), priceFactor(s)
	total := h*p.WeightHealth + l*p.WeightLatency + c*p.WeightCapacity + pr*p.WeightPrice
	reason := "argmax"
	return Row{
		ConnectionID: s.ConnectionID,
		Health:       h,
		Latency:      l,
		Capacity:     c,
		Price:        pr,
		Total:        total,
		Reason:       reason,
	}
}

// Rank scores only the provided qualified IDs. Unknown IDs are skipped.
func Rank(qualified []string, signals map[string]Signals, p Policy, seed int64) []Row {
	p = p.withDefaults()
	rows := make([]Row, 0, len(qualified))
	for _, id := range qualified {
		s, ok := signals[id]
		if !ok {
			s = Signals{ConnectionID: id} // all conservative zeros
		}
		s.ConnectionID = id
		rows = append(rows, scoreOne(s, p))
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if rows[i].Total != rows[j].Total {
			return rows[i].Total > rows[j].Total
		}
		return rows[i].ConnectionID < rows[j].ConnectionID
	})
	if len(rows) == 0 {
		return rows
	}
	if p.ExploreBPS > 0 && seed != 0 {
		pick := weightedPick(rows, p.ExploreBPS, seed)
		for i := range rows {
			if rows[i].ConnectionID == pick {
				rows[i].Reason = "explore"
				if i != 0 {
					rows[0], rows[i] = rows[i], rows[0]
				}
				break
			}
		}
	} else {
		rows[0].Reason = "argmax"
	}
	return rows
}

func weightedPick(rows []Row, exploreBPS int, seed int64) string {
	if len(rows) == 1 {
		return rows[0].ConnectionID
	}
	rng := rand.New(rand.NewSource(seed))
	// Mix greedy vs weight-by-total using exploreBPS/10000.
	if rng.Intn(10000) >= exploreBPS {
		return rows[0].ConnectionID
	}
	var sum int64
	for _, r := range rows {
		w := r.Total
		if w < 1 {
			w = 1
		}
		sum += int64(w)
	}
	x := rng.Int63n(sum)
	var acc int64
	for _, r := range rows {
		w := r.Total
		if w < 1 {
			w = 1
		}
		acc += int64(w)
		if x < acc {
			return r.ConnectionID
		}
	}
	return rows[0].ConnectionID
}

// Winner returns the first ranked ID or empty.
func Winner(rows []Row) string {
	if len(rows) == 0 {
		return ""
	}
	return rows[0].ConnectionID
}

// Decision is a replayable ranking snapshot (policy version + seed + scores).
type Decision struct {
	PolicyVersion string `json:"policy_version"`
	Seed          int64  `json:"seed"`
	Winner        string `json:"winner"`
	Reason        string `json:"reason,omitempty"`
	Rows          []Row  `json:"scores"`
}

// Decide ranks qualified IDs and records policy version, seed, and win reason.
func Decide(qualified []string, signals map[string]Signals, p Policy, seed int64) Decision {
	p = p.withDefaults()
	rows := Rank(qualified, signals, p, seed)
	d := Decision{
		PolicyVersion: p.Version,
		Seed:          seed,
		Winner:        Winner(rows),
		Rows:          rows,
	}
	if len(rows) > 0 {
		d.Reason = rows[0].Reason
	}
	return d
}

// ReplayJSON is a stable encoding of ranking rows.
func ReplayJSON(rows []Row) []byte {
	b, _ := json.Marshal(rows)
	return b
}

// ReplayDecisionJSON is a stable encoding of a full decision snapshot.
func ReplayDecisionJSON(d Decision) []byte {
	b, _ := json.Marshal(d)
	return b
}
