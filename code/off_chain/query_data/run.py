"""off_chain: query_data. Replace with project methods after completing the author worksheet."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
from pipeline import cli
if __name__ == '__main__':
    cli('off_chain', 'query_data')
