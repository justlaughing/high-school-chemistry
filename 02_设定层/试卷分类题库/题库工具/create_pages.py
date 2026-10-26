"""Build all entry pages from the shared template; original questions are untouched."""
from pathlib import Path
import argparse
import html
import os

ROOT = Path(__file__).resolve().parent.parent

def build(root=ROOT, entry_root=None):
    root = Path(root).resolve()
    entry_root = Path(entry_root).resolve() if entry_root else root.parent.parent
    template = (root / '题库工具' / 'page.html').read_text(encoding='utf-8')
    def page(base, view='library'):
        return template.replace('{{BASE}}', html.escape(base, quote=True)).replace('{{VIEW}}', view)
    for name, view in [('阅读入口.html', 'library'), ('分类概况.html', 'overview')]:
        (root / name).write_text(page('./', view), encoding='utf-8')
    relative = os.path.relpath(root, entry_root).replace(os.sep, '/').rstrip('/') + '/'
    (entry_root / '题库首页.html').write_text(page(relative), encoding='utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--entry-root', type=Path)
    args = parser.parse_args()
    build(args.root, args.entry_root)
    print('题库入口已同步。')
