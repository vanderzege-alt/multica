package execenv

import (
	"fmt"
	"os"
	"path/filepath"
)

const governanceShimName = "multica"

// InstallGovernanceCLIShim writes workDir/.multica/bin/multica that delegates to
// the real multica binary. When multica-org-governance is checked out beside the
// shim, multica-governed runs mechanical gates; otherwise the shim forwards directly.
func InstallGovernanceCLIShim(workDir, realMulticaPath string) error {
	if workDir == "" || realMulticaPath == "" {
		return nil
	}
	binDir := filepath.Join(workDir, ".multica", "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		return fmt.Errorf("execenv: create governance bin dir: %w", err)
	}
	shimPath := filepath.Join(binDir, governanceShimName)
	script := fmt.Sprintf(`#!/usr/bin/env bash
set -euo pipefail
REAL_MULTICA=%q
WORKDIR=%q
GOV_WRAPPER="$WORKDIR/multica-org-governance/scripts/multica-governed"
if [[ -x "$GOV_WRAPPER" ]]; then
  export MULTICA_BIN="$REAL_MULTICA"
  exec "$GOV_WRAPPER" "$@"
fi
exec "$REAL_MULTICA" "$@"
`, realMulticaPath, workDir)
	if err := os.WriteFile(shimPath, []byte(script), 0o755); err != nil {
		return fmt.Errorf("execenv: write governance shim: %w", err)
	}
	return nil
}

// GovernanceShimBinDir returns workDir/.multica/bin when the shim exists.
func GovernanceShimBinDir(workDir string) string {
	if workDir == "" {
		return ""
	}
	binDir := filepath.Join(workDir, ".multica", "bin")
	if info, err := os.Stat(filepath.Join(binDir, governanceShimName)); err != nil || info.IsDir() {
		return ""
	}
	return binDir
}
