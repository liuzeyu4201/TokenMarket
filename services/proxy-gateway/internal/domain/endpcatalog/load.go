package endpcatalog

import (
	_ "embed"
	"encoding/json"
	"os"
	"strconv"
)

//go:embed catalog.snapshot.json
var snapshotJSON []byte

func Parse(raw []byte) (*Catalog, error) {
	var c Catalog
	if err := json.Unmarshal(raw, &c); err != nil {
		return nil, &LoadError{Code: CodeLoadFailed, Message: "invalid json"}
	}
	if c.Records == nil {
		c.Records = []EndpointRecord{}
	}
	for i := range c.Records {
		if c.Records[i].CapabilityTags == nil {
			c.Records[i].CapabilityTags = []string{}
		}
	}
	return &c, nil
}

func LoadBytes(raw []byte, wantMajor int) (*Catalog, error) {
	c, err := Parse(raw)
	if err != nil {
		return nil, err
	}
	if err := ValidateMajor(c, wantMajor); err != nil {
		return nil, err
	}
	return c, nil
}

func LoadFile(path string, wantMajor int) (*Catalog, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, &LoadError{Code: CodeLoadFailed, Message: "missing catalog file"}
	}
	return LoadBytes(raw, wantMajor)
}

func LoadEmbedded(wantMajor int) (*Catalog, error) {
	return LoadBytes(snapshotJSON, wantMajor)
}

func MustLoadFromEnv() (*Catalog, error) {
	want := CatalogMajor
	if v := os.Getenv("TOKENMARKET_CATALOG_MAJOR"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil {
			return nil, &LoadError{Code: CodeVersionMismatch, Message: "invalid TOKENMARKET_CATALOG_MAJOR"}
		}
		want = n
	}
	if path := os.Getenv("TOKENMARKET_ENDPOINT_CATALOG"); path != "" {
		return LoadFile(path, want)
	}
	return LoadEmbedded(want)
}
