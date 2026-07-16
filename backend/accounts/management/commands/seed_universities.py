from django.core.management.base import BaseCommand

from accounts.models import University

# 医学部医学科を設置する日本の大学一覧（2026年時点、防衛医科大学校を除く）。
# 東京医科歯科大学は2024年10月の統合により東京科学大学に名称変更。
NATIONAL_UNIVERSITIES = [
    "北海道大学",
    "旭川医科大学",
    "弘前大学",
    "東北大学",
    "秋田大学",
    "山形大学",
    "筑波大学",
    "群馬大学",
    "千葉大学",
    "東京大学",
    "東京科学大学",
    "新潟大学",
    "富山大学",
    "金沢大学",
    "福井大学",
    "山梨大学",
    "信州大学",
    "岐阜大学",
    "浜松医科大学",
    "名古屋大学",
    "三重大学",
    "滋賀医科大学",
    "京都大学",
    "大阪大学",
    "神戸大学",
    "鳥取大学",
    "島根大学",
    "岡山大学",
    "広島大学",
    "山口大学",
    "徳島大学",
    "香川大学",
    "愛媛大学",
    "高知大学",
    "九州大学",
    "佐賀大学",
    "長崎大学",
    "熊本大学",
    "大分大学",
    "宮崎大学",
    "鹿児島大学",
    "琉球大学",
]

PUBLIC_UNIVERSITIES = [
    "札幌医科大学",
    "福島県立医科大学",
    "横浜市立大学",
    "名古屋市立大学",
    "京都府立医科大学",
    "大阪公立大学",
    "奈良県立医科大学",
    "和歌山県立医科大学",
]

PRIVATE_UNIVERSITIES = [
    "岩手医科大学",
    "自治医科大学",
    "獨協医科大学",
    "埼玉医科大学",
    "国際医療福祉大学",
    "杏林大学",
    "慶應義塾大学",
    "順天堂大学",
    "昭和大学",
    "帝京大学",
    "東京医科大学",
    "東京慈恵会医科大学",
    "東京女子医科大学",
    "東邦大学",
    "日本大学",
    "日本医科大学",
    "北里大学",
    "聖マリアンナ医科大学",
    "東海大学",
    "金沢医科大学",
    "愛知医科大学",
    "藤田医科大学",
    "大阪医科薬科大学",
    "関西医科大学",
    "近畿大学",
    "兵庫医科大学",
    "川崎医科大学",
    "久留米大学",
    "産業医科大学",
    "福岡大学",
    "東北医科薬科大学",
]

ALL_UNIVERSITIES = NATIONAL_UNIVERSITIES + PUBLIC_UNIVERSITIES + PRIVATE_UNIVERSITIES


class Command(BaseCommand):
    help = "Seed all Japanese universities with a medical school (医学部医学科) into University."

    def handle(self, *args, **options):
        created_count = 0
        for name in ALL_UNIVERSITIES:
            _, was_created = University.objects.get_or_create(name=name)
            created_count += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created_count} new universities "
                f"(国立{len(NATIONAL_UNIVERSITIES)}/公立{len(PUBLIC_UNIVERSITIES)}/私立{len(PRIVATE_UNIVERSITIES)}, "
                f"total in DB: {University.objects.count()})."
            )
        )
