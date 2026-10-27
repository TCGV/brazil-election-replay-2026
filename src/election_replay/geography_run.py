"""Reproduce the geographic timing analysis and its evidence bundle."""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import importlib.metadata
import json
import logging
from pathlib import Path
import subprocess
import sys

from .geography_data import build_analysis_database,file_hash


def run_analysis(replay_database:Path,details_csv:Path,output_dir:Path,randomizations=0,seed=20261027):
    if randomizations < 0 or seed < 0:
        raise ValueError('Randomizations and seed must be nonnegative integers')
    from .geography import analyze
    from .geography_controls import controls
    from .geography_charts import generate_charts
    from .geography_report import generate_report
    logging.info('Validating sources and preparing section geography')
    db=build_analysis_database(replay_database,details_csv,output_dir)
    manifest_path=output_dir/'analysis-manifest.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['status']='running'
    manifest['randomization_config']={'permutations':randomizations,'seed':seed}
    manifest['started_at_utc']=datetime.now(timezone.utc).isoformat()
    try:
        manifest['git_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        manifest['git_dirty']=bool(subprocess.check_output(['git','status','--porcelain'],text=True))
        manifest['implementation_sha256']={p.name:file_hash(p) for p in sorted(Path(__file__).parent.glob('geography*.py'))}
        manifest['dependencies']={name:importlib.metadata.version(name) for name in ['matplotlib','numpy']}
        logging.info('Computing timing, composition and decomposition')
        summary=analyze(db,output_dir)
        manifest['municipality_controls']=controls(db,output_dir)
        logging.info('Checking results independently against the original replay database')
        validation_script=Path(__file__).resolve().parents[2]/'scripts'/'validate_geography.py'
        subprocess.run([sys.executable,str(validation_script),'--replay-db',str(replay_database),
                        '--analysis-dir',str(output_dir)],check=True,stdout=subprocess.PIPE,text=True)
        manifest['independent_validation']=json.loads((output_dir/'independent-validation.json').read_text())
        if randomizations:
            from .geography_randomization import run_randomization
            logging.info('Testing section-order randomness: %s permutations, seed %s',randomizations,seed)
            manifest['randomization']=run_randomization(db,output_dir,permutations=randomizations,seed=seed)
            validation_script=Path(__file__).resolve().parents[2]/'scripts'/'validate_randomization.py'
            subprocess.run([sys.executable,str(validation_script),'--replay-db',str(replay_database),
                            '--analysis-dir',str(output_dir)],check=True,stdout=subprocess.PIPE,text=True)
            manifest['randomization_validation']=json.loads((output_dir/'randomization-validation.json').read_text())
        logging.info('Rendering scientific figures and consolidated report')
        manifest['figures']=generate_charts(output_dir)
        if randomizations:
            from .geography_randomization_charts import generate_charts as generate_randomization_charts
            manifest['figures'].extend(generate_randomization_charts(output_dir))
        manifest['reports']=generate_report(output_dir)
        manifest['status']='completed'
        manifest['completed_at_utc']=datetime.now(timezone.utc).isoformat()
        manifest['artifacts']=sorted(str(p.relative_to(output_dir)) for p in output_dir.rglob('*') if p.is_file() and p.suffix!='.sqlite')
        return summary
    except Exception as error:
        manifest['status']='failed'
        manifest['error']=str(error)
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    parser=argparse.ArgumentParser(description='Geographic timing analysis of both presidential replay rounds.')
    parser.add_argument('--replay-db',type=Path,default=Path('output/replay/replay.sqlite'))
    parser.add_argument('--details',type=Path,default=Path('data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv'))
    parser.add_argument('--output',type=Path,default=Path('output/geography'))
    parser.add_argument('--randomizations',type=int,default=0,
                        help='Number of section-order permutations; 0 preserves the descriptive workflow.')
    parser.add_argument('--seed',type=int,default=20261027,help='Reproducible randomization seed.')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    try:
        run_analysis(args.replay_db,args.details,args.output,randomizations=args.randomizations,seed=args.seed)
    except (ValueError,OSError) as error:
        print(f'Analysis failed: {error}',file=sys.stderr)
        return 2
    print(f'Completed: {args.output}/REPORT.pt-BR.md and report.html')
    return 0


if __name__=='__main__':
    sys.exit(main())
