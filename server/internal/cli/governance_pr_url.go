package cli

import (
	"fmt"
	"net/url"
	"os"
	"regexp"
	"strings"
)

const defaultPRURLAllowedOwner = "vanderzege-alt"

var githubPRPathRE = regexp.MustCompile(`^/([^/]+)/([^/]+)/pull/([0-9]+)/?$`)

// ValidatePRURLMetadata rejects upstream or non-fork PR links for issue metadata.
// SSOT: multica-org-governance docs/UPSTREAM_FORK_POLICY.md
func ValidatePRURLMetadata(raw string) error {
	value := strings.TrimSpace(raw)
	if value == "" {
		return fmt.Errorf("pr_url value is empty")
	}

	u, err := url.Parse(value)
	if err != nil {
		return fmt.Errorf("pr_url is not a valid URL: %w", err)
	}
	if !strings.EqualFold(u.Scheme, "https") || !strings.EqualFold(u.Host, "github.com") {
		return prURLViolation("pr_url must be a GitHub pull request URL (https://github.com/<owner>/<repo>/pull/<n>)", "", "")
	}

	m := githubPRPathRE.FindStringSubmatch(u.Path)
	if m == nil {
		return prURLViolation("pr_url must be a GitHub pull request URL (https://github.com/<owner>/<repo>/pull/<n>)", "", "")
	}

	owner := strings.ToLower(m[1])
	repo := strings.ToLower(m[2])
	allowedOwner := strings.ToLower(strings.TrimSpace(os.Getenv("MULTICA_GOVERNANCE_PR_URL_ALLOWED_OWNER")))
	if allowedOwner == "" {
		allowedOwner = defaultPRURLAllowedOwner
	}

	if owner != allowedOwner {
		return prURLViolation(
			fmt.Sprintf("pr_url must point to %s/* (got %s/%s)", allowedOwner, owner, repo),
			allowedOwner,
			allowedOwner+"/"+repo,
		)
	}

	if owner == "multica-ai" {
		return prURLViolation("pr_url must not reference multica-ai/* upstream org", allowedOwner, "vanderzege-alt/multica")
	}

	return nil
}

func prURLViolation(msg, allowedOwner, forkRepo string) error {
	if allowedOwner == "" {
		allowedOwner = defaultPRURLAllowedOwner
	}
	if forkRepo == "" {
		forkRepo = allowedOwner + "/<repo>"
	}
	return fmt.Errorf(
		"%s\nAllowed format: https://github.com/%s/<repo>/pull/<number>\nHow to fix:\n  1. Open PR on fork: gh pr create --repo %s --base main --head <branch>\n  2. Set metadata: multica issue metadata set <issue-id> --key pr_url --value https://github.com/%s/pull/N\nSSOT: UPSTREAM_FORK_POLICY.md · ISSUE_METADATA_CONTRACT.md",
		msg,
		allowedOwner,
		forkRepo,
		forkRepo,
	)
}
