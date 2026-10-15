"""Operator CLI; guest requests never reach this host interface."""
import argparse
import json
from pathlib import Path
import sys
from lab.doctor import inspect
from lab.process import stop_owned
from lab.report import blocked_matrix, write_results
from lab.state import RUN_ID, RunStore, atomic_json
from lab.native_client import NativeClient, public_snapshot
from lab.execution import execute_matrix
from lab.live import paired

PROJECT = Path(__file__).resolve().parents[1]
STATE = PROJECT.parent / "private-state"
RESULTS = PROJECT / "results"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("doctor", "provision", "qualify", "smoke", "run", "status", "stop", "cleanup", "report"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument('--normal-only', action='store_true')
    args = parser.parse_args(argv)
    if args.command == "doctor":
        result = inspect()
        print(json.dumps(result, indent=2))
        return 0
    if args.command in ("provision", "qualify", "smoke", "run"):
        readiness = inspect()
        stage = 'provision' if args.command == 'provision' else 'qualify' if args.command == 'qualify' else 'normal' if args.normal_only else 'paired'
        stage_result = readiness['stages'][stage]
        if (args.command in ('smoke','run') and not args.dry_run
                and readiness['native'].get('observed_facts',{}).get('inference_window_active')):
            cases=['B01','B04','B08'] if args.command=='smoke' else [f'B{i:02}' for i in range(1,13)]
            rows=paired(NativeClient(timeout=480),cases,RESULTS/args.command,
                        arms=('normal',) if args.normal_only else ('normal','abliterated'), run_id=args.run_id)
            print(json.dumps(write_results(RESULTS/args.command,rows),indent=2))
            return 0 if all(row['status']=='completed' for row in rows) else 2
        result = {"status": "blocked", "dry_run": args.dry_run,
                  "reason": "stage_prerequisites_missing", 'stage': stage, "blockers": stage_result['missing']}
        if args.dry_run:
            result.update(status='planned', native_operation=args.command, prerequisites_satisfied=stage_result['ready'])
            print(json.dumps(result, indent=2))
            return 0
        if stage_result['ready']:
            client = NativeClient(timeout=480)
            if args.command == 'provision':
                result = client.call('provision')
                print(json.dumps(result, indent=2))
                return 0 if result['status'] == 'ok' else 2
            run_id = args.run_id or readiness['native'].get('run_id')
            if not run_id:
                raise ValueError('native_run_id_required')
            if args.command == 'qualify':
                result = client.call('qualify', run_id=run_id)
                print(json.dumps(result, indent=2))
                return 0 if result['status'] == 'ok' else 2
            case_ids = ['B01', 'B04', 'B08'] if args.command == 'smoke' else [f'B{i:02}' for i in range(1, 13)]
            rows = execute_matrix(client, run_id, case_ids, arms=('normal',) if args.normal_only else ('normal', 'abliterated'))
            result = {'status': 'ok' if all(row['status'] == 'completed' for row in rows) else 'partial',
                      **write_results(RESULTS/args.command, rows)}
            print(json.dumps(result, indent=2))
            return 0 if result['status'] == 'ok' else 2
        if args.command in ("smoke", "run") and not args.dry_run:
            case_ids = ["B01", "B04", "B08"] if args.command == "smoke" else [f"B{i:02}" for i in range(1, 13)]
            directory = RESULTS / args.command
            result.update(write_results(directory, blocked_matrix(case_ids, result["reason"])))
            atomic_json(directory / "readiness.json", readiness)
        print(json.dumps(result, indent=2))
        return 2
    if args.command == "report":
        catalog = {}
        for directory in (RESULTS / "smoke", RESULTS / "run", RESULTS / "matrix"):
            path = directory / "trials.jsonl"
            if path.exists():
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                catalog[directory.name] = write_results(directory, rows)
        print(json.dumps(catalog, indent=2))
        return 0
    client = NativeClient(timeout=30)
    if client.available():
        if args.command == 'status':
            print(json.dumps(client.call('status'), indent=2))
            return 0
        if args.command in ('stop', 'cleanup'):
            if not args.run_id:
                parser.error('--run-id required')
            result = {'dry_run': True, 'native_operation': args.command, 'run_id': args.run_id} if args.dry_run else client.call(args.command, run_id=args.run_id)
            print(json.dumps(result, indent=2))
            return 0 if args.dry_run or result['status'] == 'ok' else 1
    store = RunStore(STATE)
    if args.command == "status" and not args.run_id:
        runs = [store.read(p.name) for p in store.root.iterdir()
                if RUN_ID.fullmatch(p.name) and p.is_dir()]
        snapshot=public_snapshot()
        if snapshot.get('reason')=='protected_native_status_snapshot_unavailable':snapshot['offline_fixture_ledger']=runs
        print(json.dumps(snapshot, indent=2))
        return 0
    if not args.run_id:
        parser.error("--run-id required")
    if args.command == "status":
        result = store.read(args.run_id)
    elif args.command == "stop":
        if args.dry_run:
            result = {"dry_run": True, "registered_roles": [p["role"] for p in store.read(args.run_id)["processes"]]}
        else:
            store.revoke(args.run_id, "operator_stop")
            result = stop_owned(store, args.run_id)
    else:
        result = store.cleanup(args.run_id, stop_owned, args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
