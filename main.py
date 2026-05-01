import ee
import yaml
import tqdm
import os
from dotenv import load_dotenv
load_dotenv()
# TODO: Update  self.viirs_af in DataPreparation/satellites/FirePred.py

from DataPreparation.DatasetPrepareService import DatasetPrepareService

if __name__ == '__main__':

    # TODO: Enter your desired config file path here. If you just want to recreate the results from the paper, 
    # use the config files in the config folder to download the data belonging to the specified year. 
    with open("config/us_fire_2016_test.yml", "r", encoding="utf8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    # TODO: Enter your gcloud key file path here.
    key_file = 'key/gcloud_key.json'

    # TODO: Enter your gcloud service account here.
    service_account = os.getenv("GCP_SERVICE_ACCOUNT")
    # service_account = 'your_service_account'
    credentials = ee.ServiceAccountCredentials(service_account, key_file)
    ee.Initialize(credentials)

    viirs_af_path= os.getenv("VIIRS_AF_PATH")
    print(ee.data.getAsset(viirs_af_path)) # to check the assets is accessible

    # Number of days to extract additionally, before and after the fire dates given in GlobFire. 
    # If we want to perform multi-temporal modeling, e.g. with five days of input data, based on which we want to
    # predict the fire occurrence on the sixth day, we need to add four days before the first fire occurrence. This way,
    # we can predict the fire spread right on the day after the fire first appears. Alternatively, the preceding input 
    # data could of course be set to zero. However, in a real-world scenario, we would *always* have preceding data,
    # so we choose to model it this way here. Similarly, we want the last fire date to be able to take every position
    # in the input data, so we add four days after the last fire date, to 'push out' the last fire date.
    # N_BUFFER_DAYS = 0

    # Extract fire names from config file.
    fire_names = list(config.keys())
    for non_fire_key in ["output_bucket", "global_degree_bbox_size", "year", "export_crs", "pre_buffer_days","post_buffer_days"]:
        fire_names.remove(non_fire_key)
    locations = fire_names

    # Keep track of any failures happening, to be able to manually re-run these later.
    # Shouldn't happen, but if it does, we get to know about it.
    failed_locations = []
    print("starting")

    # Tell Google Earth Engine to compute the images and add them to the specified google cloud bucket.
    for location in tqdm.tqdm(locations):
        dataset_pre = DatasetPrepareService(location=location, config=config)
        print("Current Location:" + location)

        # print(config, "config")
        try:
            dataset_pre.extract_dataset_from_gee_to_gcloud()
            # dataset_pre.extract_dataset_from_gee_to_gcloud('32610', n_buffer_days=N_BUFFER_DAYS)
            # dataset_pre.extract_dataset_from_gee_to_gcloud('5070', n_buffer_days=N_BUFFER_DAYS)

            # Uncomment to download data from gcloud to the local machine right away. Alternatively, you can use the
            # gcloud command line tool to download the whole dataset at once after this script is done. 
            # dataset_pre.download_data_from_gcloud_to_local()
        except Exception as e:
            print("Failed location: ", location)
            print("Error: ", str(e))
            failed_locations.append(location)
            print(f"Failed locations so far: {failed_locations}")
            
