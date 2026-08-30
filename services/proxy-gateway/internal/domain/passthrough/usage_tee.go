package passthrough

import (
	"bytes"
	"io"
	"strings"
	"sync"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageparse"
)

const usageTeeLimit = 256 << 10

type usageTee struct {
	src        io.ReadCloser
	buf        bytes.Buffer
	max        int
	once       sync.Once
	sse        bool
	provider   string
	metering   string
	requestID  string
	projectID  string
	endpointID string
	rec        usageparse.Recorder
}

func newUsageTee(src io.ReadCloser, contentType, provider, metering, requestID, projectID, endpointID string, rec usageparse.Recorder) *usageTee {
	ct := strings.ToLower(contentType)
	return &usageTee{
		src:        src,
		max:        usageTeeLimit,
		sse:        strings.Contains(ct, "text/event-stream"),
		provider:   provider,
		metering:   metering,
		requestID:  requestID,
		projectID:  projectID,
		endpointID: endpointID,
		rec:        rec,
	}
}

func (t *usageTee) Read(p []byte) (int, error) {
	n, err := t.src.Read(p)
	if n > 0 && t.buf.Len() < t.max {
		take := n
		if t.buf.Len()+take > t.max {
			take = t.max - t.buf.Len()
		}
		_, _ = t.buf.Write(p[:take])
	}
	if err == io.EOF {
		t.finish()
	}
	return n, err
}

func (t *usageTee) Close() error {
	t.finish()
	if t.src == nil {
		return nil
	}
	return t.src.Close()
}

func (t *usageTee) finish() {
	t.once.Do(func() {
		if t.rec == nil {
			return
		}
		c := usageparse.ParseBody(t.provider, t.metering, t.buf.String(), t.sse)
		c.RequestID = t.requestID
		c.ProjectID = t.projectID
		c.EndpointID = t.endpointID
		t.rec.Record(c)
	})
}
