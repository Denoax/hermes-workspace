"""Reuse the verified committed-source packager for the corrective v4 release."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import package_chat_review as archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--review',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--verify',type=Path)
    parser.add_argument('--extract',type=Path)
    args=parser.parse_args()
    archive.NAME='MANI_HERMES_V4_COMPLETE_REVIEW'
    if args.verify:
        root,count=archive.verify(args.verify,args.extract)
        result={'root':str(root),'payloads_verified':count}
    else:
        result=archive.package(args.source,args.review,args.output)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
