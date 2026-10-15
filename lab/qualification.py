"""Independent report predicates: missing positive controls never count as denial."""


def network_supported(positive, guest_report, boundary):
    if type(positive) is not dict or positive.get('operation') != 'positive':
        return False
    endpoints = positive.get('endpoints')
    if type(endpoints) is not list or len(endpoints) != 4 or not all(value == {'responded': True} for value in endpoints):
        return False
    expected = {'host_v4', 'host_v6', 'owned_outside_v4', 'owned_outside_v6', 'DNS_v4', 'DNS_v6'}
    probes = guest_report.get('probes') if type(guest_report) is dict else None
    if type(probes) is not dict or set(probes) != expected:
        return False
    for name, result in probes.items():
        if type(result) is not dict:
            return False
        field = 'reply_received' if name.startswith('DNS') else 'connected'
        if result.get(field) is not False:
            return False
    if type(boundary) is not dict or boundary.get('operation') != 'counters':
        return False
    return boundary.get('endpoints') == [{'tcp': 0, 'udp': 0}]*4


def confinement_supported(observed):
    return type(observed) is dict and all(observed.get(field) is True for field in
        ('nonroot_dedicated_UID', 'private_network_namespace', 'private_IPC_namespace',
         'personal_home_absent', 'Docker_socket_absent', 'GPU_devices_absent',
         'capabilities_empty', 'memory_limit_observed', 'PID_limit_observed', 'UUID_matches'))
