#!/usr/bin/env python3
"""Versioned staged E6 exporter dispatcher. Defaults to the preserved v1 exporter."""
import runpy
import sys
from pathlib import Path

def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    use_v2='--e6-v2' in args
    if use_v2: args.remove('--e6-v2')
    target=Path(__file__).with_name('export_e6_v2_descriptive.py' if use_v2 else 'export_e6_descriptive_v1.py')
    sys.argv=[str(target),*args]
    runpy.run_path(str(target),run_name='__main__')

if __name__=='__main__':
    main()
