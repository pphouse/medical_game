"""「腎・泌尿器」を「腎臓」と「泌尿器」の2科目に分ける。

腎臓（内科: 腎炎・ネフローゼ・腎不全・電解質）と泌尿器（外科: 前立腺・
膀胱・尿路結石・精巣）は診る科が違うので、まとめてあると目的の分野を
探しにくい。分けても両方10問を超える（CBT 26/25、国試 32/21）。

出題基準の D-8 は腎・尿路ひとまとめなので、設問文の語で振り分ける。
泌尿器にしか出てこない語（前立腺・膀胱・尿管…）を含むものだけを泌尿器に
移し、残りは腎臓にする。「血尿」「浮腫」のような腎臓側にも出る語は使わない。
"""

from django.db import migrations
from django.db.models import Q


def split(apps, schema_editor):
    from quiz.categories import UROLOGY_KEYWORDS

    Question = apps.get_model("quiz", "Question")
    old = Question.objects.filter(category__in=["腎・泌尿器", "腎・尿路系"])

    urology = Q()
    for keyword in UROLOGY_KEYWORDS:
        urology |= Q(question_text__contains=keyword)

    # 先に泌尿器ぶんを移し、残りを腎臓にする（順番を逆にすると全部腎臓になる）。
    urology_ids = list(old.filter(urology).values_list("pk", flat=True))
    Question.objects.filter(pk__in=urology_ids).update(category="泌尿器")
    old.update(category="腎臓")


def unsplit(apps, schema_editor):
    apps.get_model("quiz", "Question").objects.filter(
        category__in=["腎臓", "泌尿器"]
    ).update(category="腎・泌尿器")


class Migration(migrations.Migration):
    dependencies = [("quiz", "0016_consolidate_small_subjects")]

    operations = [migrations.RunPython(split, unsplit)]
