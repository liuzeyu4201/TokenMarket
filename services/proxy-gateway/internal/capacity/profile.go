// Package capacity is the SF33 mock-upstream load, soak, fault, and backup engine.
package capacity

import "time"

const (
	TenantCount     = 500
	SteadyRPS       = 500
	BurstRPS        = 1000
	StreamConns     = 500
	ControlRPS      = 100
	DatasetSeed     = int64(20260831)
	SuccessFloor    = 0.999
	DisconnectMax   = 0.005
	PlatformP95Max  = 100 * time.Millisecond
	ControlP95Max   = 500 * time.Millisecond
	ControlErrMax   = 0.005
	SteadyDuration  = 30 * time.Minute
	BurstDuration   = 5 * time.Minute
	RecoverDuration = 10 * time.Minute
	StreamDuration  = 2 * time.Hour
	ControlDuration = 30 * time.Minute
	RPOLimit        = 5 * time.Minute
	RTOLimit        = 30 * time.Minute
)

type Profile struct {
	Name     string
	Tenants  int
	RPS      int
	Duration time.Duration
}

func Steady() Profile {
	return Profile{Name: "steady", Tenants: TenantCount, RPS: SteadyRPS, Duration: SteadyDuration}
}

func Burst() Profile {
	return Profile{Name: "burst", Tenants: TenantCount, RPS: BurstRPS, Duration: BurstDuration}
}

func Control() Profile {
	return Profile{Name: "control", Tenants: TenantCount, RPS: ControlRPS, Duration: ControlDuration}
}

func (p Profile) WithDuration(d time.Duration) Profile {
	p.Duration = d
	return p
}
