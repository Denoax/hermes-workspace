"""Exact additive v6 inventory; historic v5 helpers keep their 36-row defaults."""

V5_TASK_IDS = (
    'BASE-01', 'PREP-LOOP', 'NATIVE-01', 'LOOP-01', 'UI-01', 'UI-02', 'UI-03', 'UI-04',
    'REF-R01', 'REF-R02', 'REF-R03', 'REF-R04', 'REF-R05', 'REF-R06', 'REF-R07', 'REF-R08',
    'REF-R09', 'REF-R10', 'REF-R11', 'PERM-01', 'CHAT-01', 'CHAT-02', 'CHAT-03', 'METRIC-01',
    'VM-01', 'VM-02', 'VM-03', 'VOICE-01', 'ACC-01', 'PERF-01', 'RECOVERY-01', 'SOURCE-01',
    'ZIP-01', 'PHYSICAL-01', 'REBOOT-01', 'HUMAN-01',
)
V6_TASK_IDS = (
    'V6-BASE', 'V6-ZIP', 'V6-SCOPE', 'V6-NAV', 'V6-TARGET', 'V6-MENUS', 'V6-SURFACES',
    'V6-READ', 'V6-STYLE', 'V6-RESP', 'V6-MOTION', 'V6-PERF', 'V6-IMPORT', 'V6-VOICE',
    'V6-PERMISSIONS', 'V6-CHAT', 'V6-PRESERVE', 'V6-GAPS', 'V6-SOURCE', 'V6-RETURN',
    'V6-HUMAN',
)
TASK_IDS = V5_TASK_IDS + V6_TASK_IDS
NAME = 'MANI_HERMES_V6_COMPLETE_REVIEW'


def options():
    return {'expected_rows': len(TASK_IDS), 'expected_ids': TASK_IDS}
