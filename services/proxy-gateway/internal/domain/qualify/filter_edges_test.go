package qualify_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
)

func TestFilterDedicatedModeProtocolAndLifecycle(t *testing.T) {
	req := qualify.Request{
		BuyerOwnerID: "buyer-1",
		ProjectMode:  "shared",
		Provider:     "openai",
		Protocol:     "openai",
		EndpointID:   "chat.completions",
		Model:        "gpt-4o",
		Region:       "us",
		Preview:      true,
		PreviewOptIn: false,
	}
	cands := []qualify.Candidate{
		{ConnectionID: "ded", SupplyMode: "dedicated", SellerOwnerID: "s1"},
		{ConnectionID: "mode", SupplyMode: "other", SellerOwnerID: "s2"},
		{ConnectionID: "prov", SupplyMode: "shared", Provider: "anthropic", SellerOwnerID: "s3"},
		{ConnectionID: "proto", SupplyMode: "shared", Provider: "openai", Protocol: "anthropic", SellerOwnerID: "s4"},
		{
			ConnectionID:  "ep",
			SupplyMode:    "shared",
			Provider:      "openai",
			Protocol:      "openai",
			EndpointIDs:   []string{"other"},
			SellerOwnerID: "s5",
		},
		{
			ConnectionID:  "cap",
			SupplyMode:    "shared",
			Provider:      "openai",
			Protocol:      "openai",
			Capabilities:  []string{"other"},
			SellerOwnerID: "s6",
		},
		{
			ConnectionID:     "prev",
			SupplyMode:       "shared",
			Provider:         "openai",
			Protocol:         "openai",
			SellerOwnerID:    "s7",
			AdmitsNew:        true,
			DeclaredCapacity: 1,
			PriceValid:       true,
			Health:           "healthy",
		},
	}
	dec := qualify.Filter(req, cands)
	if len(dec.QualifiedIDs) != 0 {
		t.Fatalf("expected exclusions, got %v", dec.QualifiedIDs)
	}
	if len(dec.Exclusions) != len(cands) {
		t.Fatalf("exclusions %d", len(dec.Exclusions))
	}
	req.PreviewOptIn = true
	req.EndpointID = ""
	req.Model = "missing"
	modelCand := qualify.Candidate{
		ConnectionID:     "model",
		SupplyMode:       "shared",
		Provider:         "openai",
		Protocol:         "openai",
		Models:           []string{"gpt-4o"},
		Region:           "eu",
		Health:           "down",
		AdmitsNew:        false,
		DeclaredCapacity: 0,
		PriceValid:       false,
		Lifecycle:        "retired",
		SellerOwnerID:    "buyer-1",
	}
	dec = qualify.Filter(req, []qualify.Candidate{modelCand})
	if len(dec.Exclusions) != 1 {
		t.Fatalf("model/region/health %v", dec.Exclusions)
	}
}
