from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import University, User


@admin.register(University)
class UniversityAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("大学連携", {"fields": ("university", "student_verified")}),
    )
    list_display = ("username", "email", "university", "student_verified", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("university", "student_verified")
