import numpy as np
import numpy.ma as ma
import gdal
import os
import boto3
from botocore.exceptions import ClientError
import json
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
    except Exception as e:
        print(e)
        print("Input JSON field have an error.")
    
    
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
    
    def create_vsis3_url(url):
        part1 = url.split(".s3.")[0]
        part2 = url.split(".amazonaws.com")[1]
        vsis3_url = (part1+part2).replace("https:/","/vsis3" )
        return vsis3_url
    
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
        print(e)
        print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
        
    #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
    try:
        land_cover_tif = gdal.Open(save_land_cover_file)
        x_ref = land_cover_tif.RasterXSize
        y_ref = land_cover_tif.RasterYSize
        land_cover_array = land_cover_tif.ReadAsArray()
    except Exception as e:
        print(e)
        print("if ''NoneType' object has no attribute', probably the file path is wrong")
    
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
        path_to_land_degradation = create_vsis3_url(json_file["land_degradation_map"]["custom_map_url"])
    
    save_land_degradation_file = path_to_tmp + "cropped_land_degradation.tif"
    try:
        gdal.Warp(save_land_degradation_file,path_to_land_degradation,**gdal_warp_kwargs_target_area)
    except Exception as e:
        print(e)
        print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
            
    try:
        land_degradation_tif = gdal.Open(save_land_degradation_file)
        land_degradation_array = land_degradation_tif.ReadAsArray()
        x_ref = land_degradation_tif.RasterXSize
        y_ref = land_degradation_tif.RasterYSize
    except Exception as e:
        print(e)
        print("if ''NoneType' object has no attribute', probably the file path is wrong")
            
    
    
    ## land use
    if json_file["land_use_map"]["custom_map_url"]!="n/a":
        path_to_land_degradation = create_vsis3_url(json_file["land_use_map"]["custom_map_url"])
        
        custom_land_suitability = True
    else:
        custom_land_suitability = False
        
    save_land_use_file = path_to_tmp + "cropped_land_use.tif"
    
    try:
        gdal.Warp(save_land_use_file,path_to_land_use,**gdal_warp_kwargs_target_area)
    except Exception as e:
        print(e)
        print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
        
    #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
    try:
        t = gdal.Open(save_land_use_file)
        
    except Exception as e:
        print(e)
        print("if ''NoneType' object has no attribute', probably the file path is wrong")
    
    if custom_land_suitability:
        land_use_array = t.ReadAsArray()
        land_use_array = np.where(land_use_array<=0, -32768,land_use_array)
        unique, counts = np.unique(land_use_array, return_counts = True)
        if -32768 in unique:
            unique = unique[1:]
            counts = counts[1:]
    else:
        unique, counts = np.unique(land_cover_array, return_counts = True)
    
    lc_hectares = dict(zip([str(x) for x in unique], 9 * [int(x) for x in counts]))
    
    
    ## land suitability
    if custom_land_suitability:
        save_suitability_file = path_to_tmp + "cropped_suitability.tif"
        land_suitability_array = np.zeros((y_ref,x_ref),dtype=np.int16())    
        try:
            lu_map = gdal.Open(save_land_use_file).ReadAsArray()
        except Exception as e:
            print(e)
            print("if ''NoneType' object has no attribute', probably the file path is wrong")
            
            
        for suit_map_data in json_file["land_suitability_map"]:
            lu_class = suit_map_data["lu_class"]
            path_to_land_suitability = create_vsis3_url(suit_map_data["lu_suitability_map_url"])
            save_suitability_file = path_to_tmp + "cropped_suitability.tif"
            
            try:
                gdal.Warp(save_suitability_file,path_to_land_suitability,**gdal_warp_kwargs_target_area)
            except Exception as e:
                print(e)
                print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
                
            #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
            try:
                lu_class_suitability_map = gdal.Open(save_suitability_file).ReadAsArray()
            except Exception as e:
                print(e)
                print("if ''NoneType' object has no attribute', probably the file path is wrong")      
                
            land_suitability_array += np.where(lu_map==lu_class,lu_class_suitability_map,0)    
            
        land_suitability_array = np.where(land_suitability_array==0,-32768,land_suitability_array)
        save_arrays_to_tif(save_suitability_file,land_suitability_array,land_cover_tif)
     
    else:        
        save_suitability_file = path_to_tmp + "cropped_suitability.tif"
        
        try:
            gdal.Warp(save_suitability_file,path_to_land_suitability,**gdal_warp_kwargs_target_area)
        except Exception as e:
            print(e)
            print("if 'returned NULL without setting an error', probably at least one of the file paths is wrong")
            
        #must use gdal.Open in order to fill the file created from gdal.Warp, else the file remaines full of nodata
        try:
            land_suitability_tif = gdal.Open(save_suitability_file)
            land_suitability_array = land_suitability_tif.ReadAsArray()
        except Exception as e:
            print(e)
            print("if ''NoneType' object has no attribute', probably the file path is wrong")
    

    # future land degradation map
    
    
    future_ld_map = 10*land_suitability_array + land_degradation_array
    future_ld_map = np.where(future_ld_map<9,-32768,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==10,future_ld_map==11),1,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==20,future_ld_map==21),2,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==30,future_ld_map==31),3,future_ld_map )

    future_ld_map = np.where(future_ld_map==9,4,future_ld_map )

    future_ld_map = np.where(np.logical_or(future_ld_map==19,future_ld_map==29),5,future_ld_map)
    
    save_future_ld_map_file = path_to_tmp + "cropped_future_ld.tif"
    
    save_arrays_to_tif(save_future_ld_map_file,future_ld_map,land_cover_tif)
            
        
    #upload files
    file_to_upload = os.listdir(path_to_tmp)
    
    s3_lambda_path = "https://lup4ldn-lambdas.s3.eu-central-1.amazonaws.com/"    
    
    for file in file_to_upload:
        path_to_file_for_upload = path_to_tmp + file
        target_bucket = "lup4ldn-lambdas"
    
        object_name = project_id +  "/" + file
        
        # Upload the file
        try:
            response = s3.upload_file(path_to_file_for_upload, target_bucket, object_name)
    #         print("Uploaded file: " + file)
        except ClientError as e:
            logging.error(e)
    
    my_output = {
        "land_cover" : s3_lambda_path + project_id + "/cropped_land_cover.tif",
        "land_use" : s3_lambda_path + project_id + "/cropped_land_use.tif",
        "land_degradation" : s3_lambda_path + project_id + "/cropped_land_degradation.tif",
        "suitability" : s3_lambda_path + project_id + "/cropped_suitability.tif",
        "future_ld" : s3_lambda_path + project_id + "/cropped_future_ld.tif",
        "land_cover_hectares_per_class" : lc_hectares
    }

    return {
        "statusCode": 200,
        "body": json.dumps(my_output)
    }

