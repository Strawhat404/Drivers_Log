from django.db import models

class Trip(models.Model):
    current_location = models.CharField(max_length=255)
    pickup_location = models.CharField(max_length=255)
    dropoff_location = models.CharField(max_length=255)
    current_cycle_used = models.FloatField()  # Hours used in the 70-hour cycle
    created_at = models.DateTimeField(auto_now_add=True)

class LogEntry(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='logs')
    date = models.DateField()
    duty_status = models.CharField(max_length=50)  # e.g., "Driving", "Off Duty"
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=255)
    remarks = models.TextField()