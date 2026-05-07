import ee
import yaml
import tqdm
import os
from dotenv import load_dotenv
load_dotenv()

from logger import CustomLogger

""" 
VIIRS AF FeatureCollection Creation Process:

    - Download NASA FIRMS archive data for VIIRS_SNPP_SP
    - NASA DATA download request: https://firms.modaps.eosdis.nasa.gov/download/
    https://firms.modaps.eosdis.nasa.gov/download/list.php
    -  (.csv) format

    Then upload in GEE : https://code.earthengine.google.com/
    - go to assets, new, csv, give a name and add csv file
    - Go to task tab to see the progress
    - asset_name or path: projects/wsts-dataset-creation/assets/viirs_snpp_sp_af_2016_to_2023
    - then click the share and add your service account eg:"account@wsts-dataset-creation.iam.gserviceaccount.com"

    Then check the properties name (case sensitive), print(self.viirs_af.first().getInfo()),
    This repo used csv
    CSV: {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-146.16847192545256, 63.91886811399255]}, 'id': '00000000000000047b85', 'properties': {'acq_date': '2022-05-31', 'acq_time': '0002', 'bright_t31': 294.6099853515625, 'brightness': 367, 'confidence': 'h', 'daynight': 'D', 'frp': 22.59000015258789, 'instrument': 'VIIRS', 'satellite': 'N', 'scan': 0.7599999904632568, 'track': 0.7699999809265137, 'type': 0, 'version': 2}}
"""

"""
To download data from gcloud:
- Install google-cloud-sdk in host machine and login 
- Then run command: gcloud storage cp -r gs://<bucket_name> ./<target_folder>
        eg: gcloud storage cp -r gs://wsts_dataset ./data_del
"""

# TODO: Update  self.viirs_af in DataPreparation/satellites/FirePred.py

from DataPreparation.DatasetPrepareService import DatasetPrepareService

if __name__ == '__main__':
    custom_logger = CustomLogger()
    logger_output_path = "logs/us_fire_data_creation_2016.log"
    config_path = "config/us_fire_2016_test.yml"
    failed_locations = []
    try:
        with custom_logger.step("Dataset Creation Run"):
            # TODO: Enter your desired config file path here. If you just want to recreate the results from the paper,
            # use the config files in the config folder to download the data belonging to the specified year.
            custom_logger.log(f"Loading config from {config_path}")
            with open(config_path, "r", encoding="utf8") as f:
                config = yaml.load(f, Loader=yaml.FullLoader)

            # TODO: Enter your gcloud key file path here.
            key_file = 'key/gcloud_key.json'

            # TODO: Enter your gcloud service account here.
            service_account = os.getenv("GCP_SERVICE_ACCOUNT")
            # service_account = 'your_service_account'
            viirs_af_path = os.getenv("VIIRS_AF_PATH")

            custom_logger.log(f"Using key file: {key_file}")
            custom_logger.log(f"Using service account: {service_account}")
            custom_logger.log(f"Using VIIRS AF asset path: {viirs_af_path}")

            with custom_logger.step("Earth Engine Initialization"):
                credentials = ee.ServiceAccountCredentials(service_account, key_file)
                ee.Initialize(credentials)
                asset_info = ee.data.getAsset(viirs_af_path)
                custom_logger.log(f"VIIRS AF asset accessible: {asset_info.get('name', viirs_af_path)}")

            # Number of days to extract additionally, before and after the fire dates given in GlobFire.
            # If we want to perform multi-temporal modeling, e.g. with five days of input data, based on which we want to
            # predict the fire occurrence on the sixth day, we need to add four days before the first fire occurrence.
            # This way, we can predict the fire spread right on the day after the fire first appears. Alternatively,
            # the preceding input data could of course be set to zero. However, in a real-world scenario, we would
            # *always* have preceding data, so we choose to model it this way here. Similarly, we want the last fire
            # date to be able to take every position in the input data, so we add four days after the last fire date,
            # to 'push out' the last fire date.
            # N_BUFFER_DAYS = 0

            non_fire_keys = [
                "output_bucket",
                "global_degree_bbox_size",
                "year",
                "export_crs",
                "export_resolution",
                "pre_buffer_days",
                "post_buffer_days"
            ]

            fire_names = list(config.keys())
            for non_fire_key in non_fire_keys: # ["output_bucket", "global_degree_bbox_size", "year", "export_crs", "export_resolution", "pre_buffer_days", "post_buffer_days"]:
                fire_names.remove(non_fire_key)
            locations = fire_names
            custom_logger.log(f"Total fire events to process: {len(locations)}")


            custom_logger.log("=======Config=============")
            for non_fire_key in non_fire_keys:
                if non_fire_key in config:
                    custom_logger.log(f"{non_fire_key}: {config[non_fire_key]}")
                
            for location in tqdm.tqdm(locations):
                with custom_logger.step(f"----------Event {location}-----------"):
                    dataset_pre = DatasetPrepareService(location=location, config=config, logger=custom_logger)
                    # custom_logger.log(f"Current Location: {location}")
                    try:
                        dataset_pre.extract_dataset_from_gee_to_gcloud()
                        # dataset_pre.extract_dataset_from_gee_to_gcloud('32610', n_buffer_days=N_BUFFER_DAYS)
                        # dataset_pre.extract_dataset_from_gee_to_gcloud('5070', n_buffer_days=N_BUFFER_DAYS)

                        # Uncomment to download data from gcloud to the local machine right away. Alternatively, you can use the
                        # gcloud command line tool to download the whole dataset at once after this script is done.
                        # dataset_pre.download_data_from_gcloud_to_local()
                        # custom_logger.log(f"Completed location successfully: {location}")
                    except Exception as e:
                        failed_locations.append(location)
                        custom_logger.log_exception(f"Failed location: {location}", e)
                        custom_logger.log(f"Failed locations so far: {failed_locations}")

            custom_logger.log(f"========= Run finished. ========= \n")
            custom_logger.log(f"Success count: {len(locations) - len(failed_locations)}")
            custom_logger.log(f"Failure count: {len(failed_locations)}")
            if failed_locations:
                custom_logger.log(f"Failed locations: {failed_locations}")
    except Exception as e:
        custom_logger.log_exception("Fatal error in main.py", e)
        raise
    finally:
        custom_logger.save(logger_output_path)
