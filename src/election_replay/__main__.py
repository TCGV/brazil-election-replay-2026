"""CLI: python -m election_replay --help."""
import argparse
import json
import logging
from pathlib import Path
import sys

from .pipeline import run


def main():
    parser = argparse.ArgumentParser(description='Replay presidencial retrospectivo e aproximado — CSV, HTML e SVG.')
    parser.add_argument('--votes', type=Path, default=Path('data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv'))
    parser.add_argument('--details', type=Path, default=Path('data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv'))
    parser.add_argument('--output', type=Path, default=Path('output/replay'))
    parser.add_argument('--year', type=int, default=2026)
    parser.add_argument('--max-minutes', type=int, default=600000, help='Limite por eleição/turno/fonte; aborta em vez de truncar.')
    parser.add_argument('--synthetic', action='store_true', help='Marca explicitamente resultados de demonstração, não eleitorais.')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    try:
        summary = run(args.votes, args.details, args.output, year=args.year,
                      max_minutes=args.max_minutes, synthetic=args.synthetic)
    except (ValueError, OSError) as error:
        print(f'Não foi possível concluir: {error}', file=sys.stderr)
        return 2
    print(json.dumps({'status':summary['status'], 'output':str(args.output),
                      'elections':summary['replays'], 'charts':summary['charts']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
