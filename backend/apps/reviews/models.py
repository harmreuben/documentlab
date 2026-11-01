"""Review fields shared by every kind of analysis that can need a person's review.

A review records a person's decision about a result that needed review. It never changes the
technical result: an analysis that said "Needs review" keeps saying so, with the decision beside it.
"""
from django.conf import settings
from django.db import models


class ReviewState(models.TextChoices):
    NONE = "", "Not needed"
    PENDING = "PENDING", "Waiting for review"
    CONFIRMED = "CONFIRMED", "Confirmed"
    REJECTED = "REJECTED", "Rejected"
    EXPIRED = "EXPIRED", "Data deleted before review"


class ReviewMixin(models.Model):
    ruleset_version = models.CharField(max_length=20, blank=True,
                                       help_text="Validation rule set in force when this was analysed.")
    review_state = models.CharField(max_length=10, choices=ReviewState.choices, blank=True, default="", db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)

    class Meta:
        abstract = True
