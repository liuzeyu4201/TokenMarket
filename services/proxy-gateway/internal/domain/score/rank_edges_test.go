package score_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
)

func TestEffectiveVersionDefaults(t *testing.T) {
	if (score.Policy{}).EffectiveVersion() != score.ScoringVersion {
		t.Fatal("empty version")
	}
	if (score.Policy{Version: "9.9.9"}).EffectiveVersion() != "9.9.9" {
		t.Fatal("explicit version")
	}
}

func TestRankClampsAndExplorePick(t *testing.T) {
	policy := score.Policy{
		Version:        "1.0.0",
		WeightHealth:   1,
		WeightLatency:  1,
		WeightCapacity: 1,
		WeightPrice:    1,
		ExploreBPS:     10000,
	}
	signals := map[string]score.Signals{
		"low": {
			ConnectionID:    "low",
			Health:          "healthy",
			LatencyPresent:  true,
			LatencyMS:       -50,
			CapacityPresent: true,
			Remaining:       1,
			Declared:        1,
			PricePresent:    true,
			SellerBPS:       30000,
		},
		"high": {
			ConnectionID:    "high",
			Health:          "degraded",
			LatencyPresent:  true,
			LatencyMS:       5,
			CapacityPresent: true,
			Remaining:       0,
			Declared:        10,
			PricePresent:    true,
			SellerBPS:       100,
		},
	}
	rows := score.Rank([]string{"low", "high", "missing"}, signals, policy, 7)
	if len(rows) != 3 {
		t.Fatalf("rows %d", len(rows))
	}
	id := score.Winner(rows)
	if id == "" {
		t.Fatal("winner")
	}
	if score.Winner(nil) != "" {
		t.Fatal("empty winner")
	}
	dec := score.Decide([]string{"low", "high"}, signals, policy, 42)
	if dec.PolicyVersion != "1.0.0" {
		t.Fatal(dec.PolicyVersion)
	}
}
