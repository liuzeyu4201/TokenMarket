package capacity

import (
	"fmt"
	"math/rand"
)

type Tenant struct {
	BuyerID   string
	ProjectID string
	KeyID     string
	Protocol  string
}

var protocols = []string{"openai", "anthropic", "vertex"}

func Dataset(seed int64, n int) []Tenant {
	rng := rand.New(rand.NewSource(seed))
	out := make([]Tenant, n)
	seen := map[string]struct{}{}
	for i := 0; i < n; i++ {
		id := fmt.Sprintf("b-%d-%d", seed, rng.Int63())
		for _, ok := seen[id]; ok; _, ok = seen[id] {
			id = fmt.Sprintf("b-%d-%d", seed, rng.Int63())
		}
		seen[id] = struct{}{}
		out[i] = Tenant{
			BuyerID:   id,
			ProjectID: fmt.Sprintf("p-%s", id),
			KeyID:     fmt.Sprintf("k-%s", id),
			Protocol:  protocols[i%len(protocols)],
		}
	}
	return out
}

func (t Tenant) Path() string {
	switch t.Protocol {
	case "anthropic":
		return "/anthropic/v1/messages"
	case "vertex":
		return "/vertex/v1/projects/p/locations/l/publishers/google/models/m:generateContent"
	default:
		return "/openai/v1/chat/completions"
	}
}
