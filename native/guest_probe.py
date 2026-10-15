#!/usr/bin/python3
"""Fixed read-only guest installation and native policy probes, no conversations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True

SELF = Path('/usr/local/lib/mani-vmlab-setup/guest_probe.py')
INSTALL = Path('/usr/local/lib/mani-vmlab')


def firewall():
    raw = subprocess.check_output(['/usr/bin/nft', '-j', 'list', 'ruleset'], timeout=10)
    rules = json.loads(raw)['nftables']
    chains = [x['chain'] for x in rules if 'chain' in x and 'hook' in x['chain']]
    summary = [{k:c[k] for k in ('family', 'table', 'name', 'hook', 'policy') if k in c} for c in chains]
    # Address/peer values remain root-private. A manager state is never evidence.
    Path('/var/lib/mani-vmlab-setup/post-reboot-firewall.private.json').write_bytes(raw)
    input_drop = any(c.get('family') == 'inet' and c.get('hook') == 'input' and c.get('policy') == 'drop' for c in chains)
    return {'base_chains': summary, 'dual_stack_input_default_drop': input_drop,
            'ruleset_sha256': hashlib.sha256(raw).hexdigest(),
            'physical_LAN_WAN_tested': False, 'configuration_changed': False}


def main():
    if os.geteuid() != 0 or Path(__file__).absolute() != SELF:
        raise SystemExit('protected_guest_probe_only')
    sys.path.insert(0, str(INSTALL))
    import supervisor
    supervisor.protected(SELF)
    supervisor.protected(SELF.parent)
    supervisor.initialize_imports()
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('hermes', 'firewall'))
    args = parser.parse_args()
    if args.operation == 'firewall':
        print(json.dumps(firewall()))
        return
    control = supervisor.Supervisor()
    run_id = control.active_run()
    if not run_id or not control.store.read(run_id).get('control_verified'):
        raise RuntimeError('live_pinned_no_agent_control_required')
    control.store.heartbeat(run_id)
    results = {}
    for role in ('controller', 'worker_a', 'worker_b'):
        results[role] = control.ssh(run_id, role, 'hermes_health')
        control.store.heartbeat(run_id)
    print(json.dumps({'run_id': run_id, 'guest_Hermes_imports': results, 'conversations': 0}))


if __name__ == '__main__':
    main()
