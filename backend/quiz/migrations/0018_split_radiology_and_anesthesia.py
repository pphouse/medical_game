"""放射線と麻酔を独立した科目に切り出す。

0016 で「放射線科」を医学総論へ、0013 で「麻酔」を救急・中毒・麻酔へ
まとめたが、どちらも問題数が10問に届かないことが理由だった。問題を
足して科目として成立する数になったので、独立した科目に戻す。

* 放射線 … CBT・国試の両方で科目にする。画像を使うだけの臨床問題は
  各科に残し、「何を問うているか」＝設問の最後の一文に放射線の語が
  出るものだけを移す（quiz.categories の DISCIPLINE_ASKED と同じ線引き）。
* 麻酔 … 国試だけ科目にする。残りは「救急・中毒」に名前を変える。
  CBT では麻酔の設問が無いので「救急・中毒・麻酔」のまま。

設問文で判定するので、どのデータベースで流しても同じ問題が動く。
"""

import re

from django.db import migrations

# 設問の最後の「〜はどれか。」に出たら、主題がその領域だと言い切れる語。
RADIOLOGY_MARKERS = (
    "放射線", "被曝", "被ばく", "線量", "核医学", "シンチグラ",
    "照射", "画像下治療", "IVR",
)
ANESTHESIA_MARKERS = (
    "麻酔", "気管挿管", "筋弛緩", "悪性高熱", "硬膜外",
    "脊髄くも膜下", "気道確保の手技", "鎮静",
)
# 上の語が出ても主題が別にある設問（制度を問うものが多い）。
EXCEPTIONS = ("母子健康手帳", "母子保健法", "検疫法", "社会保障", "医療費")

ASKED = re.compile(r"[^。\n]*か。")


def asked_sentence(text):
    """設問が何を問うているかの一文。「〜はどれか。」の最後のもの。"""
    found = ASKED.findall(text or "")
    return found[-1] if found else ""


def split(apps, schema_editor):
    Question = apps.get_model("quiz", "Question")

    # 1) 国試の「救急・中毒・麻酔」から麻酔を外し、科目名を改める。
    Question.objects.filter(
        exam_type="KOKUSHI", category="救急・中毒・麻酔"
    ).update(category="救急・中毒")

    # 2) 旧名を新しい科目名へ。0016 より前のデータベースにだけ残っている。
    Question.objects.filter(category__in=["放射線科", "放射線"]).update(
        category="放射線"
    )
    Question.objects.filter(
        exam_type="KOKUSHI", category__in=["麻酔", "麻酔科"]
    ).update(category="麻酔")

    # 3) 主題が放射線・麻酔そのものの設問を集める。
    to_radiology = []
    to_anesthesia = []
    for question in Question.objects.all().only(
        "id", "exam_type", "category", "question_text"
    ):
        text = question.question_text or ""
        if any(word in text for word in EXCEPTIONS):
            continue
        asked = asked_sentence(text)
        if any(marker in asked for marker in RADIOLOGY_MARKERS):
            if question.category != "放射線":
                to_radiology.append(question.id)
        elif question.exam_type == "KOKUSHI" and any(
            marker in asked for marker in ANESTHESIA_MARKERS
        ):
            if question.category != "麻酔":
                to_anesthesia.append(question.id)

    Question.objects.filter(id__in=to_radiology).update(category="放射線")
    Question.objects.filter(id__in=to_anesthesia).update(category="麻酔")


def noop(apps, schema_editor):
    """元の科目は残していないので、戻す操作は用意しない。"""


class Migration(migrations.Migration):
    dependencies = [("quiz", "0017_split_kidney_and_urology")]

    operations = [migrations.RunPython(split, noop)]
