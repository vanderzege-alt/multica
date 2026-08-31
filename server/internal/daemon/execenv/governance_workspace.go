package execenv

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const governanceConfigRel = ".multica/governance.yaml"

// PrepareWorkspaceGovernanceCLI installs a workdir/bin/multica shim that delegates
// to the workspace cli_wrapper from .multica/governance.yaml. Returns the bin
// directory to prepend to PATH (empty when no wrapper configured).
func PrepareWorkspaceGovernanceCLI(workDir string) (string, error) {
	configPath := filepath.Join(workDir, governanceConfigRel)
	data, err := os.ReadFile(configPath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", fmt.Errorf("read governance config: %w", err)
	}

	wrapperRel := parseCLIWrapper(string(data))
	if wrapperRel == "" {
		return "", nil
	}

	wrapperPath := wrapperRel
	if !filepath.IsAbs(wrapperPath) {
		wrapperPath = filepath.Join(workDir, wrapperRel)
	}
	wrapperPath = filepath.Clean(wrapperPath)
	if _, err := os.Stat(wrapperPath); err != nil {
		return "", fmt.Errorf("cli_wrapper not found at %s: %w", wrapperPath, err)
	}

	binDir := filepath.Join(workDir, "bin")
	if err := os.MkdirAll(binDir, 0o755); err != nil {
		return "", fmt.Errorf("create governance bin dir: %w", err)
	}

	shimPath := filepath.Join(binDir, "multica")
	script := fmt.Sprintf("#!/usr/bin/env bash\nset -euo pipefail\nexec %q \"$@\"\n", wrapperPath)
	if err := os.WriteFile(shimPath, []byte(script), 0o755); err != nil {
		return "", fmt.Errorf("write multica shim: %w", err)
	}
	return binDir, nil
}

func parseCLIWrapper(yaml string) string {
	for _, line := range strings.Split(yaml, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "#") || line == "" {
			continue
		}
		const key = "cli_wrapper:"
		if strings.HasPrefix(line, key) {
			return strings.TrimSpace(strings.TrimPrefix(line, key))
		}
	}
	return ""
}
