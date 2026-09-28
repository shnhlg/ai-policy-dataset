"""Configure the already-transferred raw directory; never copy or delete raw data."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    print('请填写以前数据包解压后的 data/raw 文件夹完整路径。')
    print('此操作只保存路径，不复制或删除原始文件。')
    raw = input('原始附件目录：').strip().strip('"')
    path = Path(raw).expanduser().resolve()
    if not raw or not path.is_dir():
        raise SystemExit('目录不存在，未保存。')
    if not any(p.suffix.lower() in {'.pdf', '.html'} for p in path.iterdir() if p.is_file()):
        raise SystemExit('该目录没有 PDF/HTML，请选择 data/raw 而不是它的上一级目录。')
    (ROOT/'raw-root.txt').write_text(str(path),encoding='utf-8')
    print('已保存。重新启动检索窗口即可。')
