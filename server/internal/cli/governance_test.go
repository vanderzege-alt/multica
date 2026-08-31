package cli

import (
	"os"
	"path/filepath"
	"testing"
)

func writeGovernanceFixture(t *testing.T, root string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(root, ".multica"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(root, "multica-org-governance", "scripts"), 0o755); err != nil {
		t.Fatal(err)
	}
	guard := filepath.Join(root, "multica-org-governance", "scripts", "guard-upstream-repo.sh")
	script := `#!/usr/bin/env bash
case "$1" in
  check-url)
    if [[ "$2" == *"multica-ai/multica"* ]]; then
      echo "blocked upstream" >&2
      exit 1
    fi
    ;;
esac
exit 0
`
	if err := os.WriteFile(guard, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	cfg := `governance_root: multica-org-governance
hooks:
  pre_comment: multica-org-governance/scripts/pre-comment-stub.sh
  pre_repo_checkout: multica-org-governance/scripts/guard-upstream-repo.sh
`
	if err := os.WriteFile(filepath.Join(root, ".multica", "governance.yaml"), []byte(cfg), 0o644); err != nil {
		t.Fatal(err)
	}
	preComment := `#!/usr/bin/env bash
if grep -q "BAD" "$MULTICA_COMMENT_FILE"; then
  echo "comment blocked" >&2
  exit 1
fi
exit 0
`
	if err := os.WriteFile(filepath.Join(root, "multica-org-governance", "scripts", "pre-comment-stub.sh"), []byte(preComment), 0o755); err != nil {
		t.Fatal(err)
	}
}

func TestRunPreRepoCheckoutHookBlocksUpstream(t *testing.T) {
	root := t.TempDir()
	writeGovernanceFixture(t, root)
	t.Chdir(root)

	if err := RunPreRepoCheckoutHook("https://github.com/multica-ai/multica"); err == nil {
		t.Fatal("expected upstream checkout to be blocked")
	}
	if err := RunPreRepoCheckoutHook("https://github.com/vanderzege-alt/multica"); err != nil {
		t.Fatalf("fork checkout should pass: %v", err)
	}
}

func TestRunPreCommentHookBlocksBadContent(t *testing.T) {
	root := t.TempDir()
	writeGovernanceFixture(t, root)
	t.Chdir(root)

	if err := RunPreCommentHook("STATUS: DONE\nall good"); err != nil {
		t.Fatalf("good comment should pass: %v", err)
	}
	if err := RunPreCommentHook("STATUS: DONE\nBAD payload"); err == nil {
		t.Fatal("expected bad comment to be blocked")
	}
}

func TestFindGovernanceConfigWalksUp(t *testing.T) {
	root := t.TempDir()
	writeGovernanceFixture(t, root)
	nested := filepath.Join(root, "a", "b")
	if err := os.MkdirAll(nested, 0o755); err != nil {
		t.Fatal(err)
	}
	path, _, ok, err := FindGovernanceConfig(nested)
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected config")
	}
	want := filepath.Join(root, ".multica", "governance.yaml")
	if path != want {
		t.Fatalf("path = %q, want %q", path, want)
	}
}
