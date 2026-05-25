import re

with open('tests/test_ai_authority_routing.py', 'r') as f:
    text = f.read()

# We need to change required_phrases to include "preflight result evidence"
# and change the error messages to expect that.

new_text = text.replace(
'''    required_phrases = [
        "workflow preflight",
        "routing-manifest",
        "manifest-backed routing",
    ]''',
'''    required_phrases = [
        "preflight result evidence",
    ]''')

new_text = new_text.replace(
'''                    f"{wrapper}: missing workflow preflight or manifest-backed routing checks lock"''',
'''                    f"{wrapper}: missing requirement for preflight result evidence in handoff"''')

new_text = new_text.replace(
'''            "P0 wrappers must explicitly mention workflow preflight or manifest-backed routing checks before action:\\n"''',
'''            "P0 wrappers must require preflight result evidence in handoff or closeout:\\n"''')

with open('tests/test_ai_authority_routing.py', 'w') as f:
    f.write(new_text)
