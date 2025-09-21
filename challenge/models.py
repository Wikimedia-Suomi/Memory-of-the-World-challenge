from django.db import models

class Participant(models.Model):
    username = models.CharField(max_length=255, unique=True)

    def __str__(self) -> str:
        return self.username

class WikiActivity(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name="activities")
    wiki = models.CharField(max_length=50)
    editcount = models.IntegerField(default=0)
    active = models.BooleanField(default=False)
    rev_count = models.IntegerField(default=0)
    ar_count = models.IntegerField(default=0)

    class Meta:
        unique_together = ("participant", "wiki")

    def __str__(self) -> str:
        return f"{self.participant.username} on {self.wiki}"
