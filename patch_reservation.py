import re

with open('oms_project/reservation_service.py', 'r') as f:
    content = f.read()

target = """                if get_available_capital is not None:
                    available_capital = Decimal(str(get_available_capital(account_id)))
                else:"""

replacement = """                if get_available_capital is not None:
                    base_capital = Decimal(str(get_available_capital(account_id)))
                    cursor.execute(
                        "SELECT COALESCE(SUM(reserved_cash), 0.0) FROM capital_reservations WHERE account_id = ? AND status = ?",
                        (account_id, ReservationStatus.ACTIVE.value)
                    )
                    active_row = cursor.fetchone()
                    active_res = Decimal(str(active_row[0])) if active_row and active_row[0] else Decimal("0.0")
                    available_capital = base_capital - active_res
                else:"""

content = content.replace(target, replacement)

with open('oms_project/reservation_service.py', 'w') as f:
    f.write(content)
