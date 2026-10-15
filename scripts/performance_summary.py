"""Summarize retained CPU/browser samples; never infer GPU or display FPS."""
import argparse
import bisect
import json
import math
from pathlib import Path


def distribution(values):
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values):
        raise ValueError('finite_nonnegative_measurements_required')
    ordered = sorted(values)
    if not ordered:
        return {'count': 0, 'p50_ms': None, 'p95_ms': None, 'p99_ms': None, 'max_ms': None}
    def nearest_rank(fraction):return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]
    return {'count': len(ordered), 'p50_ms': nearest_rank(.5), 'p95_ms': nearest_rank(.95),
            'p99_ms': nearest_rank(.99), 'max_ms': ordered[-1]}


def summarize(raw):
    if raw.get('schema') != 'hermes-cpu-performance-v1' or raw.get('duration_ms') is None:
        raise ValueError('stopped_performance_sample_required')
    marks = raw['marks']
    starts = [mark['at_ms'] for mark in marks]
    if starts != sorted(starts):raise ValueError('ordered_phase_marks_required')
    def bucket():return {'frames': [], 'visible_frames': [], 'longtasks': [], 'inputs': [],
                          'input_handler': [], 'pending_inputs': 0, 'crossing_phase_measurements': 0}
    all_samples = bucket()
    groups = [bucket() for _mark in marks]
    unmarked = bucket()
    def add(kind, begin, end, value, visible=False):
        first = bisect.bisect_right(starts, begin) - 1
        last = bisect.bisect_right(starts, end) - 1
        destination = groups[first] if first >= 0 else unmarked
        all_samples[kind].append(value)
        if visible:all_samples['visible_frames'].append(value)
        if first != last:
            all_samples['crossing_phase_measurements'] += 1
            destination['crossing_phase_measurements'] += 1
        else:
            destination[kind].append(value)
            if visible:destination['visible_frames'].append(value)
    for row in raw['frames']:
        add('frames', row['from_ms'], row['to_ms'], row['interval_ms'], row['visible_entire_interval'])
    for row in raw['longtasks']:
        add('longtasks', row['at_ms'], row['at_ms'] + row['duration_ms'], row['duration_ms'])
    for row in raw['inputs']:
        first = bisect.bisect_right(starts, row['at_ms']) - 1
        destination = groups[first] if first >= 0 else unmarked
        if row['handler_to_next_raf_ms'] is None:
            all_samples['pending_inputs'] += 1
            destination['pending_inputs'] += 1
            continue
        add('input_handler', row['at_ms'], row['callback_at_ms'], row['handler_to_next_raf_ms'])
        if row['event_to_next_raf_ms'] is not None:
            add('inputs', row['at_ms'], row['callback_at_ms'], row['event_to_next_raf_ms'])
    def render(samples):
        return {'raf_interval_all': distribution(samples['frames']),
                'raf_interval_visible_entire_interval': distribution(samples['visible_frames']),
                'longtask_duration': distribution(samples['longtasks']),
                'trusted_event_to_next_raf_callback': distribution(samples['inputs']),
                'trusted_handler_to_next_raf_callback': distribution(samples['input_handler']),
                'inputs_without_next_callback': samples['pending_inputs'],
                'crossing_phase_measurements': samples['crossing_phase_measurements']}
    return {'status': 'MEASURED', 'scope': 'CPU/browser callbacks only; no GPU or presentation FPS measurement',
            'percentiles': 'nearest rank; adverse samples retained in the companion raw data',
            'duration_ms': raw['duration_ms'], 'stop_reason': raw['stop_reason'],
            'coverage_limited': raw['stop_reason'] != 'caller', 'browser': raw['browser'],
            'longtask_status': raw['longtask_status'], 'visibility': raw['visibility'],
            'ignored_untrusted_inputs': raw['ignored_untrusted_inputs'],
            'evidence_coverage': {'raf_intervals': len(raw['frames']), 'trusted_inputs': len(raw['inputs']),
                                  'phase_marks': len(marks), 'human_or_physical_input_approval': False},
            'overall': render(all_samples), 'unmarked': render(unmarked),
            'phases': [{**mark, 'until_ms': marks[index + 1]['at_ms'] if index + 1 < len(marks) else raw['duration_ms'],
                        **render(groups[index])} for index, mark in enumerate(marks)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.raw.stat().st_size > 32 * 1024 * 1024:raise ValueError('bounded_performance_report_required')
    report = summarize(json.loads(args.raw.read_text()))
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':main()
