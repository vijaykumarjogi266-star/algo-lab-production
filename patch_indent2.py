import re

with open('oms_project/database.py', 'r') as f:
    content = f.read()

new_transitions = """ALLOWED_TRANSITIONS = {
    OrderState.RECEIVED: {OrderState.VALIDATED, OrderState.REJECTED},
    OrderState.VALIDATED: {OrderState.RISK_RESERVED, OrderState.REJECTED},
    OrderState.RISK_RESERVED: {OrderState.SUBMITTING, OrderState.SUBMITTED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED},
    OrderState.SUBMITTING: {OrderState.SUBMITTED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED},
    OrderState.SUBMITTED: {OrderState.ACKNOWLEDGED, OrderState.SUBMISSION_UNKNOWN, OrderState.REJECTED, OrderState.FILLED, OrderState.LIVE},
    OrderState.SUBMISSION_UNKNOWN: {OrderState.ACKNOWLEDGED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.LIVE, OrderState.PARTIALLY_FILLED},
    OrderState.ACKNOWLEDGED: {OrderState.LIVE, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.CANCELLED, OrderState.REJECTED},
    OrderState.LIVE: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.CANCEL_UNKNOWN, OrderState.CANCELLED},
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCEL_PENDING, OrderState.CANCEL_UNKNOWN, OrderState.CANCELLED},
    OrderState.CANCEL_PENDING: {OrderState.CANCELLED, OrderState.CANCEL_UNKNOWN, OrderState.FILLED, OrderState.PARTIALLY_FILLED, OrderState.LIVE},
    OrderState.CANCEL_UNKNOWN: {OrderState.CANCELLED, OrderState.FILLED, OrderState.PARTIALLY_FILLED, OrderState.LIVE},
    OrderState.FILLED: set(),
    OrderState.CANCELLED: set(),
    OrderState.REJECTED: set(),
}"""

content = re.sub(r'ALLOWED_TRANSITIONS = \{.*?\}\n\nclass', new_transitions + '\n\nclass', content, flags=re.DOTALL)

with open('oms_project/database.py', 'w') as f:
    f.write(content)
