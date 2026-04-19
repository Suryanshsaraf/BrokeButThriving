import json
from pathlib import Path

runs = Path('artifacts/public-benchmark-runs/run-002')
for task in ['wellbeing_regression', 'future_difficulty_classification']:
    m = json.loads((runs / task / 'metrics.json').read_text())
    print(f'TASK: {task}')
    print(f'  rows={m["row_count"]}  raw_features={m["raw_feature_count"]}  encoded_features={m["feature_count"]}')
    print(f'  sources={m["dataset_sources"]}')
    for model_name, metrics in m['model_metrics'].items():
        print(f'  MODEL: {model_name}')
        for k, v in metrics.items():
            print(f'    {k} = {v}')
    print()

sruns = Path('artifacts/sequence-runs/run-002')
sm = json.loads((sruns / 'metrics.json').read_text())
print('TASK: lstm_spend_sequence')
for k, v in sm.items():
    if not isinstance(v, dict):
        print(f'  {k} = {v}')
for model_name, metrics in sm.get('model_metrics', {}).items():
    print(f'  MODEL: {model_name}')
    for k, v in metrics.items():
        print(f'    {k} = {v}')
