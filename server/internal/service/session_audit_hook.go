package service

import (
	"context"
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"strings"
	"time"

	obsmetrics "github.com/multica-ai/multica/server/internal/metrics"
	"github.com/multica-ai/multica/server/internal/util"
	db "github.com/multica-ai/multica/server/pkg/db/generated"
)

//go:embed session_audit_hook.py session_audit_matrix.json
var sessionAuditFiles embed.FS

func localSessionAuditEnabled() bool {
	return strings.EqualFold(strings.TrimSpace(os.Getenv("MULTICA_SESSION_AUDIT_ENABLED")), "true")
}

type sessionAuditField struct {
	Value      any            `json:"value"`
	Complete   *bool          `json:"complete,omitempty"`
	TraceRef   string         `json:"trace_ref,omitempty"`
	Provenance map[string]any `json:"provenance"`
}

type localSessionAuditInput struct {
	WorkspaceID     string            `json:"workspace_id"`
	IssueID         string            `json:"issue_id,omitempty"`
	RuntimeProvider string            `json:"runtime_provider,omitempty"`
	Task            map[string]string `json:"task"`
	Manifest        map[string]any    `json:"manifest"`
	Snapshot        map[string]any    `json:"snapshot"`
	Matrix          json.RawMessage   `json:"matrix"`
}

