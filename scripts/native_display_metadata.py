"""Read sanitized native monitor metadata; never modify display configuration."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import subprocess


def sanitize_monitors(rows):
    if not isinstance(rows, list) or len(rows) > 16:raise ValueError('bounded_native_monitors_required')
    result = []
    for row in rows:
        integer_keys = ('id', 'width', 'height', 'x', 'y', 'transform')
        if not isinstance(row, dict) or any(type(row.get(key)) is not int for key in integer_keys):
            raise ValueError('native_monitor_geometry_required')
        for key in ('scale', 'refreshRate'):
            value = row.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('native_monitor_scale_and_refresh_required')
        if not isinstance(row.get('name'), str) or len(row['name']) > 64:
            raise ValueError('native_monitor_connector_required')
        safe = {key: row[key] for key in integer_keys}
        safe.update(connector=row['name'], scale=row['scale'], refresh_hz=row['refreshRate'])
        for key in ('focused', 'disabled', 'dpmsStatus', 'vrr'):
            if type(row.get(key)) is bool:safe[key] = row[key]
        result.append(safe)
    return {'source': '/usr/bin/hyprctl -j monitors', 'scope': 'native compositor reported configuration; not measured presentation cadence',
            'monitors': result}


def collect():
    result = subprocess.run(['/usr/bin/hyprctl', '-j', 'monitors'], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=5, check=True)
    if len(result.stdout) > 256 * 1024:raise ValueError('bounded_native_monitor_reply_required')
    report = sanitize_monitors(json.loads(result.stdout))
    report['observed_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    return report


if __name__ == '__main__':print(json.dumps(collect(), indent=2, allow_nan=False))
