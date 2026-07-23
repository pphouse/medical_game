from django.contrib import admin

from .models import BattleBuzz, BattleParticipant, BattleRoom, BattleRound


@admin.register(BattleRoom)
class BattleRoomAdmin(admin.ModelAdmin):
    list_display = ("id", "room_code", "host", "status", "question_count", "created_at")
    list_filter = ("status",)


@admin.register(BattleParticipant)
class BattleParticipantAdmin(admin.ModelAdmin):
    list_display = ("id", "room", "user", "score", "last_seen_at")


@admin.register(BattleRound)
class BattleRoundAdmin(admin.ModelAdmin):
    list_display = ("id", "room", "round_number", "question", "revealed_at", "closed_at")


@admin.register(BattleBuzz)
class BattleBuzzAdmin(admin.ModelAdmin):
    list_display = ("id", "round", "profile", "rank", "buzzed_at", "selected_choice_key", "is_correct")
