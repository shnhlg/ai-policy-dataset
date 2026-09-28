"""Small read-only warm-request benchmark, not a capacity/load test."""
import argparse
import concurrent.futures
import json
import math
import statistics
import time
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8765')
parser.add_argument('--runs', type=int, default=30)
args = parser.parse_args()
if not 3 <= args.runs <= 1000:
    parser.error('--runs must be between 3 and 1000')


def request(path):
    started = time.perf_counter()
    with urllib.request.urlopen(args.url + path, timeout=30) as response:
        json.load(response)
    return (time.perf_counter() - started) * 1000


def summary(times):
    return {'median_ms': round(statistics.median(times), 2),
            'p95_ms': round(sorted(times)[math.ceil(len(times) * .95) - 1], 2),
            'max_ms': round(max(times), 2), 'requests': len(times)}


cases = {'default': '/api/search?relevance=high&page_size=20', 'stats': '/api/stats',
         'short_AI': '/api/search?q=AI&relevance=high', 'late_page': '/api/search?relevance=all&page=500&page_size=20'}
output = {}
for name, path in cases.items():
    request(path)
    output[name] = summary([request(path) for _ in range(args.runs)])
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    started = time.perf_counter()
    times = list(pool.map(request, [cases['default']] * 4))
    output['four_concurrent'] = {**summary(times), 'wall_ms': round((time.perf_counter() - started) * 1000, 2)}
print(json.dumps(output, indent=2))
