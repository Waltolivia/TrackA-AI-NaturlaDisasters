"""Derive an operational phase from normalized alert fields.

This is deliberately separate from the database event lifecycle (ACTIVE/ENDED/COMPLETE).
"""
def phase(alert):
    text=f'{alert.event_type} {alert.headline}'.lower()
    status=(alert.status or '').lower()
    urgency=(alert.urgency or '').lower()
    certainty=(alert.certainty or '').lower()
    if status in {'ended','cancel','cancelled','expired'} or any(x in text for x in (' cancelled',' canceled',' expired')):
        return 'ENDED'
    if certainty == 'observed' and urgency == 'immediate':
        return 'ACTIVE_CONFIRMED'
    if urgency == 'immediate' or any(x in text for x in ('imminent','emergency')):
        return 'IMMINENT'
    if 'warning' in text:
        return 'WARNING'
    if 'watch' in text:
        return 'WATCH'
    if 'advisory' in text or 'statement' in text:
        return 'ADVISORY'
    if status == 'active':
        return 'ACTIVE'
    return 'MONITORING'
