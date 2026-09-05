package capacity

import (
	"testing"
)

func TestDockerRunCmdNeverPulls(t *testing.T) {
	cmd := dockerRunCmd([]string{postgresTestImage})
	args := cmd.Args
	if len(args) < 5 || args[0] != "docker" || args[1] != "run" || args[2] != "-d" {
		t.Fatalf("unexpected docker run prefix: %v", args)
	}
	found := false
	for i := 0; i < len(args)-1; i++ {
		if args[i] == "--pull" && args[i+1] == "never" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("expected --pull never in %v", args)
	}
}

func TestRequireDockerImageSkipsMissingImage(t *testing.T) {
	dockerAvailable(t)
	t.Run("missing-image", func(t *testing.T) {
		requireDockerImage(t, "tokenmarket.invalid/ci-missing:do-not-pull")
		t.Fatal("expected skip when image is absent")
	})
}
