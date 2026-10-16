"""Read-only translation between compositor and XWayland output origins.

XWayland may order named outputs differently. Never assume its root coordinates
are compositor coordinates, and never alter either output configuration.
"""
import json
import math
import re
import subprocess


def match_outputs(monitors, randr):
    outputs = {}
    for line in randr.splitlines():
        match = re.match(r'^([A-Za-z0-9_.-]+) connected(?: primary)? (\d+)x(\d+)([+-]\d+)([+-]\d+)\s', line)
        if match:
            name, width, height, x, y = match.groups()
            if name in outputs:
                raise RuntimeError('duplicate_X11_output')
            outputs[name] = (int(x), int(y), int(width), int(height))
    result = []
    for monitor in monitors:
        name = monitor.get('name')
        scale = monitor.get('scale')
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', name)
                or name not in outputs or type(scale) not in (float, int) or not math.isfinite(scale) or scale <= 0):
            raise RuntimeError('named_native_output_mapping_required')
        size = [monitor['width'] / scale, monitor['height'] / scale]
        if monitor.get('transform', 0) % 2:
            size.reverse()
        wayland = (monitor['x'], monitor['y'], *size)
        x11 = outputs[name]
        if (any(type(v) not in (float, int) or not math.isfinite(v) for v in wayland)
                or any(abs(a-b) > .01 for a,b in zip(size,x11[2:]))):
            raise RuntimeError('native_output_units_or_dimensions_differ')
        result.append((name, wayland, x11))
    if not result or len({row[0] for row in result}) != len(result) or set(outputs) != {row[0] for row in result}:
        raise RuntimeError('complete_unique_native_output_mapping_required')
    return tuple(sorted(result))


def read_layout():
    def read(args):
        value = subprocess.check_output(args, text=True, stderr=subprocess.PIPE, timeout=4)
        if len(value) > 256 * 1024:
            raise RuntimeError('native_output_metadata_limit')
        return value
    monitors = json.loads(read(['/usr/bin/hyprctl', 'monitors', '-j']))
    randr = read(['/usr/bin/xrandr', '--query', '--current'])
    return match_outputs(monitors, randr)


def translate_point(layout, x, y):
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in (x,y)):
        raise ValueError('finite_native_point_required')
    matches = [row for row in layout if row[1][0] <= x < row[1][0]+row[1][2]
               and row[1][1] <= y < row[1][1]+row[1][3]]
    if len(matches) != 1:
        raise RuntimeError('point_requires_one_named_native_output')
    _, wayland, x11 = matches[0]
    return (x - wayland[0] + x11[0], y - wayland[1] + x11[1])


def translate_rectangle(layout, position, size):
    x,y = position; width,height = size
    if any(type(v) not in (float,int) or not math.isfinite(v) or v <= 0 for v in size):
        raise ValueError('positive_native_rectangle_required')
    origin = translate_point(layout,x,y)
    # Retain the strict one-output capture requirement; a spanning window cannot
    # be attested with one translated origin.
    corner = translate_point(layout,x+width-.001,y+height-.001)
    if any(abs(a-b) > .01 for a,b in zip(corner,(origin[0]+width-.001,origin[1]+height-.001))):
        raise RuntimeError('native_window_spans_different_coordinate_origins')
    return origin, tuple(size)
