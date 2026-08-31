package capacity

import "time"

type Report struct {
	Profile          string  `json:"profile"`
	Tenants          int     `json:"tenants"`
	TargetRPS        float64 `json:"target_rps"`
	AchievedRPS      float64 `json:"achieved_rps"`
	Duration         time.Duration
	DurationMS       int64   `json:"duration_ms"`
	Total            int     `json:"total"`
	Success          int     `json:"success"`
	SuccessRate      float64 `json:"success_rate"`
	PlatformP95      time.Duration
	PlatformP95MS    float64 `json:"platform_p95_ms"`
	DisconnectRate   float64 `json:"disconnect_rate"`
	HeapDeltaBytes   int64   `json:"heap_delta_bytes"`
	OpenReservations int     `json:"open_reservations"`
	DoubleCharge     int     `json:"double_charge"`
	CrossTenantLeaks int     `json:"cross_tenant_leaks"`
	Pass             bool    `json:"pass"`
}

func (r Report) PassSteady() bool {
	ok := r.SuccessRate >= SuccessFloor &&
		r.PlatformP95 <= PlatformP95Max &&
		r.OpenReservations == 0 &&
		r.DoubleCharge == 0 &&
		r.CrossTenantLeaks == 0
	if r.Duration >= time.Second && r.TargetRPS > 0 {
		ok = ok && r.AchievedRPS >= r.TargetRPS*0.9
	}
	return ok
}

func (r Report) PassStream() bool {
	return r.DisconnectRate <= DisconnectMax &&
		r.HeapDeltaBytes < 64*1024*1024 &&
		r.DoubleCharge == 0
}
