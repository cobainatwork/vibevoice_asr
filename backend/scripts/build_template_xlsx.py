"""一次性生成 dataset_template.xlsx；commit 結果到 git，不在 runtime 跑。"""
from pathlib import Path
from openpyxl import Workbook


def build():
    wb = Workbook()
    ws = wb.active
    ws.title = "dataset"
    ws.append(["start_time", "end_time", "speaker", "text"])
    ws.append([0.00, 3.45, 0, "各位早安，今天我們要討論糖尿病"])
    ws.append([3.45, 7.20, 1, "是的，胰島素分泌不足是主因"])
    out = Path(__file__).parent.parent / "templates" / "dataset_template.xlsx"
    wb.save(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    build()
