package endpcatalog_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func sampleRecord() endpcatalog.EndpointRecord {
	return endpcatalog.EndpointRecord{
		ID:                    "openai.post.v1.chat.completions",
		Provider:              "openai",
		ProtocolVersion:       "v1",
		Method:                "POST",
		PathTemplate:          "/v1/chat/completions",
		Stability:             "stable",
		CapabilityTags:        []string{"chat"},
		Transport:             "http",
		Affinity:              "none",
		MeteringSource:        "usage",
		FirstSupportedVersion: "v0.2.0",
		TestFixtureVersion:    "fx-v0.2.0",
		OfficialSource:        "https://developers.openai.com/api/reference/",
		OwningSF:              "SF19",
	}
}

func validCatalog() *endpcatalog.Catalog {
	return &endpcatalog.Catalog{
		SchemaVersion: endpcatalog.SchemaVersion,
		CatalogMajor:  endpcatalog.CatalogMajor,
		CatalogMinor:  0,
		FreezeDate:    endpcatalog.FreezeDate,
		Providers:     []string{"openai", "anthropic", "vertex"},
		Records:       []endpcatalog.EndpointRecord{sampleRecord()},
	}
}

func TestValidateRejectsMissingFields(t *testing.T) {
	fields := []string{"stability", "transport", "metering", "fixture"}
	for _, field := range fields {
		c := validCatalog()
		switch field {
		case "stability":
			c.Records[0].Stability = ""
		case "transport":
			c.Records[0].Transport = ""
		case "metering":
			c.Records[0].MeteringSource = ""
		case "fixture":
			c.Records[0].TestFixtureVersion = ""
		}
		if err := endpcatalog.Validate(c); err == nil {
			t.Fatalf("expected reject for %s", field)
		}
	}
}

func TestValidateRejectsDuplicateKey(t *testing.T) {
	c := validCatalog()
	dup := sampleRecord()
	dup.ID = "other"
	c.Records = append(c.Records, dup)
	if err := endpcatalog.Validate(c); err == nil {
		t.Fatal("expected duplicate reject")
	}
}

func TestValidateRejectsPreviewWithoutOptIn(t *testing.T) {
	c := validCatalog()
	c.Records[0].Stability = "preview"
	c.Records[0].RequiresProjectOptIn = false
	if err := endpcatalog.Validate(c); err == nil {
		t.Fatal("expected opt-in reject")
	}
}

func TestEmbeddedCatalogValidatesAndMatchesMajor(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(endpcatalog.CatalogMajor)
	if err != nil {
		t.Fatal(err)
	}
	if c.FreezeDate != endpcatalog.FreezeDate {
		t.Fatalf("freeze %s", c.FreezeDate)
	}
	err = endpcatalog.ValidateMajor(c, 99)
	if err == nil {
		t.Fatal("expected version mismatch")
	}
	le, ok := err.(*endpcatalog.LoadError)
	if !ok || le.Code != endpcatalog.CodeVersionMismatch {
		t.Fatalf("want CATALOG_VERSION_MISMATCH got %v", err)
	}
}

func TestSnapshotByteIdenticalToSharedContract(t *testing.T) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("caller")
	}
	dir := filepath.Dir(file)
	var root string
	for i := 0; i < 8; i++ {
		if _, err := os.Stat(filepath.Join(dir, "shared", "contracts")); err == nil {
			root = dir
			break
		}
		dir = filepath.Dir(dir)
	}
	if root == "" {
		t.Fatal("repo root")
	}
	shared, err := os.ReadFile(filepath.Join(root, "shared", "contracts", "endpoint-catalog", "v1", "catalog.json"))
	if err != nil {
		t.Fatal(err)
	}
	snap, err := os.ReadFile(filepath.Join(filepath.Dir(file), "catalog.snapshot.json"))
	if err != nil {
		t.Fatal(err)
	}
	if string(shared) != string(snap) {
		t.Fatal("catalog snapshot drifted from shared/contracts")
	}
	var doc map[string]any
	if err := json.Unmarshal(shared, &doc); err != nil {
		t.Fatal(err)
	}
}
