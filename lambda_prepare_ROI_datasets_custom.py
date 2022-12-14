import numpy as np
import numpy.ma as ma
import gdal
import os
import boto3
from botocore.exceptions import ClientError
import json
import requests
import logging

# import sys

s3 = boto3.client('s3')


  
def lambda_handler(event, context):
    
    body = json.loads(event['body'])
    json_file = body
        
    #get  input json and extract geojson
    try:
        project_id = json_file["project_id"]
        ROI = json_file["ROI"]
        if ROI==None:
            ROI = requests.get(json_file["ROI_file_url"])
            ROI = json.loads(ROI.text) #.replace("'",'"')
        
    except Exception as e:
        print("Input JSON field have an error.")
        return {
            "statusCode": 400,
            "body": e
        }
    
    
    #for local
    # path_to_tmp = "/home/christos/Desktop/SCiO_Projects/lup4ldn/data/cropped_files/"
    #for aws
    path_to_tmp = "/tmp/"
    
    # s3_file_path = '/vsis3/lup4ldn-dataset' + "/" + country_iso + "/"
    # s3_file_path = "https://lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com/"
    s3_file_path = '/vsis3/lup4ldn-default-global-datasets/'
    
    
    path_to_land_degradation = s3_file_path  + "global_land_degradation_map.tif"
    path_to_land_cover_folder = s3_file_path  + "global_land_cover_dataset/"
    path_to_land_use = s3_file_path + "global_land_use_map.tif"
    path_to_land_suitability = s3_file_path + "global_land_suitability_map.tif"
    path_to_fire_freq = s3_file_path + "global_fire_freq_map.tif"
    
    s3_lambda_path = "https://lup4ldn-prod.s3.us-east-2.amazonaws.com/"
    
    def create_vsis3_url(url):
        part1 = url.split(".s3.")[0]
        part2 = url.split(".amazonaws.com")[1]
        vsis3_url = (part1+part2).replace("https:/","/vsis3" )
        return vsis3_url
    
    def get_bucket_from_URL(url):
        part1 = url.split(".s3.")[0]
        part2 = part1.split("https://")[1]
        # vsis3_url = (part1+part2).replace("https:/","/vsis3" )
        return part2
    
    def get_object_from_URL(url):
        part2 = url.split(".amazonaws.com/")[1]
        # vsis3_url = (part1+part2).replace("https:/","/vsis3" )
        return part2
    
    def check_aws_s3_empty_file(url):
        metadata = s3.head_object(Bucket=get_bucket_from_URL(url),Key = get_object_from_URL(url))
        return int(metadata["ContentLength"])<=0

    ## land cover
    #read the first year
    save_land_cover_file = path_to_tmp + "cropped_land_cover.tif"
    
    gdal_warp_kwargs_target_area = {
        'format': 'GTiff',
        'cutlineDSName' : json.dumps(ROI),
        'cropToCutline' : True,
        'height' : None,
        'width' : None,
        'srcNodata' : -32768.0,
        'dstNodata' : -32768.0,
        'creationOptions' : ['COMPRESS=DEFLATE']
    }
    
    try:
        #CHANGE HERE THE YEAR IF MORE YEARS ARE TO BE USED
        gdal.Warp(save_land_cover_file,path_to_land_cover_folder + "global_land_cover_map_2020.tif" ,**gdal_warp_kwargs_target_area)
    except Exception as e:
        print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
        return {
            "statusCode": 400,
            "body": e
        }
        
    #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
    try:
        land_cover_tif = gdal.Open(save_land_cover_file)
        x_ref = land_cover_tif.RasterXSize
        y_ref = land_cover_tif.RasterYSize
        land_cover_array = land_cover_tif.ReadAsArray()
    except Exception as e:
        print("if ''NoneType' object has no attribute', probably the file path is wrong")
        return {
            "statusCode": 500,
            "body": e
        }
    
    land_cover_array = np.expand_dims(land_cover_array,axis=0)
    
    gdal_warp_kwargs_target_area["height"] = y_ref
    gdal_warp_kwargs_target_area["width"] = x_ref
    
    # # read and concatenate the rest years, IF we want older years as well
    # for i in range(2019,2021):
    #     try:
    #         gdal.Warp(save_land_cover_file,path_to_land_cover_folder + "global_land_cover_map_" + str(i) + ".tif" ,**gdal_warp_kwargs_target_area)
    #     except Exception as e:
    #         print(e)
    #         print(i)
    #         print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
    
    #     #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
    #     try:
    #         temp_array = gdal.Open(save_land_cover_file).ReadAsArray()
    #     except Exception as e:
    #         print(e)
    #         print("if ''NoneType' object has no attribute', probably the file path is wrong")
        
    #     temp_array = np.expand_dims(temp_array,axis=0)
    #     land_cover_array = np.concatenate((land_cover_array, temp_array), axis=0)
    

    ## map the 22-classes lc to the 7-classes lc
    
    # Functions
    def save_arrays_to_tif(output_tif_path, array_to_save, old_raster_used_for_projection):
        
    # output_tif_path : path to output file including its title in string format.
    # array_to_save : numpy array to be saved, 3d shape with the following format (no_bands, width, height). If only one band then should be extended with np.expand_dims to the format (1, width, height).
    # reference_tif : path to tif which will be used as reference for the geospatial information applied to the new tif.
        if len(array_to_save.shape)==2:
            array_to_save = np.expand_dims(array_to_save,axis=0)
    
        no_bands, width, height = array_to_save.shape
    
        gt = old_raster_used_for_projection.GetGeoTransform()
        wkt_projection = old_raster_used_for_projection.GetProjectionRef()
    
        driver = gdal.GetDriverByName("GTiff")
        DataSet = driver.Create(output_tif_path, height, width, no_bands, gdal.GDT_Int16,['COMPRESS=LZW']) #gdal.GDT_Int16
    
        DataSet.SetGeoTransform(gt)
        DataSet.SetProjection(wkt_projection)
    
        #no data value
        ndval = -32768
        for i, image in enumerate(array_to_save, 1):
            DataSet.GetRasterBand(i).WriteArray(image)
            DataSet.GetRasterBand(i).SetNoDataValue(ndval)
        DataSet = None
        # print(output_tif_path, " has been saved")
        return
    
    def map_land_cover_to_trendsearth_labels(array,labels_dict):
        for key in labels_dict:
            array = np.where(array==key,labels_dict[key],array)
            return array
    
    dict_labels_map_100m_to_trends = {
    10 : 3,
    11 : 3,
    12 : 3,
    20 : 3,
    30 : 3,
    40 : 2,
    50 : 1,
    60 : 1,
    61 : 1,
    62 : 1,
    70 : 1,
    71 : 1,
    72 : 1,
    80 : 1,
    81 : 1,
    82 : 1,
    90 : 1,
    100 : 1,
    110 : 2,
    120 : 2,
    121 : 2,
    122 : 2,
    130 : 2,
    140 : 2,
    150 : 2,
    151 : 2,
    152 : 2,
    153 : 2,
    160 : 4,
    170 : 4,
    180 : 4,
    190 : 5,
    200 : 6,
    201 : 6,
    202 : 6,
    210 : 7,
    220 : 6,
    0 : -32768
}
    
    land_cover_array = map_land_cover_to_trendsearth_labels(land_cover_array,dict_labels_map_100m_to_trends)
        
    save_arrays_to_tif(save_land_cover_file,land_cover_array,land_cover_tif)
    
    
    ##crop land degradation (SDG)
    if json_file["land_degradation_map"]["custom_map_url"]!="n/a":
        #check if file ends with .tif extension
        if not json_file["land_degradation_map"]["custom_map_url"].endswith(".tif"):
            return {
                "statusCode": 400,
                "body": "land_degradation url doesn't end with .tif extension"
            }
        #check if file is empty
        if check_aws_s3_empty_file(json_file["land_degradation_map"]["custom_map_url"]):
            return {
                "statusCode": 400,
                "body": "land_degradation url points to empty file"
            }
        path_to_land_degradation = create_vsis3_url(json_file["land_degradation_map"]["custom_map_url"])
    
    save_land_degradation_file = path_to_tmp + "cropped_land_degradation.tif"
    try:
        gdal.Warp(save_land_degradation_file,path_to_land_degradation,**gdal_warp_kwargs_target_area)
    except Exception as e:
        print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
        return {
            "statusCode": 400,
            "body": e
        }
            
    try:
        land_degradation_tif = gdal.Open(save_land_degradation_file)
        x_ref = land_degradation_tif.RasterXSize
        y_ref = land_degradation_tif.RasterYSize
        
        land_degradation_array = land_degradation_tif.ReadAsArray()
        ld_array = ma.array(land_degradation_array,mask=land_degradation_array==-32768,fill_value=-32768)
    except Exception as e:
        print("if ''NoneType' object has no attribute', probably the file path is wrong")
        return {
            "statusCode": 500,
            "body": e
        }
            
    unique, counts = np.unique(ld_array, return_counts=True)
    try:
        improved_pixels = counts[np.where(unique==1)]
        if improved_pixels.size == 0:
            improved_pixels = 0
    except Exception as e:
        print(e)
        print("Setting number of improved pixels to 0")
        improved_pixels = 0
      
    try:
        degraded_pixels = counts[np.where(unique==-1)]
        if degraded_pixels.size == 0:
            degraded_pixels = 0
    except Exception as e:
        print(e)
        print("Setting number of degraded pixels to 0")
        degraded_pixels = 0  

    initial_roi_ld = int(9*(improved_pixels - degraded_pixels))
    
    ## fire freq
    save_fire_freq_file = path_to_tmp + "cropped_fire_freq.tif"
    
    try:
        gdal.Warp(save_fire_freq_file,path_to_fire_freq,**gdal_warp_kwargs_target_area)
    except Exception as e:
        print(e)
        print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
        
    #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
    try:
        t = gdal.Open(save_fire_freq_file)
        data = t.ReadAsArray()
        uniques = np.unique(data)

        if np.isnan(uniques).all():
            fire_freq_URL = "n/a"
        else:
            fire_freq_URL = s3_lambda_path + project_id + "/cropped_fire_freq.tif"
        
    except Exception as e:
        print("if ''NoneType' object has no attribute', probably the file path is wrong")    
        raise(e)
    
    
    ## land use
    if json_file["land_use_map"]["custom_map_url"]!="n/a":
        #check if file ends with .tif extension
        if not json_file["land_use_map"]["custom_map_url"].endswith(".tif"):
            return {
                "statusCode": 400,
                "body": "land_use url doesn't end with .tif extension"
            }
        #check if file is empty
        if check_aws_s3_empty_file(json_file["land_use_map"]["custom_map_url"]):
            return {
                "statusCode": 400,
                "body": "land_use url points to empty file"
            }
        path_to_land_use = create_vsis3_url(json_file["land_use_map"]["custom_map_url"])
        
        custom_land_suitability = True
    else:
        custom_land_suitability = False
        
    save_land_use_file = path_to_tmp + "cropped_land_use.tif"
    
    try:
        gdal.Warp(save_land_use_file,path_to_land_use,**gdal_warp_kwargs_target_area)
    except Exception as e:
        print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
        return {
            "statusCode": 400,
            "body": e
        }
        
    #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
    try:
        land_use_tif = gdal.Open(save_land_use_file)
        
    except Exception as e:
        print("if ''NoneType' object has no attribute', probably the file path is wrong")
        return {
            "statusCode": 500,
            "body": e
        }
        
    

    
    if custom_land_suitability:
        land_use_array = land_use_tif.ReadAsArray()
        land_use_array = np.where(land_use_array<=0, -32768,land_use_array)
        unique, counts = np.unique(land_use_array, return_counts = True)
        if -32768 in unique:
            unique = unique[1:]
            counts = counts[1:]
    #     print(unique)
    #     print(counts)
    #     return {
    #     "statusCode": 700,
    #     "body": custom_land_suitability
    # }
    else:
        unique, counts = np.unique(land_cover_array, return_counts = True)
    
    lc_hectares = dict(zip([str(x) for x in unique],  [9*int(x) for x in counts]))
    
    
    ## land suitability
    if custom_land_suitability:
        save_suitability_file = path_to_tmp + "cropped_suitability.tif"
        land_suitability_array = np.zeros((y_ref,x_ref),dtype=np.int16())    
        try:
            lu_map = gdal.Open(save_land_use_file).ReadAsArray()
        except Exception as e:
            print("if ''NoneType' object has no attribute', probably the file path is wrong")
            return {
                "statusCode": 500,
                "body": e
            }
            
            
        for suit_map_data in json_file["land_suitability_map"]:
            lu_class = suit_map_data["lu_class"]
            
            #check if file ends with .tif extension
            if not suit_map_data["lu_suitability_map_url"].endswith(".tif"):
                return {
                    "statusCode": 400,
                    "body": "a suitability map urls doesn't end with .tif extension"
                }
            
            #check if file is empty
            if check_aws_s3_empty_file(suit_map_data["lu_suitability_map_url"]):
                return {
                    "statusCode": 400,
                    "body": "a suitability map url points to empty file"
                }
            
            path_to_land_suitability = create_vsis3_url(suit_map_data["lu_suitability_map_url"])
            save_suitability_file = path_to_tmp + "cropped_suitability.tif"
            
            try:
                gdal.Warp(save_suitability_file,path_to_land_suitability,**gdal_warp_kwargs_target_area)
            except Exception as e:
                print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
                return {
                    "statusCode": 400,
                    "body": e
                }
                
            #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
            try:
                lu_class_suitability_map = gdal.Open(save_suitability_file).ReadAsArray()
            except Exception as e:
                print("if ''NoneType' object has no attribute', probably the file path is wrong")      
                return {
                    "statusCode": 500,
                    "body": e
                }
                
            land_suitability_array += np.where(lu_map==lu_class,lu_class_suitability_map,0)    
            
        land_suitability_array = np.where(land_suitability_array==0,-32768,land_suitability_array)
        save_arrays_to_tif(save_suitability_file,land_suitability_array,land_cover_tif)
     
    else:        
        save_suitability_file = path_to_tmp + "cropped_suitability.tif"
        
        try:
            gdal.Warp(save_suitability_file,path_to_land_suitability,**gdal_warp_kwargs_target_area)
        except Exception as e:
            print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
            return {
                "statusCode": 400,
                "body": e
            }
            
        #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
        try:
            land_suitability_tif = gdal.Open(save_suitability_file)
            land_suitability_array = land_suitability_tif.ReadAsArray()
        except Exception as e:
            print("if ''NoneType' object has no attribute', probably the file path is wrong")
            return {
                "statusCode": 500,
                "body": e
            }
    

    # future land degradation map
    
    
    #!!!!!!!!!!!WATCH OUT FOR NEGATIVE OVERFLOW IF -1 FROM LAND DEGRADATION IS ADDED TO -32768 NO DATA OF SUITABILITY!!!!!!!!!!!!
    future_ld_map = 10*land_suitability_array + land_degradation_array
    
    future_ld_map = np.where(future_ld_map<-1,-32768,future_ld_map )

    future_ld_map = np.where(future_ld_map==-1,5,future_ld_map )
    
    future_ld_map = np.where(future_ld_map==0,2,future_ld_map )
    
    future_ld_map = np.where(future_ld_map==1,1,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==10,future_ld_map==11),1,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==20,future_ld_map==21),2,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==30,future_ld_map==31),3,future_ld_map )

    future_ld_map = np.where(future_ld_map==9,4,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==19,future_ld_map==29),5,future_ld_map)
    
    save_future_ld_map_file = path_to_tmp + "cropped_future_ld.tif"
    
    save_arrays_to_tif(save_future_ld_map_file,future_ld_map,land_cover_tif)
            
        
    #upload files
    file_to_upload = os.listdir(path_to_tmp)
    
    
    for file in file_to_upload:
        path_to_file_for_upload = path_to_tmp + file
        target_bucket = "lup4ldn-prod"
    
        object_name = project_id +  "/" + file
        
        # Upload the file
        try:
            response = s3.upload_file(path_to_file_for_upload, target_bucket, object_name)
    #         print("Uploaded file: " + file)
        except ClientError as e:
            logging.error(e)
            return {
                "statusCode": 500,
                "body": e
            }
    
    my_output = {
        "land_cover" : s3_lambda_path + project_id + "/cropped_land_cover.tif",
        "land_use" : s3_lambda_path + project_id + "/cropped_land_use.tif",
        "land_degradation" : s3_lambda_path + project_id + "/cropped_land_degradation.tif",
        "suitability" : s3_lambda_path + project_id + "/cropped_suitability.tif",
        "future_ld" : s3_lambda_path + project_id + "/cropped_future_ld.tif",
        "fire_freq" : fire_freq_URL,
        "land_cover_hectares_per_class" : lc_hectares,
        "initial_roi_ld" : initial_roi_ld
    }

    return {
        "statusCode": 200,
        "body": json.dumps(my_output)
    }
