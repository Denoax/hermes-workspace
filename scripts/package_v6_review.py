"""v6 fixed-root packaging with the same strict review/source/privacy checks."""
import argparse
import json
from pathlib import Path

import package_v5_review as shared
from v6_review_profile import NAME, options


def verify(archive, destination):
    return shared.verify(archive, destination, archive_name=NAME)


def package(public, review, review_files, output):
    return shared.package(public, review, review_files, output, archive_name=NAME, **options())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    for name in ('live', 'public', 'selection', 'destination'):
        export.add_argument('--' + name, type=Path, required=True)
    bundle = commands.add_parser('package')
    for name in ('public', 'review', 'review-files', 'output'):
        bundle.add_argument('--' + name, type=Path, required=True)
    audit = commands.add_parser('verify')
    audit.add_argument('archive', type=Path)
    audit.add_argument('destination', type=Path)
    args = parser.parse_args()
    if args.command == 'export':
        result = shared.export_source(args.live, args.public,
                                      json.loads(args.selection.read_text()), args.destination)
    elif args.command == 'package':
        result = package(args.public, args.review, json.loads(args.review_files.read_text()), args.output)
    else:
        root, count = verify(args.archive, args.destination)
        result = {'root': str(root), 'payloads_verified': count}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
