package endpcatalog_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func TestAdmitStableStatelessAllowed(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider:    "openai",
		Method:      "POST",
		Path:        "/v1/chat/completions",
		ProjectMode: "shared",
	})
	if !d.Allow {
		t.Fatalf("want allow got %s", d.Code)
	}
}

func TestAdmitUncataloged(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider: "openai",
		Method:   "POST",
		Path:     "/v1/does-not-exist",
	})
	if d.Allow || d.Code != endpcatalog.CodeNotCataloged {
		t.Fatalf("got %+v", d)
	}
}

func TestAdmitControlPlane(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider: "openai",
		Method:   "GET",
		Path:     "/v1/organization/users",
	})
	if d.Allow || d.Code != endpcatalog.CodeControlPlane {
		t.Fatalf("got %+v", d)
	}
}

func TestAdmitPreviewDefaultDenied(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider:     "openai",
		Method:       "POST",
		Path:         "/v1/videos",
		ProjectMode:  "dedicated",
		PreviewOptIn: false,
	})
	if d.Allow || d.Code != endpcatalog.CodePreview {
		t.Fatalf("got %+v", d)
	}
	d = endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider:     "openai",
		Method:       "POST",
		Path:         "/v1/videos",
		ProjectMode:  "dedicated",
		PreviewOptIn: true,
	})
	if !d.Allow {
		t.Fatalf("opt-in should allow got %s", d.Code)
	}
}

func TestAdmitStatefulRequiresDedicated(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider:    "openai",
		Method:      "POST",
		Path:        "/v1/files",
		ProjectMode: "shared",
	})
	if d.Allow || d.Code != endpcatalog.CodeDedicatedRequired {
		t.Fatalf("got %+v", d)
	}
	d = endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider:    "openai",
		Method:      "POST",
		Path:        "/v1/files",
		ProjectMode: "dedicated",
	})
	if !d.Allow {
		t.Fatalf("dedicated should allow files got %s", d.Code)
	}
}

func TestAdmitUnknownModeFailClosedForStateful(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider: "openai",
		Method:   "POST",
		Path:     "/v1/files",
	})
	if d.Allow || d.Code != endpcatalog.CodeDedicatedRequired {
		t.Fatalf("got %+v", d)
	}
}

func TestAdmitVertexGenerateContent(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider:    "vertex",
		Method:      "POST",
		Path:        "/v1/projects/p1/locations/us-central1/publishers/google/models/gemini-1.5-pro:generateContent",
		ProjectMode: "shared",
	})
	if !d.Allow {
		t.Fatalf("want allow got %s", d.Code)
	}
}

func TestAdmitAnthropicMessages(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	d := endpcatalog.Admit(c, endpcatalog.AdmitInput{
		Provider:    "anthropic",
		Method:      "POST",
		Path:        "/v1/messages",
		ProjectMode: "shared",
	})
	if !d.Allow {
		t.Fatalf("got %s", d.Code)
	}
}

func TestMatchPrefersLiteralOverPathVar(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	rec := endpcatalog.Match(c, "openai", "POST", "/v1/threads/runs")
	if rec == nil || rec.PathTemplate != "/v1/threads/runs" {
		t.Fatalf("got %+v", rec)
	}
	rec = endpcatalog.Match(c, "openai", "POST", "/v1/threads/thread-1")
	if rec == nil || rec.PathTemplate != "/v1/threads/{thread_id}" {
		t.Fatalf("got %+v", rec)
	}
}
