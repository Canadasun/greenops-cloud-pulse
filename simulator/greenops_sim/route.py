"""A route is a list of GPS waypoints; position_at() interpolates along it."""
import math
from dataclasses import dataclass


def _km(a, b):
    """Great-circle distance in km between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


@dataclass
class Route:
    route_id: str
    waypoints: list

    def __post_init__(self):
        self.legs = [_km(a, b) for a, b in zip(self.waypoints, self.waypoints[1:])]
        self.length_km = sum(self.legs)

    def position_at(self, progress: float):
        """Position after `progress` (0.0 = start, 1.0 = destination) of the route."""
        progress = min(max(progress, 0.0), 1.0)
        target = progress * self.length_km
        for (a, b), leg in zip(zip(self.waypoints, self.waypoints[1:]), self.legs):
            if target <= leg or leg == 0:
                f = target / leg if leg else 0
                return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
            target -= leg
        return tuple(self.waypoints[-1])
