#!/bin/bash
# PR Template Validation Script
# Validates PR body before creation to prevent CI failures
# Part of Agent Improvement Plan - Phase 1.1 (Issue #159)

set -euo pipefail

# Configuration
DRY_RUN=false
PR_BODY_FILE=""
REPO_TYPE="backend"  # backend or client

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Validate PR body template before creating PR.

OPTIONS:
    --body-file FILE    Path to PR body markdown file (required)
    --repo TYPE         Repository type: backend or client (default: backend)
    --dry-run           Run validation without failing (exit code 0)
    -h, --help          Show this help message

EXIT CODES:
    0 - Validation passed (or dry-run mode)
    1 - Validation failed

EXAMPLE:
    $0 --body-file .tmp/pr-body.md
    $0 --body-file .tmp/pr-body.md --repo client --dry-run
EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --body-file)
            if [[ $# -lt 2 || "$2" == --* ]]; then
                echo -e "${RED}Error: --body-file requires a file path${NC}"
                exit 1
            fi
            PR_BODY_FILE="$2"
            shift 2
            ;;
        --repo)
            if [[ $# -lt 2 || "$2" == --* ]]; then
                echo -e "${RED}Error: --repo requires a value (backend|client)${NC}"
                exit 1
            fi
            REPO_TYPE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Error: Unknown option $1${NC}"
            usage
            ;;
    esac
done

# Validate inputs
if [[ -z "$PR_BODY_FILE" ]]; then
    echo -e "${RED}Error: --body-file is required${NC}"
    usage
fi

if [[ ! -f "$PR_BODY_FILE" ]]; then
    echo -e "${RED}Error: PR body file not found: $PR_BODY_FILE${NC}"
    exit 1
fi

if [[ "$REPO_TYPE" != "backend" && "$REPO_TYPE" != "client" ]]; then
    echo -e "${RED}Error: invalid --repo value '$REPO_TYPE' (expected: backend|client)${NC}"
    exit 1
fi

# Validation state
ERRORS=0
WARNINGS=0

error() {
    echo -e "${RED}❌ ERROR: $1${NC}"
    ERRORS=$((ERRORS + 1))
}

warning() {
    echo -e "${YELLOW}⚠️  WARNING: $1${NC}"
    WARNINGS=$((WARNINGS + 1))
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

info() {
    echo -e "ℹ️  $1"
}

# Validation functions

validate_required_sections() {
    info "Checking required sections..."

    local section_labels=()
    local section_patterns=()

    if [[ "$REPO_TYPE" == "backend" ]]; then
        section_labels=(
            "## Goal / Context"
            "## Acceptance Criteria"
            "## Validation Evidence"
            "## Repo Hygiene / Safety"
        )
        section_patterns=(
            '^##[[:space:]]+Goal[[:space:]]*/[[:space:]]*Context[[:space:]]*$'
            '^##[[:space:]]+Acceptance[[:space:]]+Criteria[[:space:]]*$'
            '^##[[:space:]]+Validation[[:space:]]+Evidence[[:space:]]*$'
            '^##[[:space:]]+Repo[[:space:]]+Hygiene[[:space:]]*/[[:space:]]*Safety[[:space:]]*$'
        )
    else
        section_labels=(
            "# Summary"
            "## Goal / Acceptance Criteria (required)"
            "## Issue / Tracking Link (required)"
            "## Validation (required)"
            "## Automated checks"
            "## Manual test evidence (required)"
        )
        section_patterns=(
            '^#[[:space:]]+Summary[[:space:]]*$'
            '^##[[:space:]]+Goal[[:space:]]*/[[:space:]]*Acceptance[[:space:]]+Criteria[[:space:]]*\(required\)[[:space:]]*$'
            '^##[[:space:]]+Issue[[:space:]]*/[[:space:]]*Tracking[[:space:]]+Link[[:space:]]*\(required\)[[:space:]]*$'
            '^##[[:space:]]+Validation[[:space:]]*\(required\)[[:space:]]*$'
            '^##+[[:space:]]+Automated[[:space:]]+checks[[:space:]]*$'
            '^##+[[:space:]]+Manual[[:space:]]+test[[:space:]]+evidence[[:space:]]*\(required\)[[:space:]]*$'
        )
    fi

    local idx
    for idx in "${!section_labels[@]}"; do
        local label="${section_labels[$idx]}"
        local pattern="${section_patterns[$idx]}"

        if grep -Eqi "$pattern" "$PR_BODY_FILE"; then
            success "Found: $label"
        else
            error "Missing required section: $label"
        fi
    done
}

validate_evidence_format() {
    info "Checking evidence format..."

    # Check for fenced code blocks inside validation/manual evidence sections (bad)
    if awk '
        BEGIN { in_section=0; bad=0 }
        /^##[[:space:]]+(Validation( Evidence)?|Manual test evidence)/ { in_section=1; next }
        /^##[[:space:]]+/ { in_section=0 }
        in_section && /```/ { bad=1 }
        END { exit bad ? 0 : 1 }
    ' "$PR_BODY_FILE"; then
        error 'Evidence must be in inline format, not code blocks (```).'
        echo "  → Use: ✅ npm test -- PASS (10 tests), ✅ npm run lint -- OK"
        echo "  → Not: \`\`\`bash ... \`\`\`"
    else
        success "Evidence format correct (inline, no code blocks)"
    fi
    
    # Check for placeholder evidence
    if grep -iE '(TBD|TODO|paste output here|add evidence|pending|will add|coming soon)' "$PR_BODY_FILE" | grep -v '^#' | grep -v '<!--' >/dev/null; then
        error "Evidence contains placeholders (TBD, TODO, 'paste output here', etc.)"
        echo "  → Add real validation evidence before creating PR"
    else
        success "No placeholder evidence found"
    fi
}

validate_checkboxes() {
    info "Checking required checkboxes..."
    
    # Count total checkboxes
    total_checkboxes=$(grep -c '\[ \]' "$PR_BODY_FILE" || true)
    checked_boxes=$(grep -c '\[x\]' "$PR_BODY_FILE" || true)
    checked_boxes_alt=$(grep -c '\[X\]' "$PR_BODY_FILE" || true)
    total_checked=$((checked_boxes + checked_boxes_alt))
    
    if [[ $total_checkboxes -gt 0 ]]; then
        if [[ $total_checked -eq 0 ]]; then
            error "Found $total_checkboxes unchecked boxes. All must be checked before PR creation."
        else
            local unchecked_boxes=$((total_checkboxes - total_checked))
            warning "Found $total_checkboxes total checkboxes, $total_checked checked, $unchecked_boxes unchecked."
            echo "  → Verify all boxes should be checked per PR review gate"
        fi
    else
        if [[ $total_checked -gt 0 ]]; then
            success "All checkboxes checked ($total_checked)"
        else
            info "No checkboxes found (this may be OK depending on PR type)"
        fi
    fi
}

validate_fixes_format() {
    info "Checking Fixes: format..."
    
    # Check for Fixes: line
    if grep -q '^Fixes: ' "$PR_BODY_FILE"; then
        fixes_line=$(grep '^Fixes: ' "$PR_BODY_FILE")
        
        # Check format: #N or owner/repo#N
        if echo "$fixes_line" | grep -qE '^Fixes: (#[0-9]+|[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+#[0-9]+)$'; then
            success "Fixes: format correct: $fixes_line"
        else
            error "Fixes: format incorrect. Use 'Fixes: #N' or 'Fixes: owner/repo#N'"
            echo "  → Found: $fixes_line"
        fi
    else
        warning "No 'Fixes:' line found. Add if this PR closes an issue."
    fi
}

validate_cross_repo_impact() {
    info "Checking cross-repo impact documentation..."
    
    if grep -qE '(cross.?repo|client|backend|multi.?repo)' "$PR_BODY_FILE"; then
        success "Cross-repo impact mentioned"
    else
        info "No cross-repo impact mentioned (OK if single-repo PR)"
    fi
}

validate_minimum_length() {
    info "Checking PR body minimum length..."
    
    line_count=$(wc -l < "$PR_BODY_FILE")
    word_count=$(wc -w < "$PR_BODY_FILE")
    
    if [[ $line_count -lt 10 ]]; then
        warning "PR body very short ($line_count lines). Consider adding more detail."
    elif [[ $word_count -lt 50 ]]; then
        warning "PR body very short ($word_count words). Consider adding more detail."
    else
        success "PR body length adequate ($line_count lines, $word_count words)"
    fi
}

# Run all validations
echo "========================================="
echo "PR Template Validation"
echo "========================================="
echo "File: $PR_BODY_FILE"
echo "Repo Type: $REPO_TYPE"
echo "Dry Run: $DRY_RUN"
echo "========================================="
echo ""

validate_required_sections
echo ""
validate_evidence_format
echo ""
validate_checkboxes
echo ""
validate_fixes_format
echo ""
validate_cross_repo_impact
echo ""
validate_minimum_length

# Summary
echo ""
echo "========================================="
echo "Validation Summary"
echo "========================================="

if [[ $ERRORS -gt 0 ]]; then
    echo -e "${RED}❌ FAILED: $ERRORS error(s), $WARNINGS warning(s)${NC}"
    echo ""
    echo "Fix errors before creating PR to avoid CI failures."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "(Dry run mode: exiting with success)"
        exit 0
    else
        exit 1
    fi
elif [[ $WARNINGS -gt 0 ]]; then
    echo -e "${YELLOW}⚠️  PASSED with warnings: $WARNINGS warning(s)${NC}"
    echo ""
    echo "Consider addressing warnings to improve PR quality."
    exit 0
else
    echo -e "${GREEN}✅ PASSED: PR template validation successful!${NC}"
    exit 0
fi
