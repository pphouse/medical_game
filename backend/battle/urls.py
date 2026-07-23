from django.urls import path

from .views import (
    AnswerView,
    BuzzView,
    RoomCreateView,
    RoomJoinView,
    RoomResultView,
    RoomStartView,
    RoomStateView,
)

urlpatterns = [
    path("rooms/", RoomCreateView.as_view(), name="battle-room-create"),
    path("rooms/<str:code>/join/", RoomJoinView.as_view(), name="battle-room-join"),
    path("rooms/<str:code>/start/", RoomStartView.as_view(), name="battle-room-start"),
    path("rooms/<str:code>/state/", RoomStateView.as_view(), name="battle-room-state"),
    path("rooms/<str:code>/result/", RoomResultView.as_view(), name="battle-room-result"),
    path("rounds/<int:round_id>/buzz/", BuzzView.as_view(), name="battle-buzz"),
    path("rounds/<int:round_id>/answer/", AnswerView.as_view(), name="battle-answer"),
]
