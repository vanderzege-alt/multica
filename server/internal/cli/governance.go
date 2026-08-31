package cli

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

const governanceConfigRel = ".multica/governance.yaml"

type governanceConfig struct {
	GovernanceRoot string `yaml:"governance_root"`
	Hooks          struct {
		PreComment      string `yaml:"pre_comment"`
		PreIssueCreate  string `yaml:"pre_issue_create"`
		PreStatus       string `yaml:"pre_status"`
		PreRepoCheckout string `yaml:"pre_repo_checkout"`
	} `yaml:"hooks"`
}

// FindGovernanceConfig walks up from startDir looking for .multica/governance.yaml.
func FindGovernanceConfig(startDir string) (configPath string, cfg governanceConfig, ok bool, err error) {
	dir := startDir
	for {
		candidate := filepath.Join(dir, governanceConfigRel)
		data, readErr := os.ReadFile(candidate)
		if readErr == nil {
			var parsed governanceConfig
			if unmarshalErr := yaml.Unmarshal(data, &parsed); unmarshalErr != nil {
				return candidate, governanceConfig{}, false, fmt.Errorf("parse %s: %w", candidate, unmarshalErr)
			}
			return candidate, parsed, true, nil
		}
		if !os.IsNotExist(readErr) {
			return "", governanceConfig{}, false, readErr
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", governanceConfig{}, false, nil
		}
		dir = parent
	}
}

func (c governanceConfig) resolveHook(workdir, rel string) string {
	rel = strings.TrimSpace(rel)
	if rel == "" {
		return ""
	}
	if filepath.IsAbs(rel) {
		return rel
	}
	return filepath.Clean(filepath.Join(workdir, rel))
}

func hookPathFromConfig(configPath string, cfg governanceConfig, hookRel string) (string, error) {
	workdir := filepath.Dir(filepath.Dir(configPath))
	hook := cfg.resolveHook(workdir, hookRel)
	if hook == "" {
		return "", fmt.Errorf("governance hook path is empty in %s", configPath)
	}
	if _, err := os.Stat(hook); err != nil {
		return "", fmt.Errorf("governance hook not found: %s (%w)", hook, err)
	}
	return hook, nil
}

// RunGovernanceHook executes a workspace governance hook script.
func RunGovernanceHook(hookPath string, extraEnv map[string]string, args ...string) error {
	cmd := exec.Command("bash", append([]string{hookPath}, args...)...)
	cmd.Env = append(os.Environ(), governanceBaseEnv()...)
	for k, v := range extraEnv {
		cmd.Env = append(cmd.Env, k+"="+v)
	}
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = err.Error()
		}
		return fmt.Errorf("comment rejected by governance gate:\n%s", msg)
	}
	return nil
}

func governanceBaseEnv() []string {
	pairs := []string{}
	for _, key := range []string{
		"MULTICA_AGENT_ID",
		"MULTICA_TASK_ID",
		"MULTICA_WORKSPACE_ID",
		"MULTICA_AUTHOR_ID",
	} {
		if v := strings.TrimSpace(os.Getenv(key)); v != "" {
			pairs = append(pairs, key+"="+v)
		}
	}
	if id := strings.TrimSpace(os.Getenv("MULTICA_AGENT_ID")); id != "" && strings.TrimSpace(os.Getenv("MULTICA_AUTHOR_ID")) == "" {
		pairs = append(pairs, "MULTICA_AUTHOR_ID="+id)
	}
	return pairs
}

// RunPreCommentHook runs the configured pre-comment governance gate.
func RunPreCommentHook(comment string) error {
	cwd, err := os.Getwd()
	if err != nil {
		return err
	}
	configPath, cfg, ok, err := FindGovernanceConfig(cwd)
	if err != nil {
		return err
	}
	if !ok {
		return nil
	}
	hook, err := hookPathFromConfig(configPath, cfg, cfg.Hooks.PreComment)
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp("", "multica-governance-comment-*.md")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath)
	if _, err := tmp.WriteString(comment); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return RunGovernanceHook(hook, map[string]string{
		"MULTICA_COMMENT_FILE": tmpPath,
	}, "--file", tmpPath)
}

// RunPreRepoCheckoutHook runs upstream + governance gates before repo checkout.
func RunPreRepoCheckoutHook(repoURL string) error {
	cwd, err := os.Getwd()
	if err != nil {
		return err
	}
	configPath, cfg, ok, err := FindGovernanceConfig(cwd)
	if err != nil {
		return err
	}
	if !ok {
		return nil
	}
	hookRel := cfg.Hooks.PreRepoCheckout
	if hookRel == "" {
		hookRel = filepath.Join(strings.TrimSpace(cfg.GovernanceRoot), "scripts", "guard-upstream-repo.sh")
	}
	hook, err := hookPathFromConfig(configPath, cfg, hookRel)
	if err != nil {
		// Fallback: direct guard-upstream-repo.sh check-url
		guard := cfg.resolveHook(filepath.Dir(filepath.Dir(configPath)), filepath.Join(strings.TrimSpace(cfg.GovernanceRoot), "scripts/guard-upstream-repo.sh"))
		if _, statErr := os.Stat(guard); statErr == nil {
			return RunGovernanceHook(guard, nil, "check-url", repoURL)
		}
		return err
	}
	// pre-repo-checkout expects URL as first arg; it calls guard then multica.
	if strings.HasSuffix(hook, "pre-repo-checkout") {
		return RunGovernanceHook(hook, nil, repoURL)
	}
	return RunGovernanceHook(hook, nil, "check-url", repoURL)
}

// RunPreStatusHook runs the configured pre-status governance gate before a
// status transition reaches the API.
func RunPreStatusHook(issueID, newStatus, prevStatus, issueTitle, parentIssueID string) error {
	cwd, err := os.Getwd()
	if err != nil {
		return err
	}
	configPath, cfg, ok, err := FindGovernanceConfig(cwd)
	if err != nil {
		return err
	}
	if !ok {
		return nil
	}
	hookRel := cfg.Hooks.PreStatus
	if hookRel == "" {
		hookRel = filepath.Join(strings.TrimSpace(cfg.GovernanceRoot), "scripts", "pre-status")
	}
	hook, err := hookPathFromConfig(configPath, cfg, hookRel)
	if err != nil {
		return err
	}

	authorID := strings.TrimSpace(os.Getenv("MULTICA_AUTHOR_ID"))
	if authorID == "" {
		authorID = strings.TrimSpace(os.Getenv("MULTICA_AGENT_ID"))
	}
	if authorID == "" {
		return fmt.Errorf("pre-status hook requires MULTICA_AUTHOR_ID or MULTICA_AGENT_ID")
	}

	args := []string{
		"--issue-id", issueID,
		"--status", newStatus,
		"--prev-status", prevStatus,
		"--author-id", authorID,
	}
	if issueTitle != "" {
		args = append(args, "--issue-title", issueTitle)
	}
	if parentIssueID != "" {
		args = append(args, "--parent-id", parentIssueID)
	}
	env := map[string]string{
		"ISSUE_ID":          issueID,
		"STATUS":            newStatus,
		"PREV_STATUS":       prevStatus,
		"MULTICA_AUTHOR_ID": authorID,
	}
	if issueTitle != "" {
		env["ISSUE_TITLE"] = issueTitle
	}
	if parentIssueID != "" {
		env["PARENT_ISSUE_ID"] = parentIssueID
	}
	return RunGovernanceHook(hook, env, args...)
}
