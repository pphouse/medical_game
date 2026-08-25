from django.urls import path

from .views import (
    AnswerView,
    QuickMatchCreateView,
    QuickMatchPollView,
    RoomCreateView,
    RoomJoinView,
    RoomLeaveView,
    RoomResultView,
    RoomStartView,
    RoomStateView,
)

urlpatterns = [
    path("rooms/", RoomCreateView.as_view(), name="battle-room-create"),
    path("rooms/<str:code>/join/", RoomJoinView.as_view(), name="battle-room-join"),
    path("rooms/<str:code>/leave/", RoomLeaveView.as_view(), name="battle-room-leave"),
    path("rooms/<str:code>/start/", RoomStartView.as_view(), name="battle-room-start"),
    path("rooms/<str:code>/state/", RoomStateView.as_view(), name="battle-room-state"),
    path("rooms/<str:code>/result/", RoomResultView.as_view(), name="battle-room-result"),
    path("rounds/<int:round_id>/answer/", AnswerView.as_view(), name="battle-answer"),
    path("quickmatch/", QuickMatchCreateView.as_view(), name="battle-quickmatch-create"),
    path("quickmatch/<int:ticket_id>/", QuickMatchPollView.as_view(), name="battle-quickmatch-poll"),
]
