"""Remove repeated CSV columns only when their values agree in every row."""
import argparse
import collections
import csv
import os
from pathlib import Path
import tempfile


def normalize(path: Path) -> bool:
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.reader(source)
        header = next(reader)
        groups = collections.defaultdict(list)
        for index, field in enumerate(header):
            groups[field].append(index)
        if len(groups) == len(header):
            return False
        selected = [indices[0] for indices in groups.values()]
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='', dir=path.parent,
                                         prefix='headers-', suffix='.tmp', delete=False) as target:
            temporary = Path(target.name)
            try:
                writer = csv.writer(target)
                writer.writerow(list(groups))
                for number, row in enumerate(reader, 2):
                    if len(row) != len(header):
                        raise ValueError(f'Row {number}: incorrect field count')
                    for field, indices in groups.items():
                        if len({row[index] for index in indices}) != 1:
                            raise ValueError(f'Row {number}: conflicting values for {field}')
                    writer.writerow([row[index] for index in selected])
            except BaseException:
                target.close()
                temporary.unlink(missing_ok=True)
                raise
    os.replace(temporary, path)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    print('Duplicate columns removed' if normalize(args.path.resolve()) else 'No duplicate columns')