#%%

# json_file = {
#     "body": "{\"project_id\":\"some_projectID_custom\",\"land_degradation_map\":{\"custom_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_degradation_map.tif\"},\"land_use_map\":{\"custom_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_use_map.tif\"},\"land_suitability_map\":[{\"lu_class\":21,\"lu_suitability_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_suitability_map_1.tif\"},{\"lu_class\":34,\"lu_suitability_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_suitability_map_2.tif\"}],\"ROI\":{\"type\":\"FeatureCollection\",\"features\":[{\"type\":\"Feature\",\"properties\":{},\"geometry\":{\"type\":\"Polygon\",\"coordinates\":[[[8.72314453125,33.04550781490999],[10.052490234375,33.04550781490999],[10.052490234375,37.17782559332976],[8.72314453125,37.17782559332976],[8.72314453125,33.04550781490999]]]}}]}}"
# }

# t = lambda_handler(json_file, 1)


# {
#      "body": "{\"project_id\":\"some_projectID_custom\",\"land_degradation_map\":{\"custom_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_degradation_map.tif\"},\"land_use_map\":{\"custom_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_use_map.tif\"},\"land_suitability_map\":[{\"lu_class\":21,\"lu_suitability_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_suitability_map_1.tif\"},{\"lu_class\":34,\"lu_suitability_map_url\":\"https:\/\/lup4ldn-default-global-datasets.s3.eu-central-1.amazonaws.com\/lup4ldn_custom_inputs\/custom_land_suitability_map_2.tif\"}],\"ROI\":{\"type\":\"FeatureCollection\",\"features\":[{\"type\":\"Feature\",\"properties\":{},\"geometry\":{\"type\":\"Polygon\",\"coordinates\":[[[8.72314453125,33.04550781490999],[10.052490234375,33.04550781490999],[10.052490234375,37.17782559332976],[8.72314453125,37.17782559332976],[8.72314453125,33.04550781490999]]]}}]}}"
# }


