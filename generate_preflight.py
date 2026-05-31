import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd())))
from scripts.workflow_preflight_gate import record_preflight_evidence
record_preflight_evidence('issue-workflow', 'copilot-workspace', 'pass', exact_state={'branch': 'issue-635-llm-provider-registry'})
