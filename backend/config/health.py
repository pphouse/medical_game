"""デプロイの疎通確認用エンドポイント。

フロントから「APIエラー」としか見えないとき、原因がバックエンドまで届いて
いないのか（DNS・ルーティング・VITE_API_BASE_URL の誤り）、届いた上で
Django が弾いているのか（DJANGO_ALLOWED_HOSTS・DJANGO_SECRET_KEY 未設定）
を切り分けられない。ブラウザで直接開ける認証不要の口をひとつ用意しておく。

    GET /api/health/  ->  200 {"status": "ok"}

設定値は返さない。ここで返してよいのは「Django が起動して応答できている」
という事実だけで、それ以外は本番環境の構成を晒すことになる。

読み取れること:
- 200 が返る               … バックエンドは正常。原因はフロント側の設定
                              （VITE_API_BASE_URL）か CORS
- 400 DisallowedHost       … DJANGO_ALLOWED_HOSTS に本番ホストが無い
- 500 / 関数起動失敗       … DJANGO_SECRET_KEY 未設定など、起動時の失敗
- そもそも届かない         … URL が違う
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """認証不要。Django が応答できることだけを返す。"""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})
