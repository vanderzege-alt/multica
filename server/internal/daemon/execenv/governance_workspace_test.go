package execenv

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPrepareWorkspaceGovernanceCLI(t *testing.T) {
	work := t.TempDir()
	govDir := filepath.Join(work, "multica-org-governance", "scripts")
	if err := os.MkdirAll(govDir, 0o755); err != nil {
		t.Fatal(err)
	}
	wrapper := filepath.Join(govDir, "multica-governed")
	if err := os.WriteFile(wrapper, []byte("#!/usr/bin/env bash\nexit 0\n"), 0o755); err != nil {
		t.Fatal(err)
	}

	cfgDir := filepath.Join(work, ".multica")
	if err := os.MkdirAll(cfgDir, 0o755); err != nil {
		t.Fatal(err)
	}
	cfg := "cli_wrapper: multica-org-governance/scripts/multica-governed\n"
	if err := os.WriteFile(filepath.Join(cfgDir, "governance.yaml"), []byte(cfg), 0o644); err != nil {
		t.Fatal(err)
	}

	binDir, err := PrepareWorkspaceGovernanceCLI(work)
	if err != nil {
		t.Fatalf("PrepareWorkspaceGovernanceCLI: %v", err)
	}
	if binDir != filepath.Join(work, "bin") {
		t.Fatalf("binDir = %q", binDir)
	}
	shim := filepath.Join(binDir, "multica")
	data, err := os.ReadFile(shim)
	if err != nil {
		t.Fatal(err)
	}
	if !contains(string(data), "multica-governed") {
		t.Fatalf("shim content = %q", string(data))
	}
}

func contains(s, sub string) bool {
	return len(sub) == 0 || (len(s) >= len(sub) && stringIndex(s, sub) >= 0)
}

func stringIndex(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}

func TestPrepareWorkspaceGovernanceCLI_NoConfig(t *testing.T) {
	binDir, err := PrepareWorkspaceGovernanceCLI(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if binDir != "" {
		t.Fatalf("expected empty binDir, got %q", binDir)
	}
}
