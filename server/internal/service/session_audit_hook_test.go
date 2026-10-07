package service

import (
	"context"
	"errors"
	"testing"

	db "github.com/multica-ai/multica/server/pkg/db/generated"
)

func TestSessionAuditHookIsOptInForLocalBuilds(t *testing.T) {
	t.Setenv("MULTICA_SESSION_AUDIT_ENABLED", "false")
	if svc := NewTaskService(nil, nil, nil, nil); svc.SessionAudit != nil {
		t.Fatal("session audit hook enabled without explicit local opt-in")
	}
	t.Setenv("MULTICA_SESSION_AUDIT_ENABLED", "true")
	if svc := NewTaskService(nil, nil, nil, nil); svc.SessionAudit == nil {
		t.Fatal("session audit hook not enabled after explicit opt-in")
	}
}

func TestRunSessionAuditInvokesSharedHookOnlyForCompletedTasks(t *testing.T) {
	calls := 0
	svc := &TaskService{SessionAudit: func(_ context.Context, task db.AgentTaskQueue) error {
		calls++
		if task.Status != "completed" {
			t.Fatalf("hook received status %q", task.Status)
		}
		return nil
	}}
	svc.runSessionAudit(context.Background(), db.AgentTaskQueue{Status: "failed"})
	svc.runSessionAudit(context.Background(), db.AgentTaskQueue{Status: "completed"})
	if calls != 1 {
		t.Fatalf("hook calls = %d, want 1", calls)
	}
}

func TestRunSessionAuditFailureDoesNotReverseTaskCompletion(t *testing.T) {
	svc := &TaskService{SessionAudit: func(context.Context, db.AgentTaskQueue) error {
		return errors.New("synthetic generator failure")
	}}
	// Completion is already committed; audit errors are logged for recovery.
	svc.runSessionAudit(context.Background(), db.AgentTaskQueue{Status: "completed"})
}
