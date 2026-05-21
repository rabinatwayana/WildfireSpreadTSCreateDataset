import datetime
import json
import os

import ee
import imageio
from google.cloud import storage

from .satellites.FirePred import FirePred


class DatasetPrepareService:
    STATIC_BANDS = FirePred.STATIC_BANDS
    DYNAMIC_BANDS = FirePred.DYNAMIC_BANDS
    
    def __init__(self, location, config, logger=None):
        """_summary_ Class that handles downloading data associated with the given location and time period from Google Earth Engine.

        Args:
            location (_type_): _description_ Location for which to download data. Must be a key in the config file.
            config (_type_): _description_. Config file containing the location and time period for which to download data, 
            as well as the size of the rectangular area to extract.
        """
        self.config = config
        self.location = location
        self.logger = logger
        # self.rectangular_size = self.config.get('rectangular_size')
        self.degree_bbox_size = self.config.get(location).get('degree_bbox_size')
        print(self.degree_bbox_size, "degree_bbox_size")
        if self.degree_bbox_size is None:
            self.degree_bbox_size = self.config.get('global_degree_bbox_size')

        self.latitude = self.config.get(self.location).get('latitude')
        self.longitude = self.config.get(self.location).get('longitude')
        self.start_time = self.config.get(location).get('start')
        self.end_time = self.config.get(location).get('end')
        self.pre_buffer_days = self.config.get('pre_buffer_days')
        self.post_buffer_days = self.config.get('post_buffer_days')
        self.export_crs = self.config.get('export_crs')
        self.x = self.config.get(self.location).get('x')
        self.y = self.config.get(self.location).get('y')
        self.patch_pixels_x = self.config.get(self.location).get('patch_pixels_x')
        self.patch_pixels_y = self.config.get(self.location).get('patch_pixels_y')
        self.export_resolution = self.config.get('export_resolution')

        # Set the area to extract as an image
        # self.rectangular_size = self.config.get('rectangular_size')

        self.geometry = ee.Geometry.Rectangle(
            [self.longitude - self.degree_bbox_size/2, self.latitude - self.degree_bbox_size/2,
                self.longitude + self.degree_bbox_size/2, self.latitude + self.degree_bbox_size/2])
        
        # TO get the specified output
        # Get VIIRS grid origin in EPSG:3070
        viirs_sample = ee.ImageCollection('NOAA/VIIRS/001/VNP09GA') \
            .filterBounds(self.geometry) \
            .first() \
            .select('I1') \
            .reproject(crs=self.export_crs, scale=self.export_resolution)
        proj_info = viirs_sample.projection().getInfo()
        # print("proj_info:", proj_info)
        transform = proj_info['transform']
        origin_x = float(transform[2])
        origin_y = float(transform[5])
        
        # transform = viirs_sample.projection().transform().getInfo()
        # origin_x, origin_y = float(transform[2]), float(transform[5])
        res = self.export_resolution

        # Step 1: snap center to VIIRS grid
        x_snapped = round((self.x - origin_x) / res) * res + origin_x
        y_snapped = round((self.y - origin_y) / res) * res + origin_y

        # Step 2: ensure even patch size (odd → subtract 1)
        patch_x = self.patch_pixels_x if self.patch_pixels_x % 2 == 0 else self.patch_pixels_x + 1
        patch_y = self.patch_pixels_y if self.patch_pixels_y % 2 == 0 else self.patch_pixels_y + 1

        if patch_x != self.patch_pixels_x or patch_y != self.patch_pixels_y:
            print(f"Warning: patch size adjusted to even: {patch_x} x {patch_y}")

        x_size = patch_x * res
        y_size = patch_y * res

        self.export_geometry = ee.Geometry.Rectangle(
            [
                x_snapped - x_size / 2,
                y_snapped - y_size / 2,
                x_snapped + x_size / 2,
                y_snapped + y_size / 2,
            ],
            proj=self.export_crs,
            geodesic=False
        )

        # x_size= self.patch_pixels_x * self.export_resolution
        # y_size= self.patch_pixels_y * self.export_resolution

        # self.export_geometry = ee.Geometry.Rectangle(
        #     [ self.x - (x_size/2),  self.y - (y_size/2),  self.x + (x_size/2),  self.y+(y_size/2)],
        #     proj=self.export_crs,
        #     geodesic=False
        # )

        # self.scale_dict = {"FirePred": 375}

    def _log(self, message: str):
        if self.logger is not None:
            self.logger.log(message)
        else:
            print(message)

    def cast_to_uint8(self, image):
        return image.multiply(512).uint8()
        
    def prepare_daily_image(self, event_start_date:str, date_of_interest:str, time_stamp_start:str="00:00", time_stamp_end:str="23:59"):
        """_summary_

        Args:
            date_of_interest (str): _description_ Date for which we want to download data.
            time_stamp_start (str, optional): _description_. String representation of start of day time. Defaults to "00:00".
            time_stamp_end (str, optional): _description_. String representation of end of day time. Defaults to "23:59".

        Returns:
            _type_: _description_ Extracted image collection.
        """        """"""
        # self._log(f"[{self.location}] Preparing daily image for event_start_date={event_start_date}, date={date_of_interest}")

        satellite_client = FirePred(logger=self.logger)
        img_collection = satellite_client.compute_daily_features(event_start_date, date_of_interest + 'T' + time_stamp_start,
                                                                 date_of_interest + 'T' + time_stamp_end,
                                                                 self.geometry)        
        return img_collection

    def _event_gcs_prefix(self):
        return "WildfireSpreadTS/" + str(self.config["year"]) + '/' + self.location
        # return "nan_viirs" + str(self.config["year"]) + '/' + self.location


    def _event_local_dir(self):
        return os.path.join("data", str(self.config["year"]), self.location)

    def _write_metadata(self):
        metadata = {
            "event_id": self.location,
            "year": self.config.get("year"),
            "start": str(self.start_time),
            "end": str(self.end_time),
            "pre_buffer_days": self.pre_buffer_days,
            "post_buffer_days": self.post_buffer_days,
            "export_crs": self.export_crs,
            "export_resolution": self.export_resolution,
            "patch_pixels_x": self.patch_pixels_x,
            "patch_pixels_y": self.patch_pixels_y,
            "static_bands": self.STATIC_BANDS,
            "dynamic_bands": self.DYNAMIC_BANDS,
        }
        metadata_json = json.dumps(metadata, indent=2)
        bucket = storage.Client().bucket(self.config.get('output_bucket'))
        meta_blob = bucket.blob(self._event_gcs_prefix() + "/meta.json")
        meta_blob.upload_from_string(metadata_json, content_type="application/json")
        self._log(f"[{self.location}] Uploaded metadata to gs://{self.config.get('output_bucket')}/{self._event_gcs_prefix()}/meta.json")

    def export_image_to_gcloud(self, image, file_name_prefix: str, description: str):
        """Export the given image to Google Cloud Storage."""

        image_task = ee.batch.Export.image.toCloudStorage(
            image=image.toFloat(),
            description=description,
            fileNamePrefix=file_name_prefix,
            bucket=self.config.get('output_bucket'),
            scale=self.export_resolution,
            crs=self.export_crs,
            maxPixels=1e13,
            region=self.export_geometry
        )
        self._log(f"Started export task: {description}")

        image_task.start()

    def download_static_to_gcloud(self, image_collection):
        """Export the static features once per fire event."""
        static_image = image_collection.max().select(self.STATIC_BANDS)
        self.export_image_to_gcloud(
            static_image,
            self._event_gcs_prefix() + "/static/static",
            f"{self.location}_static"
        )

    def download_dynamic_to_gcloud(self, image_collection, index: str):
        """Export the dynamic features for a given date to Google Cloud Storage.

        Args:
            image_collection (_type_): _description_
            index (str): _description_
        """
        dynamic_image = image_collection.max().select(self.DYNAMIC_BANDS)
        self.export_image_to_gcloud(
            dynamic_image,
            self._event_gcs_prefix() + "/dynamic/" + index,
            f"{self.location}_dynamic_{index}"
        )
        
    # def extract_dataset_from_gee_to_gcloud(self, utm_zone:str, n_buffer_days:int=0):
    def extract_dataset_from_gee_to_gcloud(self):
        # print("Using utm_zone", utm_zone)
        """_summary_ Iterate over the time period specified in the config file, 
        and download the data for each day to Google Cloud.

        Args:
            utm_zone (str): _description_
            n_buffer_days (int, optional): _description_. Number of days before and 
            after the fire dates for which we also want to collect data. Defaults to 0.

        Raises:
            RuntimeError: _description_
        """
        # self._log(f"[{self.location}] pre_buffer_days={self.pre_buffer_days}, post_buffer_days={self.post_buffer_days}")
        # self._write_metadata()
        # buffer_days = datetime.timedelta(days=n_buffer_days)
        n_pre_buffer_days = datetime.timedelta(days=self.pre_buffer_days)
        n_post_buffer_days = datetime.timedelta(days=self.post_buffer_days)
        

        # time_dif = self.end_time - self.start_time + 2 * buffer_days + datetime.timedelta(days=1)
        time_dif = (self.end_time - self.start_time) + n_pre_buffer_days + n_post_buffer_days + datetime.timedelta(days=1)
        # self._log(f"[{self.location}] total extraction window={time_dif}")

        static_exported = False
        for i in range(time_dif.days):

            date_of_interest = str(self.start_time - n_pre_buffer_days + datetime.timedelta(days=i))
            self._log(f"------ Processing date={date_of_interest} ------")

            img_collection = self.prepare_daily_image(event_start_date=str(self.start_time), date_of_interest=date_of_interest)

            n_images = len(img_collection.getInfo().get("features"))
            if n_images > 1:
                raise RuntimeError(f"Found {n_images} features in img_collection returned by prepare_daily_image. "
                                    f"Should have been exactly 1.")
            max_img = img_collection.max()
            if len(max_img.getInfo().get('bands')) != 0:
                if not static_exported:
                    self.download_static_to_gcloud(img_collection)
                    static_exported = True
                    # self._log("Exporting static data ....")
                self.download_dynamic_to_gcloud(img_collection, date_of_interest)
                # self._log("Exporting dynamic data ....")
            else:
                self._log(f"*** ERROR FLAG *** Skipping {date_of_interest}: no bands found in daily image")

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
            if blob.name.endswith('/'):
                continue
            blob.download_to_filename(destination_file_name)
            self._log("Blob {} downloaded to {}.".format(blob.name, destination_file_name))

    def download_data_from_gcloud_to_local(self):
        """_summary_ Download the data from Google Cloud to the local machine. 
        The data must have been exported from GEE to GCloud first.
        """
        event_dir = self._event_local_dir()
        static_dir = os.path.join(event_dir, "static")
        dynamic_dir = os.path.join(event_dir, "dynamic")
        os.makedirs(static_dir, exist_ok=True)
        os.makedirs(dynamic_dir, exist_ok=True)
        # self._write_metadata()

        bucket = storage.Client().bucket(self.config.get('output_bucket'))
        prefix = self._event_gcs_prefix() + '/'
        for blob in bucket.list_blobs(prefix=prefix):
            if not (blob.name.endswith('.tif') or blob.name.endswith('meta.json')):
                continue
            relative_path = blob.name[len(prefix):]
            destination_file_name = os.path.join(event_dir, relative_path)
            os.makedirs(os.path.dirname(destination_file_name), exist_ok=True)
            blob.download_to_filename(destination_file_name)
            print("Blob {} downloaded to {}.".format(blob.name, destination_file_name))
