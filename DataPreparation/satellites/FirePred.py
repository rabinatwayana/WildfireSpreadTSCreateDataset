"""
## RABINA: ERROR: 00F01 and 00F24, reperesents F10 to F240
"""

import datetime
import ee
import math
import os
from dotenv import load_dotenv
load_dotenv()
import calendar

class FirePred:
    STATIC_BANDS = ["elevation", "slope", "aspect", "NDVI", "EVI2", "LC_Type1", "water mask"]
    DYNAMIC_BANDS = [
        "I1", "I2", "I3", "M11",
        "total precipitation", "wind direction", "minimum temperature",
        "maximum temperature", "energy release component", "specific humidity",
        "wind speed", "pdsi", "forecast total precipitation", "forecast wind speed",
        "forecast wind direction", "forecast temperature",
        "forecast specific humidity", "active fire", "active fire confidence"
    ]

    def __init__(self, logger=None):
        # TODO: Update self.viirs_af feature collection
        """_summary_ This class describes which data to extract how from Google Earth Engine. 
        The init defines the different source data products to use. 
        """
        self.name = "FirePred"
        self.logger= logger
        # VIIRS surface reflectance
        self.viirs = ee.ImageCollection('NASA/VIIRS/002/VNP09GA') # 'NOAA/VIIRS/001/VNP09GA'  NASA/VIIRS/002/VNP09GA VNP09GA VIIRS Version 1 data product was decommissioned on April 8th, 2025

        # Static Features
        self.srtm = ee.Image("USGS/SRTMGL1_003")
        self.landcover = ee.ImageCollection("MODIS/061/MCD12Q1")
        self.viirs_veg_idx = ee.ImageCollection("NASA/VIIRS/002/VNP13A1") #NOAA/VIIRS/001/VNP13A1

        # Dynamic Features
        self.weather = ee.ImageCollection("IDAHO_EPSCOR/GRIDMET")
        self.weather_forecast = ee.ImageCollection('NOAA/GFS0P25')
        self.drought = ee.ImageCollection("GRIDMET/DROUGHT")
        
        # VIIRS active fire product
        # self.viirs_af = ee.FeatureCollection('projects/grand-drive-285514/assets/afall')
        viirs_af_path= os.getenv("VIIRS_AF_PATH")
        self.viirs_af = ee.FeatureCollection(viirs_af_path)

        # print("Checking VIIRS AF asset...")
        # try:
        #     # print(self.viirs_af.size().getInfo())
        #     print(self.viirs_af.first().getInfo()) # to check the properties name
        # except Exception as e:
        #     print("Error:", e)
        # print("no pass")

    def _log(self, msg):
        if self.logger is not None:
            self.logger.log(msg)
        else:
            print(msg)

    

    def compute_daily_features(self, event_start_date:str, start_time:str, end_time:str, geometry:ee.Geometry):
        """_summary_ Compute the daily features in Google Earth Engine.

        Args:
            start_time (str): _description_
            end_time (str): _description_
            geometry (ee.Geometry): _description_

        Returns:
            ee.ImageCollection: _description_ ImageCollection containing one image, 
            with all desired features for the given day, inside the given geometry.
        """
        # Time objects we need later. We add "000" to timestamps, because GEE has timestamps with miliseconds,
        # but datetime doesn't by default
        # today_string = start_time[:-6].replace("-", "")
        # today = datetime.datetime.strptime(start_time[:-6], '%Y-%m-%d')
        # today_timestamp = int(datetime.datetime.timestamp(today)) * 1000

        #==========================================================
        # VIIRS Spectral Data
        #==========================================================
        # VIIRS IMG and AF product
        # viirs_img = self.viirs.filterDate(start_time, end_time).filterBounds(geometry).select(
        #     ['M11', 'I2', 'I1']).median()

        viirs_img = self.viirs.filterDate(start_time, end_time).filterBounds(geometry).select(
            [ 'I1', 'I2', 'I3','M11']).median()

        #==========================================================
        # Dynamic Features
        #==========================================================
        #-----------------------
        # Current weather
        #-----------------------
        # Median is used to turn ee.ImageCollection into a single ee.Image.
        # Each ImageCollection should only contain a single image at this point.
        weather = self.weather.filterDate(start_time, end_time).filterBounds(geometry)
        weather_image_size = weather.size().getInfo()
        self._log(f"Weather image size: {weather_image_size}")
        if weather_image_size == 0:
            self._log("*** ERROR FLAG ***: weather_image_size is 0")

        precipitation = weather.select('pr').sum().rename("total precipitation")
        wind_direction = weather.select('th').mean().rename("wind direction")
        temperature_min = weather.select('tmmn').min().rename("minimum temperature")
        temperature_max = weather.select('tmmx').max().rename("maximum temperature")
        energy_release_component = weather.select('erc').max().rename("energy release component")
        specific_humidity = weather.select('sph').mean().rename("specific humidity")
        wind_velocity = weather.select('vs').max().rename("wind speed")

        #-----------------------
        # Forecast weather data
        #-----------------------
        # Take forecasts made at midnight (00), and that tell us something about the hours between 01 and 24.
        # Important: The forecasts at 00 contain six features instead of nine, like all others.

        ## RABINA: FRAGILE: 00F01 and 00F24, reperesents F10 to F240, this is fetching  today's full day range, not tomorrow
        # weather_forecast = self.weather_forecast.filter(
        #     ee.Filter.gte("system:index", today_string + "00F01")).filter(
        #     ee.Filter.lte("system:index", today_string + "00F24")
        # ).filterBounds(geometry)
        
        # corrected version based on forecast time
        today = datetime.datetime.strptime(start_time[:-6], '%Y-%m-%d')
        today_timestamp = calendar.timegm(today.timetuple()) * 1000
        tomorrow_start = today + datetime.timedelta(days=1)
        tomorrow_end = today + datetime.timedelta(days=2)
        tomorrow_start_ms = calendar.timegm(tomorrow_start.timetuple()) * 1000
        tomorrow_end_ms = calendar.timegm(tomorrow_end.timetuple()) * 1000
        self._log(f"Forecast duration: {tomorrow_start} to {tomorrow_end}")
        # print(tomorrow_end, "tomorrow_end")
        # print(tomorrow_start_ms, tomorrow_end_ms, "tomorrow start end ms")
        # print(today_timestamp, "today_timestamp ms")
        today_end_ms = calendar.timegm((today + datetime.timedelta(days=1)).timetuple()) * 1000
        weather_forecast = self.weather_forecast \
            .filter(ee.Filter.gte('creation_time', today_timestamp)) \
            .filter(ee.Filter.lt('creation_time',  today_end_ms)) \
            .filter(ee.Filter.gte("forecast_time", tomorrow_start_ms)) \
            .filter(ee.Filter.lt("forecast_time",  tomorrow_end_ms)) \
            .filterBounds(geometry)
        forecast_image_size= weather_forecast.size().getInfo()
        self._log(f"Number of forecast images: {forecast_image_size}")
        if forecast_image_size == 0:
            self._log(f"*** ERROR FLAG ***: forecast_image_size is 0")
        # forecast_times = weather_forecast.aggregate_array('forecast_time')
        # print(forecast_times.getInfo())

        #-------Forecast Temperature-------
        forecast_temperature = weather_forecast.select("temperature_2m_above_ground").mean().rename(
            "forecast temperature")
        
        #-------Forecast Humidity-------
        forecast_specific_humidity = weather_forecast.select("specific_humidity_2m_above_ground").mean().rename(
            "forecast specific humidity")
        
        #-------Forecast wind speed and direction-------
        forecast_u_wind = weather_forecast.select("u_component_of_wind_10m_above_ground").mean()
        forecast_v_wind = weather_forecast.select("v_component_of_wind_10m_above_ground").mean()
        # Transform from u/v to direction and speed, to align with GRIDMET and DEM data, $Speed = sqrt{u^2 + v^2}
        forecast_wind_speed = forecast_u_wind.multiply(forecast_u_wind).add(
            forecast_v_wind.multiply(forecast_v_wind)).sqrt().rename("forecast wind speed")
        # old
        # forecast_wind_direction = forecast_v_wind.atan2(forecast_u_wind)
        # forecast_wind_direction = forecast_wind_direction.divide(2 * math.pi).multiply(360).rename(
        #     "forecast wind direction")

        # Updated
        # http://www.weatherclasses.com/uploads/1/3/1/3/131359169/computing_wind_direction_and_speed_from_u_and_v.pdf
        # GEE follow spreadsheet, therefore using (v,u) and no mod(360) as we normalize using sin and cos in DeepLearning
        # Formula: mod(180 + atan2(v, u) * (180 / PI), 360)
        # atan2(v, u) * (180 / PI) => value range from -180 to 180
        # +180 => 0 to 360
        # additional: mod to brings the value into the proper 0–360 range
        forecast_wind_direction = forecast_v_wind.atan2(forecast_u_wind).multiply(180 / math.pi).add(180).mod(360).rename("forecast wind direction");

        #-------Forecast precipitation-------
        # Rain forecasts were changed: From rain within the one-hour interval to cumulative rain during the day so far
        # print(weather_forecast.first().bandNames().getInfo(), "weather forcast band names info")
        forecast_rain_change_date = datetime.datetime.strptime("2019-11-07T06:00:00", '%Y-%m-%dT%H:%M:%S')
        forecast_rain = weather_forecast.select("total_precipitation_surface")
        if today <= forecast_rain_change_date:
            forecast_rain = forecast_rain.reduce(ee.Reducer.sum())
        else:
            forecast_rain = forecast_rain.reduce(ee.Reducer.last())
        forecast_rain = forecast_rain.rename("forecast total precipitation")

        #---------------------
        # Drought
        #---------------------
        # Drought Data: old
        # Only available every fifth day, but we can find the valid entry via time_start and time_end
        # drought_index = self.drought \
        #     .filter(ee.Filter.lte("system:time_start", today_timestamp)) \
        #     .filter(ee.Filter.gte("system:time_end", today_timestamp)) \
        #     .select('pdsi').median()
        # Only available every fifth day, so finding date which doesnot include the doi, using what is avalible latest based on doi, also filterout forward window, using system:time_end
        # Avoids future data contamination
        drought_index = (
            self.drought
            .filter(ee.Filter.lt("system:time_end", today_timestamp))
            .select("pdsi")
            .sort("system:time_end", False)
            .first()
        )
        drought_exists = drought_index.bandNames().size().getInfo()
        if drought_exists == 0:
            self._log("*** ERROR FLAG ***: drought_index is empty")
        # date = drought_index.get("system:time_start").getInfo()
        # print(date,"drought date")

        #==========================================================
        # Static Features
        #==========================================================
        #---------------------
        # Elevation, slope and aspect
        #---------------------
        elevation = self.srtm.select('elevation')
        slope = ee.Terrain.slope(elevation)
        aspect = ee.Terrain.aspect(elevation)
        
        #---------------------
        # Land cover
        #---------------------
        # ERROR: Same year can not be used because land cover product may already include changes caused by fires occurring during that year itself.
        # igbp_land_cover = self.landcover.filterDate(start_time[:4] + '-01-01', start_time[:4] + '-12-31').filterBounds(
        #     geometry).select('LC_Type1').first() #.median()
        # lc_year = str(int(start_time[:4]) - 1)
        # igbp_land_cover = (
        #     self.landcover
        #     .filterDate(lc_year + '-01-01', lc_year + '-12-31')
        #     .filterBounds(geometry)
        #     .select('LC_Type1')
        #     .first()
        # )

        end_year = int(start_time[:4]) - 1
        start_year = end_year - 1   # 2-year window
        igbp_land_cover = (
            self.landcover
            .filterDate(f"{start_year}-01-01", f"{end_year}-12-31")
            .filterBounds(geometry)
            .select("LC_Type1")
            .sort("system:time_start", False)  # newest first
            .first()
        )
        date_info = ee.Date(igbp_land_cover.get("system:time_start")).format("YYYY").getInfo()
        self._log(f"Land cover year: {date_info}")

        #---------------------
        # Water mask
        #---------------------

        water_mask = igbp_land_cover.neq(17)  

        #---------------------
        # VIITS NDVI and EVI2
        #---------------------
        event_start= datetime.datetime.strptime(event_start_date, '%Y-%m-%d')
        event_start_timestamp = calendar.timegm(event_start.timetuple()) * 1000 

        viirs_veg_idc = (
            self.viirs_veg_idx
            .filter(ee.Filter.lt("system:time_end", event_start_timestamp))  # fully ended before event
            .select(["NDVI", "EVI2"])
            .sort("system:time_end", False)   # most recent first
            .first()                          # most recent fully-completed composite
        )
        veg_exists = viirs_veg_idc.bandNames().size().getInfo()
        if veg_exists == 0:
            self._log("*** ERROR FLAG ***: viirs_veg_idc is empty")

        # Print which composite is being used
        if veg_exists != 0:
            time_start = viirs_veg_idc.get("system:time_start").getInfo()
            time_end   = viirs_veg_idc.get("system:time_end").getInfo()
            composite_start = datetime.datetime.utcfromtimestamp(time_start / 1000).strftime('%Y-%m-%d')
            composite_end   = datetime.datetime.utcfromtimestamp(time_end   / 1000).strftime('%Y-%m-%d')
            self._log(f"VIIRS composite: {composite_start} → {composite_end}")

        # viirs_veg_idc = self.viirs_veg_idx.filterDate((
        #         datetime.datetime.strptime(end_time[:-6], '%Y-%m-%d') + datetime.timedelta(-15)).strftime(
        #     '%Y-%m-%d'), end_time).filterBounds(geometry).select(['NDVI', 'EVI2']).reduce(
        #     ee.Reducer.last())
        #--------------------------
        # just for checking which date is picked in old version
        # filtered = (self.viirs_veg_idx
        #     .filterDate(
        #         (datetime.datetime.strptime(end_time[:-6], '%Y-%m-%d') + datetime.timedelta(-15)).strftime('%Y-%m-%d'),
        #         end_time
        #     )
        #     .filterBounds(geometry)
        #     .select(['NDVI', 'EVI2']))

        # dates = filtered.aggregate_array('system:time_start').getInfo()
        # for d in dates:
        #     print(datetime.datetime.utcfromtimestamp(d/1000).strftime('%Y-%m-%d'))
        # print("Last picked:", datetime.datetime.utcfromtimestamp(dates[-1]/1000).strftime('%Y-%m-%d'))
        #--------------------------

        #--------------------------------------------------------
        # past 16 days data can not used, need to find before that, label is beginning of composite period, 
        # treating this as a static feature, pre-event veg status is used for entire duration

        #----------------Dynamic------------------------------
        """ 
        veg_search_end_time = (datetime.datetime.strptime(end_time[:-6], '%Y-%m-%d') + datetime.timedelta(days=-15))
        veg_search_start_time = (veg_search_end_time + datetime.timedelta(days=-15))
        viirs_veg_filtered = (self.viirs_veg_idx
            .filterDate(
                veg_search_start_time.strftime('%Y-%m-%d'),
                veg_search_end_time.strftime('%Y-%m-%d')
            )
            .filterBounds(geometry)
            .select(['NDVI', 'EVI2'])
        )
        dates = viirs_veg_filtered.aggregate_array('system:time_start').getInfo()
        for d in dates:
            print(datetime.datetime.utcfromtimestamp(d/1000).strftime('%Y-%m-%d'))
        print("Last picked:", datetime.datetime.utcfromtimestamp(dates[-1]/1000).strftime('%Y-%m-%d'))
        viirs_veg_idc=viirs_veg_filtered.reduce(ee.Reducer.last())
        # The last one is what .reduce(ee.Reducer.last()) picks
        print("Last picked:", datetime.datetime.utcfromtimestamp(dates[-1]/1000).strftime('%Y-%m-%d'))
        """
        #----------------Dynamic end------------------------------

        #=============================
        # VIIRS Active Fire
        #=============================
        #---------------------
        #Active Fire Detection time
        #---------------------
        def add_acq_hour(feature):
            # Turn acq_time (String) into acq_hour (int)
            acq_time_str = ee.String(feature.get("acq_time"))
            acq_time_int = ee.Number.parse(acq_time_str)
            return feature.set({"acq_hour": acq_time_int})

        def get_buffer(feature):
            return feature.buffer(375 / 2).bounds()
        
        # VIIRS AF consists only of points, so we need to turn them into a raster image.
        # We also filter out low confidence detections, since they are most likely false positives. 
        viirs_af_img = self.viirs_af.map(add_acq_hour).filterBounds(geometry) \
            .filter(ee.Filter.gte('acq_date', start_time[:-6])) \
            .filter(ee.Filter.lt('acq_date', (
                datetime.datetime.strptime(end_time[:-6], '%Y-%m-%d') + datetime.timedelta(1)).strftime(
            '%Y-%m-%d'))) \
            .map(get_buffer) \
            .reduceToImage(['acq_hour'], ee.Reducer.last()) \
            .unmask(0) \
            .rename(['active fire'])
        # af_feature_count = (
        #     self.viirs_af
        #     .filterBounds(geometry)
        #     .filter(ee.Filter.gte('acq_date', start_time[:-6]))
        #     .filter(ee.Filter.lt('acq_date', (
        #         datetime.datetime.strptime(end_time[:-6], '%Y-%m-%d') + datetime.timedelta(1)).strftime('%Y-%m-%d')))
        #     .size()
        #     .getInfo()
        # )
        # self._log(f"Active fire feature count: {af_feature_count}")
        # if af_feature_count == 0:
        #     self._log("*** ERROR FLAG ***: active fire feature count is 0")
        
            # .filter(ee.Filter.neq('confidence', 'l')) \
        def encode_confidence(feature):
            conf = ee.String(feature.get('confidence'))
            conf_num = ee.Algorithms.If(
                conf.equals('l'), 1,
                ee.Algorithms.If(
                    conf.equals('n'), 2,
                    ee.Algorithms.If(
                        conf.equals('h'), 3,
                        0  # fallback for unknown values
                    )
                )
            )

            return feature.set('confidence_num', conf_num)
        
        viirs_af_conf_img = (
            self.viirs_af
            .map(add_acq_hour)
            .filterBounds(geometry)
            .filter(ee.Filter.gte('acq_date', start_time[:-6]))
            .filter(
                ee.Filter.lt(
                    'acq_date',(datetime.datetime.strptime(end_time[:-6], '%Y-%m-%d')+ datetime.timedelta(1)).strftime('%Y-%m-%d')
                )
            )
            .map(encode_confidence)
            .map(get_buffer)
            .reduceToImage(['confidence_num'], ee.Reducer.last())
            .rename(['active fire confidence'])
        )

        
        # viirs_af_conf_img = self.viirs_af.map(add_acq_hour).filterBounds(geometry) \
        #     .filter(ee.Filter.gte('acq_date', start_time[:-6])) \
        #     .filter(ee.Filter.lt('acq_date', (
        #         datetime.datetime.strptime(end_time[:-6], '%Y-%m-%d') + datetime.timedelta(1)).strftime(
        #     '%Y-%m-%d'))) \
        #     .map(self.get_buffer) \
        #     .reduceToImage(['confidence'], ee.Reducer.last()) \
        #     .rename(['active fire confidence'])
        #-----------------------------
        # Active Fire Confidence level
        #-----------------------------
        # return ee.ImageCollection(ee.Image(
        #     [viirs_img, viirs_veg_idc, precipitation, wind_velocity, wind_direction, temperature_min, temperature_max,
        #      energy_release_component, specific_humidity, slope, aspect,
        #      elevation, drought_index, igbp_land_cover,
        #      forecast_rain, forecast_wind_speed, forecast_wind_direction, forecast_temperature,
        #      forecast_specific_humidity,
        #      viirs_af_img]))

        # reordering layers
        static_img = ee.Image([
            elevation.rename("elevation"),
            slope.rename("slope"),
            aspect.rename("aspect"),
            viirs_veg_idc.select("NDVI").rename("NDVI"),
            viirs_veg_idc.select("EVI2").rename("EVI2"),
            igbp_land_cover.rename("LC_Type1"),
            water_mask.rename("water mask")   # 1=land, 0=water
        ])

        dynamic_img = ee.Image([
            viirs_img.select("I1").rename("I1"),
            viirs_img.select("I2").rename("I2"),
            viirs_img.select("I3").rename("I3"),
            viirs_img.select("M11").rename("M11"),
            precipitation,
            wind_direction,
            temperature_min,
            temperature_max,
            energy_release_component,
            specific_humidity,
            wind_velocity,
            drought_index.rename("pdsi"),
            forecast_rain,
            forecast_wind_speed,
            forecast_wind_direction,
            forecast_temperature,
            forecast_specific_humidity,
            viirs_af_img,
            viirs_af_conf_img
        ])

        return ee.ImageCollection(ee.Image(static_img.addBands(dynamic_img)))

    

    
    
