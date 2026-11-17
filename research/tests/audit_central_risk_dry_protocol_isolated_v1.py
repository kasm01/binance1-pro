"""Historical central DRY service audit, superseded by owner-bound CAS.

Earlier versions demonstrated unsafe unowned and late RELEASE. This regression
now requires the patched production service to reject those attempts against
a real isolated Redis instance. No live Redis/Binance access.
"""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).resolve().with_name(
 'test_stage25_central_dry_owner_release_isolated_redis.py')),run_name='__main__')
print('PASS historical unowned/late DRY release vulnerability is now blocked')
