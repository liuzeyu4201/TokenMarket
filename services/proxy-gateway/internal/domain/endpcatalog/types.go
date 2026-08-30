package endpcatalog

// 目录与准入判定的领域类型。加载后快照只读。

const (
	SchemaVersion = "1.0.0"
	CatalogMajor  = 1
	CatalogMinor  = 0
	FreezeDate    = "2026-08-31"

	CodeNotCataloged      = "ENDPOINT_NOT_CATALOGED"
	CodeControlPlane      = "CONTROL_PLANE_NOT_ALLOWED"
	CodePreview           = "PREVIEW_NOT_ENABLED"
	CodeDedicatedRequired = "DEDICATED_PROJECT_REQUIRED"
	CodeVersionMismatch   = "CATALOG_VERSION_MISMATCH"
	CodeLoadFailed        = "CATALOG_LOAD_FAILED"
)

type Catalog struct {
	SchemaVersion string           `json:"schema_version"`
	CatalogMajor  int              `json:"catalog_major"`
	CatalogMinor  int              `json:"catalog_minor"`
	FreezeDate    string           `json:"freeze_date"`
	Providers     []string         `json:"providers"`
	Records       []EndpointRecord `json:"records"`
}

type EndpointRecord struct {
	ID                    string   `json:"id"`
	Provider              string   `json:"provider"`
	ProtocolVersion       string   `json:"protocol_version"`
	Method                string   `json:"method"`
	PathTemplate          string   `json:"path_template"`
	Stability             string   `json:"stability"`
	CapabilityTags        []string `json:"capability_tags"`
	Stateful              bool     `json:"stateful"`
	Transport             string   `json:"transport"`
	Affinity              string   `json:"affinity"`
	MeteringSource        string   `json:"metering_source"`
	FirstSupportedVersion string   `json:"first_supported_version"`
	TestFixtureVersion    string   `json:"test_fixture_version"`
	OfficialSource        string   `json:"official_source"`
	OwningSF              string   `json:"owning_sf"`
	RequiresProjectOptIn  bool     `json:"requires_project_opt_in"`
}

type AdmitInput struct {
	Provider     string
	Method       string
	Path         string
	ProjectMode  string // shared | dedicated | unknown
	PreviewOptIn bool
}

type Decision struct {
	Allow  bool
	Code   string
	Record *EndpointRecord
}

type LoadError struct {
	Code    string
	Message string
}

func (e *LoadError) Error() string {
	if e == nil {
		return ""
	}
	return e.Code + ": " + e.Message
}
