package execenv

import (
	"os"
	"path/filepath"
	"testing"
)

func TestInstallGovernanceCLIShim(t *testing.T) {
	workDir := t.TempDir()
	real := filepath.Join(workDir, "multica-real")
	if err := os.WriteFile(real, []byte("#!/bin/sh\nexit 0\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := InstallGovernanceCLIShim(workDir, real, nil); err != nil {
		t.Fatal(err)
	}
	shim := filepath.Join(workDir, ".multica", "bin", "multica")
	info, err := os.Stat(shim)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode()&0o111 == 0 {
		t.Fatal("shim should be executable")
	}
	if got := GovernanceShimBinDir(workDir); got != filepath.Join(workDir, ".multica", "bin") {
		t.Fatalf("bin dir = %q", got)
	}
}
