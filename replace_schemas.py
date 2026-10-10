import re
with open('oms_project/schemas.py', 'r') as f:
    content = f.read()
new_states = """
class OrderState(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    RISK_RESERVED = "RISK_RESERVED"
    SUBMITTING = "SUBMITTING"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    SUBMITTED = "SUBMITTED"
    LIVE = "LIVE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCEL_UNKNOWN = "CANCEL_UNKNOWN"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
"""
content = re.sub(r'class OrderState\(str, Enum\):.*?(?=\n\nclass)', new_states, content, flags=re.DOTALL)
with open('oms_project/schemas.py', 'w') as f:
    f.write(content)
