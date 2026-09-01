"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from accounts.views import InternalAdvanceGradesView
from config.health import HealthView
from exams.views import InternalAggregateView, InternalCreateExamsView

urlpatterns = [
    path('admin/', admin.site.urls),
    # 疎通確認（認証不要・設定値は返さない）。config/health.py を参照。
    path('api/health/', HealthView.as_view(), name='health'),
    path('api/auth/', include('accounts.urls')),
    path('api/quiz/', include('quiz.urls')),
    # 管理画面 (moderator/admin)。学習者向けAPIとは公開ゲートの前提が違うので分ける。
    path('api/admin/', include('quiz.admin_urls')),
    path('api/battle/', include('battle.urls')),
    path('api/exams/', include('exams.urls')),
    path('api/ranking/', include('exams.urls_ranking')),
    path('api/internal/aggregate/', InternalAggregateView.as_view(), name='internal-aggregate'),
    path('api/internal/create-exams/', InternalCreateExamsView.as_view(), name='internal-create-exams'),
    path('api/internal/advance-grades/', InternalAdvanceGradesView.as_view(), name='internal-advance-grades'),
]
