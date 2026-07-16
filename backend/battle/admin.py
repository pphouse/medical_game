from django.contrib import admin

from .models import BattleAnswer, BattleParticipant, BattleRoom


@admin.register(BattleRoom)
class BattleRoomAdmin(admin.ModelAdmin):
    list_display = ("id", "room_code", "host", "status", "created_at")


@admin.register(BattleParticipant)
class BattleParticipantAdmin(admin.ModelAdmin):
    list_display = ("id", "room", "user", "score")


@admin.register(BattleAnswer)
class BattleAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "room", "user", "question", "is_correct", "answered_at")
