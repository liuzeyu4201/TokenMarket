// Package application 编排凭证验证用例。
package application

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/concurrency"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

// ModelsLister 上游模型列表端口。
type ModelsLister interface {
	ListModels(ctx context.Context, apiKey string) volcano.ModelsResult
}

// Validator 凭证验证器。
type Validator struct {
	Cfg     providervalid.Config
	Models  ModelsLister
	Quota   volcano.QuotaReader
	Gate    *concurrency.ValidateGate
	Now     func() time.Time
	Metrics *observability.ValidateMetrics
	Logger  *slog.Logger
}

// NewValidator 构造默认依赖。
func NewValidator(cfg providervalid.Config) *Validator {
	client := volcano.NewModelsClient(cfg.BaseURL, cfg.DefaultRetryAfter, cfg.MaxRetryAfter)
	return &Validator{
		Cfg:     cfg,
		Models:  client,
		Quota:   volcano.NoopQuotaReader{},
		Gate:    concurrency.NewValidateGate(cfg.GlobalConcurrency, cfg.PerCredConcurrency, cfg.GateHMACSecret),
		Now:     func() time.Time { return time.Now().UTC() },
		Metrics: observability.DefaultValidateMetrics(),
		Logger:  slog.Default(),
	}
}

// ValidateCredential 执行无状态单次验证（3s 硬截止取更严 context）。
func (v *Validator) ValidateCredential(ctx context.Context, req providervalid.CredentialValidationRequest) providervalid.CredentialValidationResult {
	start := time.Now()
	platform := strings.TrimSpace(req.Platform)
	apiKey := strings.TrimSpace(req.APIKey)
	credRef := providervalid.CredentialRef(apiKey, v.Cfg.GateHMACSecret)
	requestID := strings.TrimSpace(req.RequestID)

	deadline := 3 * time.Second
	var cancel context.CancelFunc
	if dl, ok := ctx.Deadline(); ok {
		if rem := time.Until(dl); rem < deadline {
			deadline = rem
		}
	}
	ctx, cancel = context.WithTimeout(ctx, deadline)
	defer cancel()

	finish := func(r providervalid.CredentialValidationResult) providervalid.CredentialValidationResult {
		dur := time.Since(start)
		plat := r.Platform
		if plat == "" {
			plat = platform
		}
		if v.Metrics != nil {
			v.Metrics.Observe(plat, string(r.ErrorCategory), dur)
		}
		if v.Logger != nil {
			// 禁止记录 api_key / Authorization
			v.Logger.Info("provider_validate_complete",
				"request_id", requestID,
				"platform", plat,
				"error_category", string(r.ErrorCategory),
				"duration_ms", dur.Milliseconds(),
				"credential_ref", r.CredentialRef,
			)
		}
		return r
	}

	if platform == "" || apiKey == "" {
		return finish(providervalid.NewResult(
			platform, providervalid.CategoryInvalidResponse,
			providervalid.ValidityUnknown, providervalid.AvailabilityUnavailable,
			nil, nil, nil, nil, credRef, v.Now(),
		))
	}

	if platform != "volcano" {
		return finish(providervalid.NewResult(
			platform, providervalid.CategoryUnsupportedPlatform,
			providervalid.ValidityInvalid, providervalid.AvailabilityUnavailable,
			nil, nil, nil, nil, credRef, v.Now(),
		))
	}

	release, ok := v.Gate.Acquire(apiKey)
	if !ok {
		ra := 1
		r := providervalid.NewResult(
			platform, providervalid.CategoryTemporaryUnavailable,
			providervalid.ValidityUnknown, providervalid.AvailabilityUnavailable,
			nil, nil, nil, &ra, credRef, v.Now(),
		)
		if v.Metrics != nil {
			v.Metrics.GateRejected()
		}
		return finish(r)
	}
	defer release()

	if err := ctx.Err(); err != nil {
		return finish(providervalid.NewResult(
			platform, providervalid.ClassifyTransportError(err),
			providervalid.ValidityUnknown, providervalid.AvailabilityUnavailable,
			nil, nil, nil, nil, credRef, v.Now(),
		))
	}

	mr := v.Models.ListModels(ctx, apiKey)
	if !mr.AuthOK {
		var retry *int
		if mr.Category == providervalid.CategoryRateLimited {
			ra := mr.RetryAfterSec
			if ra < 1 {
				ra = providervalid.ParseRetryAfter("", v.Cfg.DefaultRetryAfter, v.Cfg.MaxRetryAfter)
			}
			retry = &ra
		}
		validity := providervalid.ValidityUnknown
		switch mr.Category {
		case providervalid.CategoryInvalid, providervalid.CategoryForbidden:
			validity = providervalid.ValidityInvalid
		}
		return finish(providervalid.NewResult(
			platform, mr.Category, validity, providervalid.AvailabilityUnavailable,
			nil, nil, nil, retry, credRef, v.Now(),
		))
	}

	qi, qerr := v.Quota.ReadQuota(ctx, apiKey)
	if qerr != nil || !qi.Available {
		return finish(providervalid.NewResult(
			platform, providervalid.CategoryQuotaUnavailable,
			providervalid.ValidityValid, providervalid.AvailabilityUnavailable,
			providervalid.IntersectModels(mr.ModelIDs, v.Cfg.Allowlist),
			nil, nil, nil, credRef, v.Now(),
		))
	}

	models := providervalid.IntersectModels(mr.ModelIDs, v.Cfg.Allowlist)
	amount := qi.Amount
	unit := qi.Unit

	if amount == "0" {
		return finish(providervalid.NewResult(
			platform, providervalid.CategoryZeroQuota,
			providervalid.ValidityValid, providervalid.AvailabilityUnavailable,
			models, &amount, &unit, nil, credRef, v.Now(),
		))
	}

	if len(models) == 0 {
		return finish(providervalid.NewResult(
			platform, providervalid.CategoryNoSupportedModels,
			providervalid.ValidityValid, providervalid.AvailabilityUnavailable,
			models, &amount, &unit, nil, credRef, v.Now(),
		))
	}

	return finish(providervalid.NewResult(
		platform, providervalid.CategorySuccess,
		providervalid.ValidityValid, providervalid.AvailabilityAvailable,
		models, &amount, &unit, nil, credRef, v.Now(),
	))
}
