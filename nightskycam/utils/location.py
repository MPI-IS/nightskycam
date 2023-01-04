"""
Methods for getting information (e.g. current time, altitude of the sun) related to the location
of the device, as configured in the global configuration.
"""

import astropy
import geopy

_geolocator: typing.Optional[geopy.geocoders.Nominatim] = None
_locations: typing.Dict[str,geopy.location.Location] = {}


def get_location(location: str)->geopy.location.Location:
    """
    Returns the geopy.location.Location object related to the 
    string passed as argument. Raises a ValueError if the location
    is unknown. Raises a RuntimeError if geopy fails to retrieve the 
    information.
    """
    global _geolocator
    global _locations
    if _geolocator is None:
        try:
            _geolocator = geopy.geocoders.Nominatim(user_agent="nightskycam")
        except geopy.exc.GeopyError as e:
            raise RuntimeError(
                "failed to activate geopy/nominatim to retrieve information regarding "
                f"{location}: {e}"
            )
    try:
        return _locations[location]
    except KeyError:
        try:
            location_ = _geolocator.geocode(location)
        except geopy.exc.GeopyError as e:
            raise RuntimeError(
                "failed to use geopy to retrieve information regarding "
                f"{location}: {e}"
            )
        if location_ is None:
            raise ValueError(f"unknown location: {location}")
        _locations[location]=location_
        return location_

def get_coord(location: geopy.location.Location)->typing.Tuple[float,float]:
    """
    Returns the latitude and longitude of the location.
    """ 
    return (location.latitude, location.longitude)

def details(location: geopy.location.Location)->str:
    """
    Returns an informative string about the location
    """
    return location.raw["display_name"]

def get_current_time(location: geopy.location.Location)->datetime.datetime:
    """
    Returns the current time at the location
    """
    raise NotImplementedError()

def get_timezone(location: geopy.location.Location)->str:
    """
    Returns the time zone of the location. 
    """
    tzf = TimezoneFinder()
    return tzf.timezone_at(lng=location.longitude, lat=location.latitude)
    
def get_sun_altitude(location: geopy.location.Location)->float:
    """
    Returns the current altitude of the sun at the given location, 
    or raises an exception if such location is unknown.
    """
    astroloc = astropy.coordinates.coord.EarthLocation(
        location.latitude * astropy.units.deg,
        location.longitude * astropy.units.deg
    )
    now = get_current_time(location)
    altaz = coord.AltAz(location=astroloc, obstime=now)
    sun = coord.get_sun(now)
    return sun.transform_to(altaz).alt



class Location:

    def __init__(self, location: geopy.location.Location)->None:
        location_ = get_location(location)
        self.description = details(location_)
        self.current_time = get_current_time(location_)
        self.sun_altitude = get_sun_altitude(location_)
        self.timezone = get_timezone(location_)
        

    
