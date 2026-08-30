package endpcatalog

import (
	"fmt"
	"strings"
)

var (
	requiredProviders = []string{"openai", "anthropic", "vertex"}
	stabilities       = map[string]struct{}{"stable": {}, "preview": {}, "beta": {}, "control_plane": {}}
	methods           = map[string]struct{}{"GET": {}, "POST": {}, "PUT": {}, "PATCH": {}, "DELETE": {}, "WEBSOCKET": {}}
	transports        = map[string]struct{}{"http": {}, "sse": {}, "websocket": {}, "multipart": {}, "binary": {}}
	affinities        = map[string]struct{}{"none": {}, "connection": {}, "resource_id": {}}
	metering          = map[string]struct{}{"usage": {}, "reported_cost": {}, "mixed": {}, "unresolved": {}, "none": {}}
)

func Validate(c *Catalog) error {
	if c == nil {
		return &LoadError{Code: CodeLoadFailed, Message: "nil catalog"}
	}
	if c.SchemaVersion != SchemaVersion {
		return &LoadError{Code: CodeLoadFailed, Message: "schema_version"}
	}
	if c.FreezeDate != FreezeDate {
		return &LoadError{Code: CodeLoadFailed, Message: "freeze_date"}
	}
	if len(c.Providers) != 3 {
		return &LoadError{Code: CodeLoadFailed, Message: "providers"}
	}
	for i, p := range requiredProviders {
		if c.Providers[i] != p {
			return &LoadError{Code: CodeLoadFailed, Message: "providers order"}
		}
	}
	if len(c.Records) == 0 {
		return &LoadError{Code: CodeLoadFailed, Message: "empty records"}
	}
	seenKey := map[string]struct{}{}
	seenID := map[string]struct{}{}
	for i, rec := range c.Records {
		if err := validateRecord(rec); err != nil {
			return fmt.Errorf("record %d: %w", i, err)
		}
		key := rec.Provider + "\x00" + rec.ProtocolVersion + "\x00" + rec.Method + "\x00" + rec.PathTemplate
		if _, ok := seenKey[key]; ok {
			return &LoadError{Code: CodeLoadFailed, Message: "duplicate key " + rec.ID}
		}
		seenKey[key] = struct{}{}
		if _, ok := seenID[rec.ID]; ok {
			return &LoadError{Code: CodeLoadFailed, Message: "duplicate id " + rec.ID}
		}
		seenID[rec.ID] = struct{}{}
	}
	return nil
}

func validateRecord(rec EndpointRecord) error {
	if rec.ID == "" || rec.Provider == "" || rec.ProtocolVersion == "" || rec.Method == "" || rec.PathTemplate == "" {
		return &LoadError{Code: CodeLoadFailed, Message: "missing identity field"}
	}
	if !strings.HasPrefix(rec.PathTemplate, "/") {
		return &LoadError{Code: CodeLoadFailed, Message: "path_template"}
	}
	if _, ok := stabilities[rec.Stability]; !ok {
		return &LoadError{Code: CodeLoadFailed, Message: "stability"}
	}
	if _, ok := methods[rec.Method]; !ok {
		return &LoadError{Code: CodeLoadFailed, Message: "method"}
	}
	if _, ok := transports[rec.Transport]; !ok {
		return &LoadError{Code: CodeLoadFailed, Message: "transport"}
	}
	if _, ok := affinities[rec.Affinity]; !ok {
		return &LoadError{Code: CodeLoadFailed, Message: "affinity"}
	}
	if _, ok := metering[rec.MeteringSource]; !ok {
		return &LoadError{Code: CodeLoadFailed, Message: "metering_source"}
	}
	if rec.FirstSupportedVersion == "" || rec.TestFixtureVersion == "" || rec.OfficialSource == "" || rec.OwningSF == "" {
		return &LoadError{Code: CodeLoadFailed, Message: "missing trace field"}
	}
	if rec.CapabilityTags == nil {
		return &LoadError{Code: CodeLoadFailed, Message: "capability_tags"}
	}
	if (rec.Stability == "preview" || rec.Stability == "beta") && !rec.RequiresProjectOptIn {
		return &LoadError{Code: CodeLoadFailed, Message: "preview opt-in"}
	}
	return nil
}

func ValidateMajor(c *Catalog, wantMajor int) error {
	if err := Validate(c); err != nil {
		return err
	}
	if c.CatalogMajor != wantMajor {
		return &LoadError{Code: CodeVersionMismatch, Message: fmt.Sprintf("catalog_major %d != %d", c.CatalogMajor, wantMajor)}
	}
	return nil
}
