"""Fail-closed long1+short1 WATCH notification policy.

No order, no READY, no use of trade executor.
Distinguishes discovery of a move from a recommendation to enter.
"""
from __future__ import annotations
from collections.abc import Mapping
from tg_bot.signal_center_v1 import SignalDispatcher

PILOT_BOTS=frozenset({'LONG1','SHORT1'})
SENDABLE=frozenset({'STRONG_WATCH','EXTREME_WATCH'})
def candidate(symbol,bot,scanner,closed_price,*,observed_at_ms,allocations):
    if bot not in PILOT_BOTS:return None
    if not isinstance(allocations,Mapping) or symbol not in allocations.get(bot,()):
        return None
    if not isinstance(scanner,Mapping) or scanner.get('status') not in SENDABLE:
        return None
    if scanner.get('direction')!=('LONG' if bot=='LONG1' else 'SHORT'):
        return None
    if (scanner.get('telegram_ready') is not False or
        scanner.get('order_authorized') is not False or
        scanner.get('last_completed_1m_close_ms') is None):
        return None
    if scanner['last_completed_1m_close_ms']>observed_at_ms:return None
    return {'symbol':symbol,'strategy':bot,'state':'WATCH',
        'observed_at_ms':observed_at_ms,'price':closed_price,
        'reason':f"{scanner['reason']} / {scanner['status']}"}
def dispatch_candidate(dispatcher:SignalDispatcher,symbol,bot,scanner,
                       closed_price,*,observed_at_ms,allocations):
    item=candidate(symbol,bot,scanner,closed_price,
                   observed_at_ms=observed_at_ms,allocations=allocations)
    if item is None:return 'PILOT_FILTERED'
    return dispatcher.dispatch(item,now_ms=observed_at_ms)
