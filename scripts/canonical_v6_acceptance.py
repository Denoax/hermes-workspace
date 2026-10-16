"""Generate the exact preserved v5 plus additive v6 acceptance inventory."""
import argparse
import json
from pathlib import Path

import canonical_v5_acceptance as shared
from v6_review_profile import options


def generate(root, public, review, inspector=None):
    return shared.generate(root, public, review, inspector, **options())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'public', 'review'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.root.resolve(), args.public.resolve(), args.review.resolve())
    print(json.dumps({'summary': result['acceptance']['summary'],
                      'required_review_files': result['required_review_files']}, indent=2))


if __name__ == '__main__':
    main()
