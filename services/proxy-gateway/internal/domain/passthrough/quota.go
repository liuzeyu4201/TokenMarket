package passthrough

import "context"

// Quota reserves test quota before upstream and aborts if the request never leaves.
type Quota interface {
	Reserve(ctx context.Context, requestID, projectID, keyID string, amount int64) error
	Abort(ctx context.Context, requestID string) error
}

type quotaError string

func (e quotaError) Error() string { return string(e) }

const ErrInsufficientQuota quotaError = CodeInsufficientQuota