func runLocalSessionAudit(ctx context.Context, queries *db.Queries, metrics *obsmetrics.BusinessMetrics, task db.AgentTaskQueue) error {
	if !localSessionAuditEnabled() || task.Status != "completed" {
		return nil
	}
	agent, err := queries.GetAgent(ctx, task.AgentID)
	if err != nil {
		return fmt.Errorf("load audit agent: %w", err)
	}
	if agent.Kind != "user" {
		return nil // ephemeral system execution carriers are not persistent workers
	}
	runtime, err := (RuntimeLookup{
		Queries: queries,
		Metrics: metrics,
		Source:  obsmetrics.RuntimeLookupSourceTask,
	}).Get(ctx, task.RuntimeID)
	if err != nil {
		return fmt.Errorf("load audit runtime: %w", err)
	}
	skills, err := queries.ListAgentSkillSummaries(ctx, task.AgentID)
	if err != nil {
		return fmt.Errorf("load audit skill inventory: %w", err)
	}
	mcpServers, err := queries.ListAgentMcpServers(ctx, task.AgentID)
	if err != nil {
		return fmt.Errorf("load audit MCP inventory: %w", err)
	}
	targets, err := queries.ListAgentInvocationTargets(ctx, task.AgentID)
	if err != nil {
		return fmt.Errorf("load audit permission inventory: %w", err)
	}
	fields := map[string]any{}
	field := func(value any, suffix string, complete *bool) sessionAuditField {
		return sessionAuditField{Value: value, Complete: complete, Provenance: map[string]any{
			"source": "Multica server configuration", "reference": "multica-task://" + util.UUIDToString(task.ID) + "/" + suffix,
		}}
	}
	fields["agent.display_name"] = field(agent.Name, "agent/name", nil)
	fields["agent.id"] = field(util.UUIDToString(agent.ID), "agent/id", nil)
	fields["runtime.provider"] = field(runtime.Provider, "runtime/provider", nil)
	fields["runtime.runtime"] = field(runtime.RuntimeMode, "runtime/mode", nil)
	if agent.Model.Valid {
		fields["runtime.model"] = field(agent.Model.String, "runtime/model", nil)
	}
	if agent.ThinkingLevel.Valid {
		fields["runtime.thinking"] = field(agent.ThinkingLevel.String, "runtime/thinking", nil)
	}
	skillNames, skillEnabled := make([]string, 0, len(skills)), make([]bool, 0, len(skills))
	for _, skill := range skills {
		skillNames = append(skillNames, skill.Name)
		skillEnabled = append(skillEnabled, skill.Enabled)
	}
	fields["skills.assignments"] = field(skillNames, "skills/assignments", nil)
	fields["skills.enabled"] = field(skillEnabled, "skills/enabled", nil)
	mcpNames := make([]string, 0, len(mcpServers))
	for _, server := range mcpServers {
		if server.Enabled {
			mcpNames = append(mcpNames, server.Name)
		}
	}
	fields["mcp.assignments"] = field(mcpNames, "mcp/assignments", nil)
	fields["permissions.mode"] = sessionAuditField{Value: agent.PermissionMode, Provenance: map[string]any{
		"source": "Multica server authorization configuration", "reference": "multica-task://" + util.UUIDToString(task.ID) + "/permissions/mode", "enforcement": "technical",
	}}
	allowlist := make([]string, 0, len(targets))
	for _, target := range targets {
		allowlist = append(allowlist, target.TargetType+":"+util.UUIDToString(target.TargetID))
	}
	fields["permissions.allowlist"] = sessionAuditField{Value: allowlist, Provenance: map[string]any{
		"source": "Multica server authorization configuration", "reference": "multica-task://" + util.UUIDToString(task.ID) + "/permissions/allowlist", "enforcement": "technical",
	}}
	fields["concurrency"] = field(agent.MaxConcurrentTasks, "agent/concurrency", nil)
	if len(agent.Instructions) > 0 {
		hash := sha256.Sum256([]byte(agent.Instructions))
		fields["prompt.hash"] = field("sha256:"+hex.EncodeToString(hash[:]), "agent/instructions-hash", nil)
	}
	// Runtime tool inventory and execution isolation are not exposed by the
	// server config. Omitting them makes the generator's critical preflight UNKNOWN.
	manifestAgent := map[string]any{"display_name": agent.Name, "id": util.UUIDToString(agent.ID)}
	expected := map[string]any{
		"runtime.provider": runtime.Provider, "runtime.runtime": runtime.RuntimeMode,
		"skills.assignments": skillNames, "skills.enabled": skillEnabled,
		"mcp.assignments": mcpNames, "permissions.mode": agent.PermissionMode,
		"permissions.allowlist": allowlist, "concurrency": agent.MaxConcurrentTasks,
	}
	if agent.Model.Valid {
		expected["runtime.model"] = agent.Model.String
	}
	if agent.ThinkingLevel.Valid {
		expected["runtime.thinking"] = agent.ThinkingLevel.String
	}
	if len(agent.Instructions) > 0 {
		hash := sha256.Sum256([]byte(agent.Instructions))
		expected["prompt.hash"] = "sha256:" + hex.EncodeToString(hash[:])
	}
	matrix, err := sessionAuditFiles.ReadFile("session_audit_matrix.json")
	if err != nil {
		return err
	}
	var completedAt string
	if task.CompletedAt.Valid {
		completedAt = task.CompletedAt.Time.UTC().Format(time.RFC3339Nano)
	}
	input := localSessionAuditInput{
		WorkspaceID:     util.UUIDToString(agent.WorkspaceID),
		RuntimeProvider: runtime.Provider,
		Task:            map[string]string{"id": util.UUIDToString(task.ID), "completed_at": completedAt},
		Manifest:        map[string]any{"schema_version": "1", "session_id": util.UUIDToString(task.ID), "agent": manifestAgent, "expected": expected},
		Snapshot:        map[string]any{"schema_version": "1", "fields": fields},
		Matrix:          json.RawMessage(matrix),
	}
	if task.IssueID.Valid {
		input.IssueID = util.UUIDToString(task.IssueID)
	}
	body, err := json.Marshal(input)
	if err != nil {
		return err
	}
	python := strings.TrimSpace(os.Getenv("MULTICA_SESSION_AUDIT_PYTHON"))
	if python == "" {
		python = "python3"
	}
	script, err := sessionAuditFiles.ReadFile("session_audit_hook.py")
	if err != nil {
		return err
	}
	commandCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
	defer cancel()
	cmd := exec.CommandContext(commandCtx, python, "-c", string(script))
	cmd.Stdin = strings.NewReader(string(body))
	cmd.Env = os.Environ()
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("session audit hook invocation failed (%T): %w; output=%s", err, err, strings.TrimSpace(string(output)))
	}
	slog.Info("session audit hook completed", "task_id", util.UUIDToString(task.ID), "result", strings.TrimSpace(string(output)))
	return nil
}
