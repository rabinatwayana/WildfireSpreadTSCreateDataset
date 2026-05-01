import datetime
import os

import ee
import imageio
from google.cloud import storage

from .satellites.FirePred import FirePred


class DatasetPrepareService:
    
    def __init__(self, location, config):
        """_summary_ Class that handles downloading data associated with the given location and time period from Google Earth Engine.

        Args:
            location (_type_): _description_ Location for which to download data. Must be a key in the config file.
            config (_type_): _description_. Config file containing the location and time period for which to download data, 
            as well as the size of the rectangular area to extract.
        """
        self.config = config
        self.location = location
        self.rectangular_size = self.config.get('rectangular_size')
        self.latitude = self.config.get(self.location).get('latitude')
        self.longitude = self.config.get(self.location).get('longitude')
        self.start_time = self.config.get(location).get('start')
        self.end_time = self.config.get(location).get('end')

        # Set the area to extract as an image
        self.rectangular_size = self.config.get('rectangular_size')
        self.geometry = ee.Geometry.Rectangle(
            [self.longitude - self.rectangular_size, self.latitude - self.rectangular_size,
                self.longitude + self.rectangular_size, self.latitude + self.rectangular_size])

        self.scale_dict = {"FirePred": 375}

    def cast_to_uint8(self, image):
        return image.multiply(512).uint8()
        
    def prepare_daily_image(self, date_of_interest:str, time_stamp_start:str="00:00", time_stamp_end:str="23:59"):
        """_summary_

        Args:
            date_of_interest (str): _description_ Date for which we want to download data.
            time_stamp_start (str, optional): _description_. String representation of start of day time. Defaults to "00:00".
            time_stamp_end (str, optional): _description_. String representation of end of day time. Defaults to "23:59".

        Returns:
            _type_: _description_ Extracted image collection.
        """        """"""
        

        satellite_client = FirePred()
        img_collection = satellite_client.compute_daily_features(date_of_interest + 'T' + time_stamp_start,
                                                                 date_of_interest + 'T' + time_stamp_end,
                                                                 self.geometry)        
        return img_collection

    def download_image_to_gcloud(self, image_collection, index:str, utm_zone:str):
        """_summary_ Export the given images to google cloud. The output image is a rectangular image, 
        with the center at the given latitude and longitude.

        Args:
            image_collection (_type_): _description_
            index (str): _description_
            utm_zone (str): _description_
        """

        if "year" in self.config:
            filename = "WildfireSpreadTS/" + str(self.config["year"]) + '/' + self.location + '/' + index

        img = image_collection.max().toFloat()
        image_task = ee.batch.Export.image.toCloudStorage(
            image=img,
            description='Image Export',
            fileNamePrefix=filename,
            bucket=self.config.get('output_bucket'),
            scale=self.scale_dict.get("FirePred"),
            crs='EPSG:' + utm_zone,
            maxPixels=1e13,
            region=self.geometry.toGeoJSON()['coordinates'],
        )
        print('Start with image task (id: {}).'.format(image_task.id))
        image_task.start()
        
    def extract_dataset_from_gee_to_gcloud(self, utm_zone:str, n_buffer_days:int=0):
        print("Using utm_zone", utm_zone)
        """_summary_ Iterate over the time period specified in the config file, 
        and download the data for each day to Google Cloud.

        Args:
            utm_zone (str): _description_
            n_buffer_days (int, optional): _description_. Number of days before and 
            after the fire dates for which we also want to collect data. Defaults to 0.

        Raises:
            RuntimeError: _description_
        """

        buffer_days = datetime.timedelta(days=n_buffer_days)
        time_dif = self.end_time - self.start_time + 2 * buffer_days + datetime.timedelta(days=1)

        for i in range(time_dif.days):
            date_of_interest = str(self.start_time - buffer_days + datetime.timedelta(days=i))

            img_collection = self.prepare_daily_image(date_of_interest=date_of_interest)

            n_images = len(img_collection.getInfo().get("features"))
            if n_images > 1:
                raise RuntimeError(f"Found {n_images} features in img_collection returned by prepare_daily_image. "
                                    f"Should have been exactly 1.")
            max_img = img_collection.max()
            if len(max_img.getInfo().get('bands')) != 0:
                self.download_image_to_gcloud(img_collection, date_of_interest, utm_zone)

    def download_blob(self, bucket_name:str, blob_name:str, destination_file_name:str):
        """_summary_

        Args:
            bucket_name (str): _description_ GCloud bucket name, as given in config.
            blob_name (str): _description_ Name of blob inside the GCloud bucket
            destination_file_name (str): _description_ Local name for the file to be downloaded.
        """

        storage_client = storage.Client()

        bucket = storage_client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=blob_name)
        for blob in blobs:
            filename = blob.name.split('/')[2].replace('.tif', '') + '_' + blob.name.split('/')[1] + '.tif'
            blob.download_to_filename(destination_file_name + filename)
            print(
                "Blob {} downloaded to {}.".format(
                    filename, destination_file_name
                )
            )

    def download_data_from_gcloud_to_local(self):
        """_summary_ Download the data from Google Cloud to the local machine. 
        The data must have been exported from GEE to GCloud first.
        """
        if "year" in self.config:
            blob_name = str(self.config["year"]) + '/' + self.location + '/'
            destination_name = 'data/' + str(self.config["year"]) + '/' + self.location + '/'
        dir_name = os.path.dirname(destination_name)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        self.download_blob(self.config.get('output_bucket'), blob_name, destination_name)
