"""Collect installed pinned npm notices for the self-hosted frontend bundle."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT/'workspace/frontend'


def main():
    lock = json.loads((FRONTEND/'package-lock.json').read_text())
    sections = ['# Pinned frontend package notices\n\nGenerated from package-lock.json and installed package license files.\n']
    for relative, item in sorted(lock['packages'].items()):
        if not relative:
            continue
        directory = FRONTEND/relative
        if not directory.exists() and item.get('optional'):
            continue  # Other-platform build helpers are not installed/bundled.
        package = json.loads((directory/'package.json').read_text())
        text = f"\n## {package['name']} {item['version']}\n\nDeclared license: {package.get('license', item.get('license', 'see upstream package'))}\n"
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.name.lower().split('.')[0] in ('license', 'licence', 'copying', 'notice'):
                text += '\n'+path.name+'\n\n'+path.read_text(errors='replace')+'\n'
        sections.append(text)
    target = ROOT/'workspace/ui/licenses/Frontend-packages.txt'
    target.write_text('\n'.join(line.rstrip() for line in ''.join(sections).splitlines()).rstrip()+'\n')
    print(f'{len(sections)-1} pinned package notices collected')


if __name__ == '__main__':
    main()
