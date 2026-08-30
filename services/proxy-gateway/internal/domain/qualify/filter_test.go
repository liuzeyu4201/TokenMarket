package qualify_test

import (
	"bytes"
	"math/rand"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
)

func okCand(id string) qualify.Candidate {
	return qualify.Candidate{
		ConnectionID:     id,
		SellerOwnerID:    "seller-" + id,
		Provider:         "openai",
		Protocol:         "openai",
		SupplyMode:       "shared",
		Lifecycle:        "listed",
		Health:           "healthy",
		Region:           "us",
		Models:           []string{"gpt-test"},
		EndpointIDs:      []string{"openai.post.v1.chat.completions"},
		DeclaredCapacity: 8,
		AdmitsNew:        true,
		PriceValid:       true,
	}
}

func req() qualify.Request {
	return qualify.Request{
		BuyerOwnerID:    "buyer-1",
		ProjectMode:     "shared",
		Provider:        "openai",
		Protocol:        "openai",
		EndpointID:      "openai.post.v1.chat.completions",
		Model:           "gpt-test",
		Region:          "us",
		SnapshotVersion: "snap-1",
	}
}

func TestEachHardGate(t *testing.T) {
	r := req()
	cases := []struct {
		name string
		mut  func(*qualify.Candidate)
		code string
	}{
		{"dedicated", func(c *qualify.Candidate) { c.SupplyMode = "dedicated" }, qualify.ReasonDedicated},
		{"protocol", func(c *qualify.Candidate) { c.Provider = "anthropic" }, qualify.ReasonProtocol},
		{"endpoint", func(c *qualify.Candidate) { c.EndpointIDs = []string{"other"} }, qualify.ReasonEndpoint},
		{"model", func(c *qualify.Candidate) { c.Models = []string{"other"} }, qualify.ReasonModel},
		{"region", func(c *qualify.Candidate) { c.Region = "eu" }, qualify.ReasonRegion},
		{"health", func(c *qualify.Candidate) { c.Health = "unhealthy" }, qualify.ReasonHealth},
		{"capacity", func(c *qualify.Candidate) { c.DeclaredCapacity = 0; c.AdmitsNew = false }, qualify.ReasonCapacity},
		{"price", func(c *qualify.Candidate) { c.PriceValid = false }, qualify.ReasonPrice},
		{"lifecycle", func(c *qualify.Candidate) { c.Lifecycle = "paused" }, qualify.ReasonLifecycle},
		{"self", func(c *qualify.Candidate) { c.SellerOwnerID = "buyer-1" }, qualify.ReasonSelfTrade},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			c := okCand("c1")
			tc.mut(&c)
			d := qualify.Filter(r, []qualify.Candidate{c, okCand("c2")})
			if len(d.QualifiedIDs) != 1 || d.QualifiedIDs[0] != "c2" {
				t.Fatalf("qualified %v", d.QualifiedIDs)
			}
			if len(d.Exclusions) != 1 || d.Exclusions[0].Code != tc.code {
				t.Fatalf("excl %+v", d.Exclusions)
			}
		})
	}
}

func TestSelfTradeControlledSeller(t *testing.T) {
	r := req()
	r.ControlledSellerIDs = []string{"seller-owned"}
	c := okCand("c1")
	c.SellerOwnerID = "seller-owned"
	d := qualify.Filter(r, []qualify.Candidate{c})
	if len(d.QualifiedIDs) != 0 || d.Exclusions[0].Code != qualify.ReasonSelfTrade {
		t.Fatalf("%+v", d)
	}
	if !d.SelfTradeExcluded {
		t.Fatal("flag")
	}
}

func TestReplayStable(t *testing.T) {
	r := req()
	cands := []qualify.Candidate{okCand("b"), okCand("a")}
	a := qualify.Filter(r, cands)
	b := qualify.Filter(r, cands)
	if !bytes.Equal(qualify.ReplayJSON(a), qualify.ReplayJSON(b)) {
		t.Fatal("replay")
	}
	if a.QualifiedIDs[0] != "a" || a.QualifiedIDs[1] != "b" {
		t.Fatalf("sort %v", a.QualifiedIDs)
	}
}

func TestPropertyNoMismatchedProtocol(t *testing.T) {
	rng := rand.New(rand.NewSource(1))
	r := req()
	for i := 0; i < 10000; i++ {
		c := okCand("x")
		if rng.Intn(2) == 0 {
			c.Provider = "vertex"
		}
		d := qualify.Filter(r, []qualify.Candidate{c})
		for _, id := range d.QualifiedIDs {
			if c.ConnectionID == id && c.Provider != "openai" {
				t.Fatal("protocol leak")
			}
		}
	}
}

func TestPreviewRequiresOptIn(t *testing.T) {
	r := req()
	r.Preview = true
	r.PreviewOptIn = false
	d := qualify.Filter(r, []qualify.Candidate{okCand("c1")})
	if len(d.QualifiedIDs) != 0 || d.Exclusions[0].Code != qualify.ReasonCapability {
		t.Fatalf("%+v", d)
	}
	r.PreviewOptIn = true
	d = qualify.Filter(r, []qualify.Candidate{okCand("c1")})
	if len(d.QualifiedIDs) != 1 {
		t.Fatalf("%+v", d)
	}
}
