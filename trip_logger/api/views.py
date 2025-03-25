from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Trip, LogEntry
from .serializers import TripSerializer
import requests
from datetime import datetime, timedelta
import math

class TripPlannerView(APIView):
    def post(self, request):
        # Extract inputs
        data = request.data
        current_location = data['current_location']
        pickup_location = data['pickup_location']
        dropoff_location = data['dropoff_location']
        current_cycle_used = float(data['current_cycle_used'])

        # Step 1: Calculate route (using OpenRouteService as an example)
        # Note: You'll need an API key for OpenRouteService
        api_key = "your_openrouteservice_api_key"
        url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
        headers = {"Authorization": api_key}
        coords = [
            self.geocode(current_location),  # [lon, lat]
            self.geocode(pickup_location),
            self.geocode(dropoff_location)
        ]
        body = {
            "coordinates": coords,
            "instructions": True
        }
        response = requests.post(url, json=body, headers=headers)
        route_data = response.json()

        # Extract distance (in meters) and convert to miles
        distance_meters = route_data['features'][0]['properties']['summary']['distance']
        distance_miles = distance_meters / 1609.34  # Convert to miles

        # Step 2: Calculate driving time (assume 55 mph)
        driving_hours = distance_miles / 55

        # Step 3: Plan stops and HOS compliance
        logs = self.plan_trip(
            current_location, pickup_location, dropoff_location,
            distance_miles, driving_hours, current_cycle_used
        )

        # Step 4: Save trip and logs
        trip = Trip.objects.create(
            current_location=current_location,
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            current_cycle_used=current_cycle_used
        )
        for log in logs:
            LogEntry.objects.create(trip=trip, **log)

        # Serialize and return response
        serializer = TripSerializer(trip)
        return Response({
            "trip": serializer.data,
            "route": route_data,
            "distance_miles": distance_miles,
            "driving_hours": driving_hours
        })

    def geocode(self, location):
        # Placeholder for geocoding (convert location to coordinates)
        # In a real app, use a geocoding API like OpenRouteService or Google Maps
        # For now, return dummy coordinates
        return [-122.4194, 37.7749]  # Example: San Francisco

    def plan_trip(self, current_location, pickup_location, dropoff_location, distance_miles, driving_hours, current_cycle_used):
        logs = []
        current_time = datetime.now()
        total_cycle_hours = current_cycle_used
        remaining_distance = distance_miles
        remaining_hours = driving_hours
        current_location_marker = current_location

        # Add pickup and dropoff time (1 hour each)
        pickup_time = 1  # 1 hour for pickup
        dropoff_time = 1  # 1 hour for dropoff
        total_hours = driving_hours + pickup_time + dropoff_time

        # Plan fueling stops (every 1,000 miles)
        fueling_stops = math.floor(distance_miles / 1000)
        fueling_time = 0.5  # 30 minutes per fueling stop

        # Start log: On Duty (Not Driving) for pickup
        logs.append({
            "date": current_time.date(),
            "duty_status": "On Duty (Not Driving)",
            "start_time": current_time.time(),
            "end_time": (current_time + timedelta(hours=1)).time(),
            "location": pickup_location,
            "remarks": f"Pickup at {pickup_location}"
        })
        current_time += timedelta(hours=1)

        # Driving loop with HOS compliance
        hours_driven_in_window = 0
        total_driving_hours = 0
        while remaining_hours > 0:
            # Check 14-hour window
            if hours_driven_in_window >= 14:
                # Insert 10-hour off-duty period
                logs.append({
                    "date": current_time.date(),
                    "duty_status": "Off Duty",
                    "start_time": current_time.time(),
                    "end_time": (current_time + timedelta(hours=10)).time(),
                    "location": current_location_marker,
                    "remarks": f"Required 10-hour rest at {current_location_marker}"
                })
                current_time += timedelta(hours=10)
                hours_driven_in_window = 0
                continue

            # Check 8-hour driving limit for 30-minute break
            if total_driving_hours >= 8:
                logs.append({
                    "date": current_time.date(),
                    "duty_status": "Off Duty",
                    "start_time": current_time.time(),
                    "end_time": (current_time + timedelta(minutes=30)).time(),
                    "location": current_location_marker,
                    "remarks": f"30-minute rest break at {current_location_marker}"
                })
                current_time += timedelta(minutes=30)
                total_driving_hours = 0
                hours_driven_in_window += 0.5
                continue

            # Check 70-hour limit
            if total_cycle_hours >= 70:
                # Need a 34-hour restart
                logs.append({
                    "date": current_time.date(),
                    "duty_status": "Off Duty",
                    "start_time": current_time.time(),
                    "end_time": (current_time + timedelta(hours=34)).time(),
                    "location": current_location_marker,
                    "remarks": f"34-hour restart at {current_location_marker}"
                })
                current_time += timedelta(hours=34)
                total_cycle_hours = 0
                hours_driven_in_window = 0
                continue

            # Check for fueling stop
            if distance_miles - remaining_distance >= 1000:
                logs.append({
                    "date": current_time.date(),
                    "duty_status": "On Duty (Not Driving)",
                    "start_time": current_time.time(),
                    "end_time": (current_time + timedelta(minutes=30)).time(),
                    "location": current_location_marker,
                    "remarks": f"Fueling at {current_location_marker}"
                })
                current_time += timedelta(minutes=30)
                hours_driven_in_window += 0.5
                distance_miles -= 1000
                continue

            # Drive for up to 1 hour at a time (for simplicity in logging)
            drive_hours = min(1, remaining_hours)
            logs.append({
                "date": current_time.date(),
                "duty_status": "Driving",
                "start_time": current_time.time(),
                "end_time": (current_time + timedelta(hours=drive_hours)).time(),
                "location": current_location_marker,
                "remarks": f"Driving from {current_location_marker}"
            })
            current_time += timedelta(hours=drive_hours)
            remaining_hours -= drive_hours
            hours_driven_in_window += drive_hours
            total_driving_hours += drive_hours
            total_cycle_hours += drive_hours
            current_location_marker = dropoff_location if remaining_hours <= 0 else current_location_marker

        # End log: On Duty (Not Driving) for dropoff
        logs.append({
            "date": current_time.date(),
            "duty_status": "On Duty (Not Driving)",
            "start_time": current_time.time(),
            "end_time": (current_time + timedelta(hours=1)).time(),
            "location": dropoff_location,
            "remarks": f"Dropoff at {dropoff_location}"
        })

        return logs