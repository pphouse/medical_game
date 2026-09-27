"""本番に貼る SQL（scripts/sql/）が、科目立てと同梱データに追いついているかを見る。

本番はデプロイで migrate を流さないので、分野の直しは SQL Editor に SQL を
貼って当てている。その SQL が古いままだと、直した分野を古い分類へ書き戻す
（科目立てを変えた後も古い apply_categories.sql が残っていて、流すと国試に
「放射線科」の行が戻るところだった）。確認用の verify_state.sql も科目の一覧を
持っているので、古いと、直した後の本番を「科目名でない」と誤って報告する。

fix_categories.sql の生成スクリプトは Django を起動せずに seed_demo を読むため
django のモジュールを差し替える。同じプロセスで動かすと後続のテストが壊れるので
サブプロセスで動かす。
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from quiz.categories import CATEGORIES_BY_EXAM

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "scripts" / "sql"


def test_fix_categories_sql_is_up_to_date(tmp_path):
    out = tmp_path / "fix_categories.sql"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_category_fix_sql.py"), str(out)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    shipped = (SQL_DIR / "fix_categories.sql").read_text(encoding="utf-8")
    assert out.read_text(encoding="utf-8") == shipped, (
        "同梱データか科目立てが変わっている。python scripts/build_category_fix_sql.py で作り直す"
    )


@pytest.mark.parametrize("exam", sorted(CATEGORIES_BY_EXAM))
def test_verify_state_uses_the_current_categories(exam):
    sql = (SQL_DIR / "verify_state.sql").read_text(encoding="utf-8")
    lists = re.findall(rf"exam_type = '{exam}'\s+AND category NOT IN \(([^)]*)\)", sql)
    assert len(lists) == 1, f"verify_state.sql に {exam} の科目の一覧が見つからない"
    assert sorted(re.findall(r"'([^']*)'", lists[0])) == sorted(CATEGORIES_BY_EXAM[exam])
