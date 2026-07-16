from django.contrib.auth.models import AbstractUser
from django.db import models


class University(models.Model):
    name = models.CharField(max_length=255, unique=True)

    class Meta:
        verbose_name = "大学"
        verbose_name_plural = "大学"

    def __str__(self):
        return self.name


class User(AbstractUser):
    """spec: User: id, university_id (FK), student_verified (bool), email"""

    university = models.ForeignKey(
        University,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    student_verified = models.BooleanField(default=False)
    email = models.EmailField(unique=True)
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="学年（医学部は1〜6年）"
    )

    def __str__(self):
        return self.username
