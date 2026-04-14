# report_generator.py
# generates sales reports

import json, csv, os
from datetime import datetime

class Report:
    def __init__(self, path, type, start, end):
        self.path = path
        self.type = type
        self.start = start
        self.end = end
        self.data = []
        self.total = 0
        self.errors = []

    def load(self):
        try:
            f = open(self.path)
            raw = json.load(f)
            f.close()
            for r in raw:
                d = datetime.strptime(r['date'], '%Y-%m-%d')
                if d >= datetime.strptime(self.start, '%Y-%m-%d') and d <= datetime.strptime(self.end, '%Y-%m-%d'):
                    if r['amount'] > 0:
                        self.data.append(r)
        except:
            self.errors.append('load failed')

    def process(self):
        try:
            if self.type == 1:
                for r in self.data:
                    self.total += r['amount']
            elif self.type == 2:
                vals = [r['amount'] for r in self.data]
                if vals:
                    self.total = sum(vals) / len(vals)
            elif self.type == 3:
                vals = [r['amount'] for r in self.data]
                if vals:
                    self.total = max(vals)
            else:
                self.errors.append('bad type')
        except:
            self.errors.append('process failed')

    def save(self, out):
        try:
            if out.endswith('.json'):
                f = open(out, 'w')
                json.dump({'total': self.total, 'rows': self.data, 'errs': self.errors}, f)
                f.close()
            elif out.endswith('.csv'):
                f = open(out, 'w', newline='')
                w = csv.DictWriter(f, fieldnames=['date', 'amount', 'product'])
                w.writeheader()
                for r in self.data:
                    w.writerow(r)
                f.close()
            else:
                self.errors.append('bad format')
        except:
            self.errors.append('save failed')

    def display(self):
        print('Report')
        print('Type:', self.type)
        print('From:', self.start, 'To:', self.end)
        print('Records:', len(self.data))
        print('Result:', self.total)
        if self.errors:
            print('Errors:', self.errors)


if __name__ == '__main__':
    import sys
    r = Report(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])
    r.load()
    r.process()
    r.save(sys.argv[5])
    r.display()
