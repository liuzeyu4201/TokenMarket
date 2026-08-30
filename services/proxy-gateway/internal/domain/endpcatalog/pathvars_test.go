package endpcatalog_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func TestPathVarsFileID(t *testing.T) {
	vars := endpcatalog.PathVars("/v1/files/{file_id}", "/v1/files/file-1")
	if vars["file_id"] != "file-1" {
		t.Fatalf("%v", vars)
	}
	if endpcatalog.ResourceID(vars) != "file-1" {
		t.Fatalf("resource %q", endpcatalog.ResourceID(vars))
	}
}

func TestPathVarsContentSuffix(t *testing.T) {
	vars := endpcatalog.PathVars("/v1/files/{file_id}/content", "/v1/files/file-abc/content")
	if vars["file_id"] != "file-abc" {
		t.Fatalf("%v", vars)
	}
}

func TestPathVarsNoMatch(t *testing.T) {
	if vars := endpcatalog.PathVars("/v1/files/{file_id}", "/v1/files"); vars != nil {
		t.Fatalf("got %v", vars)
	}
}

func TestPathVarsStatic(t *testing.T) {
	vars := endpcatalog.PathVars("/v1/files", "/v1/files")
	if vars == nil || len(vars) != 0 {
		t.Fatalf("%v", vars)
	}
	if endpcatalog.ResourceID(vars) != "" {
		t.Fatal("list path must not yield resource id")
	}
}

func TestResourceIDPrefersID(t *testing.T) {
	got := endpcatalog.ResourceID(map[string]string{"id": "resp-1", "file_id": "file-9"})
	if got != "resp-1" {
		t.Fatalf("%q", got)
	}
}

func TestResourceIDFallbackPlain(t *testing.T) {
	got := endpcatalog.ResourceID(map[string]string{"name": "ops-1"})
	if got != "ops-1" {
		t.Fatalf("%q", got)
	}
	if endpcatalog.ResourceID(nil) != "" {
		t.Fatal("nil vars")
	}
}
