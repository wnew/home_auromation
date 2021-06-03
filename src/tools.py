import datetime
import pytz
from astral import LocationInfo
from astral.sun import sun


def is_it_dark_in_cape_town():
    """
    looks up the sunrise and sunset times for the current date and compares
    them to the current time

    returns:
    boolean: True = Dark, False = Light
    """
    # create a location with latitude and longitude co-ordinates
	location = LocationInfo("Cape Town", "South Africa", "Africa/Johannesburg", -33.92, 18.42)
	
	#print((
	#    f"Information for {location.name}/{city.region}\n"
	#    f"Timezone: {location.timezone}\n"
	#    f"Latitude: {location.latitude:.02f}; Longitude: {city.longitude:.02f}\n"
	#))
	
    # create a sun object with the current date and our location
	s = sun(city.observer, date=datetime.date.today(), tzinfo=location.timezone)
	
    # get the current datetime as a timezone aware timedate object
	time_now = datetime.datetime.now(pytz.UTC)

	#print(time_now)
	#print(s["sunrise"])
	#print(s["dusk"])

	#print((
	#     f'Dawn:    {s["dawn"]}\n'
	#     f'Sunrise: {s["sunrise"]}\n'
	#     f'Noon:    {s["noon"]}\n'
	#     f'Sunset:  {s["sunset"]}\n'
	#     f'Dusk:    {s["dusk"]}\n'))

    # return false if the current time falls between sunrise and sunset
    # otherwise return true
	return(time_now < s["sunrise"] or time_now > s["dusk"])