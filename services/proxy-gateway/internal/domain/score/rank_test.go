package score_test

import (
	"bytes"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
)

func baseSig(id string) score.Signals {
	return score.Signals{
		ConnectionID:    id,
		Health:          "healthy",
		LatencyMS:       50,
		LatencyPresent:  true,
		Remaining:       5,
		Declared:        10,
		CapacityPresent: true,
		SellerBPS:       10000,
		PricePresent:    true,
	}
}

func TestMonotonicHealthLatencyCapacityPrice(t *testing.T) {
	p := score.Policy{}
	a := baseSig("a")
	b := baseSig("b")
	ids := []string{"a", "b"}

	t.Run("health", func(t *testing.T) {
		sa, sb := a, b
		sb.Health = "degraded"
		rows := score.Rank(ids, map[string]score.Signals{"a": sa, "b": sb}, p, 0)
		if rows[0].ConnectionID != "a" || rows[0].Health <= rows[1].Health || rows[0].Total <= rows[1].Total {
			t.Fatalf("%+v", rows)
		}
	})
	t.Run("latency", func(t *testing.T) {
		sa, sb := a, b
		sb.LatencyMS = 200
		rows := score.Rank(ids, map[string]score.Signals{"a": sa, "b": sb}, p, 0)
		if rows[0].ConnectionID != "a" || rows[0].Latency <= rows[1].Latency || rows[0].Total <= rows[1].Total {
			t.Fatalf("%+v", rows)
		}
	})
	t.Run("capacity", func(t *testing.T) {
		sa, sb := a, b
		sb.Remaining = 1
		rows := score.Rank(ids, map[string]score.Signals{"a": sa, "b": sb}, p, 0)
		if rows[0].ConnectionID != "a" || rows[0].Capacity <= rows[1].Capacity || rows[0].Total <= rows[1].Total {
			t.Fatalf("%+v", rows)
		}
	})
	t.Run("price", func(t *testing.T) {
		sa, sb := a, b
		sb.SellerBPS = 15000
		rows := score.Rank(ids, map[string]score.Signals{"a": sa, "b": sb}, p, 0)
		if rows[0].ConnectionID != "a" || rows[0].Price <= rows[1].Price || rows[0].Total <= rows[1].Total {
			t.Fatalf("%+v", rows)
		}
	})
}

func TestMissingMetricsConservativeZero(t *testing.T) {
	p := score.Policy{}
	good := baseSig("good")
	missing := score.Signals{ConnectionID: "miss", Health: ""}
	rows := score.Rank([]string{"good", "miss"}, map[string]score.Signals{"good": good, "miss": missing}, p, 0)
	var miss score.Row
	for _, r := range rows {
		if r.ConnectionID == "miss" {
			miss = r
		}
	}
	if miss.Health != 0 || miss.Latency != 0 || miss.Capacity != 0 || miss.Price != 0 {
		t.Fatalf("conservative %+v", miss)
	}
	if score.Winner(rows) != "good" {
		t.Fatalf("winner %s", score.Winner(rows))
	}
}

func TestReplayIdentical(t *testing.T) {
	p := score.Policy{Version: "pol-1"}
	sig := map[string]score.Signals{"a": baseSig("a"), "b": baseSig("b")}
	sig["b"] = func() score.Signals { s := baseSig("b"); s.LatencyMS = 80; return s }()
	r1 := score.Rank([]string{"b", "a"}, sig, p, 7)
	r2 := score.Rank([]string{"b", "a"}, sig, p, 7)
	if !bytes.Equal(score.ReplayJSON(r1), score.ReplayJSON(r2)) {
		t.Fatal("replay mismatch")
	}
	if score.Winner(r1) == "" {
		t.Fatal("empty winner")
	}
}

func TestTieBreakByConnectionID(t *testing.T) {
	p := score.Policy{}
	sig := map[string]score.Signals{"z": baseSig("z"), "a": baseSig("a")}
	rows := score.Rank([]string{"z", "a"}, sig, p, 0)
	if rows[0].ConnectionID != "a" {
		t.Fatalf("%+v", rows)
	}
}

func TestExploreStaysInQualifiedSet(t *testing.T) {
	p := score.Policy{ExploreBPS: 10000}
	sig := map[string]score.Signals{"a": baseSig("a"), "b": baseSig("b")}
	seen := map[string]int{}
	for seed := int64(1); seed <= 200; seed++ {
		rows := score.Rank([]string{"a", "b"}, sig, p, seed)
		w := score.Winner(rows)
		if w != "a" && w != "b" {
			t.Fatalf("out of set %s", w)
		}
		seen[w]++
	}
	if len(seen) == 0 {
		t.Fatal("none")
	}
}

func TestEmptyQualified(t *testing.T) {
	rows := score.Rank(nil, nil, score.Policy{}, 0)
	if score.Winner(rows) != "" {
		t.Fatal(rows)
	}
}

func TestRankOnlyQualifiedIDs(t *testing.T) {
	evil := baseSig("evil")
	evil.LatencyMS = 1
	rows := score.Rank([]string{"good"}, map[string]score.Signals{
		"good": baseSig("good"),
		"evil": evil,
	}, score.Policy{}, 0)
	if len(rows) != 1 || rows[0].ConnectionID != "good" {
		t.Fatalf("%+v", rows)
	}
}

func TestUnknownIDConservativeZeros(t *testing.T) {
	rows := score.Rank([]string{"ghost"}, map[string]score.Signals{"other": baseSig("other")}, score.Policy{}, 0)
	if len(rows) != 1 || rows[0].Total != 0 {
		t.Fatalf("%+v", rows)
	}
}

func TestPolicySwitchOnlyAffectsNewDecisions(t *testing.T) {
	cheap := baseSig("cheap")
	cheap.SellerBPS = 10000
	pricey := baseSig("pricey")
	pricey.SellerBPS = 11000
	pricey.Health = "healthy"
	pricey.LatencyMS = 1
	sig := map[string]score.Signals{"cheap": cheap, "pricey": pricey}
	ids := []string{"cheap", "pricey"}
	p1 := score.Policy{Version: "pol-1", WeightHealth: 1, WeightLatency: 1, WeightCapacity: 1, WeightPrice: 1}
	d1 := score.Decide(ids, sig, p1, 3)
	if d1.PolicyVersion != "pol-1" || d1.Seed != 3 || d1.Winner == "" || d1.Reason == "" {
		t.Fatalf("%+v", d1)
	}
	p2 := score.Policy{Version: "pol-2", WeightHealth: 0, WeightLatency: 100, WeightCapacity: 0, WeightPrice: 0}
	d2 := score.Decide(ids, sig, p2, 3)
	if d2.PolicyVersion != "pol-2" {
		t.Fatalf("new policy %s", d2.PolicyVersion)
	}
	if !bytes.Equal(score.ReplayDecisionJSON(d1), score.ReplayDecisionJSON(d1)) {
		t.Fatal("snapshot mutated")
	}
	if bytes.Equal(score.ReplayDecisionJSON(d1), score.ReplayDecisionJSON(d2)) {
		t.Fatal("v2 must differ from locked v1")
	}
	d1again := score.Decide(ids, sig, p1, 3)
	if !bytes.Equal(score.ReplayDecisionJSON(d1), score.ReplayDecisionJSON(d1again)) {
		t.Fatal("locked policy replay drift")
	}
}

func TestDecideEmpty(t *testing.T) {
	d := score.Decide(nil, nil, score.Policy{Version: "pol-1"}, 9)
	if d.Winner != "" || d.PolicyVersion != "pol-1" || d.Seed != 9 {
		t.Fatalf("%+v", d)
	}
}
