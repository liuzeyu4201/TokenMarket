package providervalid_test

import (
	"reflect"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestIntersectModels(t *testing.T) {
	up := []string{"a", "b", "c"}
	al := []string{"b", "c", "d"}
	got := providervalid.IntersectModels(up, al)
	want := []string{"b", "c"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v want %v", got, want)
	}
	if len(providervalid.IntersectModels(up, []string{"z"})) != 0 {
		t.Fatal("empty intersect")
	}
}

func TestParseAllowlistCSV(t *testing.T) {
	def := providervalid.ParseAllowlistCSV("")
	if len(def) == 0 {
		t.Fatal("default empty")
	}
	got := providervalid.ParseAllowlistCSV(" m1 , m2 ")
	if !reflect.DeepEqual(got, []string{"m1", "m2"}) {
		t.Fatalf("%v", got)
	}
}
