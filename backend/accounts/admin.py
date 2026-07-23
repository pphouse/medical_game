from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Profile, University, User


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "university", "grade", "student_verified", "role")
    list_filter = ("university", "student_verified", "role")
    search_fields = ("display_name", "id")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("大学連携", {"fields": ("university", "student_verified")}),
    )
    list_display = ("username", "email", "university", "student_verified", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("university", "student_verified")
