// Package qualify applies hard shared-routing filters before any scoring.
package qualify

import (
	"encoding/json"
	"sort"
	"strings"
)

const FilterVersion = "1.0.0"

const (
	ReasonDedicated  = "DEDICATED"
	ReasonMode       = "MODE"
	ReasonProtocol   = "PROTOCOL"
	ReasonEndpoint   = "ENDPOINT"
	ReasonCapability = "CAPABILITY"
	ReasonModel      = "MODEL"
	ReasonRegion     = "REGION"
	ReasonHealth     = "HEALTH"
	ReasonCapacity   = "CAPACITY"
	ReasonPrice      = "PRICE"
	ReasonLifecycle  = "LIFECYCLE"
	ReasonSelfTrade  = "SELF_TRADE"
)

// Candidate is one Connection snapshot used for a single filter pass.
type Candidate struct {
	ConnectionID     string
	SellerOwnerID    string
	Provider         string
	Protocol         string
	SupplyMode       string
	Lifecycle        string
	Health           string
	Region           string
	Models           []string
	Capabilities     []string
	EndpointIDs      []string
	DeclaredCapacity int
	AdmitsNew        bool
	PriceValid       bool
}

// Request is the buyer-side query against one snapshot.
type Request struct {
	BuyerOwnerID        string
	ControlledSellerIDs []string
	ProjectMode         string
	Provider            string
	Protocol            string
	EndpointID          string
	Model               string
	Region              string
	Preview             bool
	PreviewOptIn        bool
	SnapshotVersion     string
}

// Exclusion records why a candidate missed.
type Exclusion struct {
	ConnectionID string `json:"connection_id"`
	Code         string `json:"code"`
}

// Decision is the replayable qualified set.
type Decision struct {
	FilterVersion     string      `json:"filter_version"`
	SnapshotVersion   string      `json:"snapshot_version"`
	QualifiedIDs      []string    `json:"qualified_connection_ids"`
	Exclusions        []Exclusion `json:"hard_filter_exclusions"`
	SelfTradeExcluded bool        `json:"self_trade_excluded"`
}

func contains(xs []string, want string) bool {
	if want == "" {
		return true
	}
	for _, x := range xs {
		if x == want {
			return true
		}
	}
	return false
}

func selfTrade(req Request, c Candidate) bool {
	if c.SellerOwnerID != "" && c.SellerOwnerID == req.BuyerOwnerID {
		return true
	}
	for _, id := range req.ControlledSellerIDs {
		if id != "" && (id == c.SellerOwnerID || id == c.ConnectionID) {
			return true
		}
	}
	return false
}

func reason(c Candidate, req Request) string {
	if c.SupplyMode == "dedicated" {
		return ReasonDedicated
	}
	if req.ProjectMode != "" && req.ProjectMode != "shared" {
		return ReasonMode
	}
	if c.SupplyMode != "" && c.SupplyMode != "shared" {
		return ReasonMode
	}
	if req.Provider != "" && c.Provider != "" && c.Provider != req.Provider {
		return ReasonProtocol
	}
	if req.Protocol != "" && c.Protocol != "" && c.Protocol != req.Protocol {
		return ReasonProtocol
	}
	if req.EndpointID != "" && len(c.EndpointIDs) > 0 && !contains(c.EndpointIDs, req.EndpointID) {
		return ReasonEndpoint
	}
	if req.EndpointID != "" && len(c.Capabilities) > 0 && !contains(c.Capabilities, req.EndpointID) && len(c.EndpointIDs) == 0 {
		return ReasonCapability
	}
	if req.Preview && !req.PreviewOptIn {
		return ReasonCapability
	}
	if req.Model != "" && len(c.Models) > 0 && !contains(c.Models, req.Model) {
		return ReasonModel
	}
	if req.Region != "" && c.Region != "" && !strings.EqualFold(c.Region, req.Region) && c.Region != "*" {
		return ReasonRegion
	}
	if c.Health != "" && c.Health != "healthy" && c.Health != "degraded" {
		return ReasonHealth
	}
	if !c.AdmitsNew || c.DeclaredCapacity == 0 {
		return ReasonCapacity
	}
	if !c.PriceValid {
		return ReasonPrice
	}
	switch c.Lifecycle {
	case "", "listed", "bound":
	default:
		return ReasonLifecycle
	}
	if selfTrade(req, c) {
		return ReasonSelfTrade
	}
	return ""
}

// Filter applies hard gates in a stable order against one candidate snapshot.
func Filter(req Request, cands []Candidate) Decision {
	d := Decision{
		FilterVersion:     FilterVersion,
		SnapshotVersion:   req.SnapshotVersion,
		SelfTradeExcluded: true,
	}
	for _, c := range cands {
		if code := reason(c, req); code != "" {
			d.Exclusions = append(d.Exclusions, Exclusion{ConnectionID: c.ConnectionID, Code: code})
			continue
		}
		d.QualifiedIDs = append(d.QualifiedIDs, c.ConnectionID)
	}
	sort.Strings(d.QualifiedIDs)
	return d
}

// ReplayJSON canonicalizes a decision for digest comparison.
func ReplayJSON(d Decision) []byte {
	b, _ := json.Marshal(d)
	return b
}
