package cli

import (
	"strings"
	"testing"
)

func TestValidatePRURLMetadata(t *testing.T) {
	t.Setenv("MULTICA_GOVERNANCE_PR_URL_ALLOWED_OWNER", "vanderzege-alt")

	tests := []struct {
		name    string
		value   string
		wantErr bool
	}{
		{"fork multica ok", "https://github.com/vanderzege-alt/multica/pull/3", false},
		{"fork governance ok", "https://github.com/vanderzege-alt/multica-org-governance/pull/53", false},
		{"upstream multica blocked", "https://github.com/multica-ai/multica/pull/7852", true},
		{"wrong owner blocked", "https://github.com/other-org/multica/pull/1", true},
		{"not a PR URL", "https://github.com/vanderzege-alt/multica", true},
		{"empty blocked", "", true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := ValidatePRURLMetadata(tt.value)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ValidatePRURLMetadata(%q) err=%v wantErr=%v", tt.value, err, tt.wantErr)
			}
			if tt.wantErr && err != nil && tt.value != "" {
				msg := err.Error()
				if !strings.Contains(msg, "How to fix") || !strings.Contains(msg, "UPSTREAM_FORK_POLICY") {
					t.Fatalf("expected actionable hint, got: %v", err)
				}
			}
		})
	}
}
