import sys
import os
from osgeo import gdal, ogr
import subprocess
from datetime import datetime, timedelta
import glob

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterstats import zonal_stats


inpe_hourly_endpoint = "ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/HOURLY_NOW/"

project_folder = "/home/diego/apps/python-projects/inpe-merge/"

uf_sp_layer  = project_folder+"/layers/limite_estadual_sp/limiteestadualsp.shp"
cities_layer = project_folder+"/layers/municipios_sp/municipios_sp.shp"
ugrhis_layer = project_folder+"/layers/ugrhis_sp/ugrhis_sp.shp"

print("************************************************")
print("********| Executing Python Script |*************")
print("************************************************")

def resampling_merge_file(merge_file, output_file, target_resolution):
    #Open file with GDAL
    dataset = gdal.Open(merge_file, gdal.GA_ReadOnly)

    if not dataset:
        raise FileNotFoundError(f"input file '{merge_file}' not found.")
    
    # Get current resolution
    geo_transform = dataset.GetGeoTransform()
    pixel_width   =  geo_transform[1]
    pixel_height  = -geo_transform[5]

    # Setup new Resolution
    new_pixel_width = target_resolution  # 1 km em metros
    new_pixel_height = target_resolution  # 1 km em metros

    # Calculate new size of pixel and image
    width = dataset.RasterXSize
    height = dataset.RasterYSize
    new_width = int(width * (pixel_width / new_pixel_width))
    new_height = int(height * (pixel_height / new_pixel_height))

    #output_file = 'caminho/para/novo_arquivo.grib2'

    # Create driver to handle data
    driver = gdal.GetDriverByName('GRIB')

    # Setup settings to resampling
    options = [
        'OUTPUT_TYPE=Float32',   # Tipo de saída (pode variar conforme a necessidade)
        f'PIXEL_RES={new_pixel_width},{new_pixel_height}'  # Definindo a nova resolução
    ]

    # Resampling file
    gdal.Translate(
        output_file,
        dataset,
        width=new_width,
        height=new_height,
        resampleAlg='bilinear',  # resampling types ('nearest', 'bilinear', 'cubic', etc.)
        options=options
    )

    return output_file

def cut_tif_using_mask(file, mask, output_file):
    tif_file   = gdal.Open(file,gdal.GA_ReadOnly)
    mask_layer = ogr.Open(mask)

    layer = mask_layer.GetLayer()

    #Create a binary mask
    driver = gdal.GetDriverByName('MEM')
    mask_ds = driver.Create('',tif_file.RasterXSize, tif_file.RasterYSize, 1, gdal.GDT_Byte)
    mask_ds.SetProjection(tif_file.GetProjection())
    mask_ds.SetGeoTransform(tif_file.GetGeoTransform())
    mask_band = mask_ds.GetRasterBand(1)
    mask_band.Fill(0)

    #Raster to Mask
    gdal.RasterizeLayer(mask_ds, [1], layer, burn_values=[1])

    #Apply mask
    gdal.Warp(output_file, tif_file, cutlineDSName=mask, cropToCutline=True, dstNodata=0)

    print("File cutted using shapefile "+str(mask))

    # After cut remove file
    os.remove(file) 

    return output_file

def calculate_statistics(raster_path, shapfile_path, field_id='id', statistics='mean min max std', csv_output='output.csv'):
    """
        statistics: ['count', 'min', 'max', 'mean', 'sum', 'std', 'median', 'majority', 'minority', 'unique', 'range', 'nodata', 'nan']
    """
    with rasterio.open(raster_path) as src:
        raster_crs = src.crs
        raster_data = src.read(1)
        transform = src.transform
    
    gdf = gpd.read_file(shapfile_path)

    if gdf.crs != raster_crs:
        gdf = gdf.to_crs(raster_crs)

    stats = zonal_stats(gdf, raster_data, affine=transform, nodata=np.nan, stats=statistics)

    #gdf['stats'] = stats

    stats_vals = {}

    #for idx,row in gdf.iterrows():
    #    zone_id = row[field_id]
    #    stats_vals[zone_id] = row['stats']

    for stat in statistics.split(' '):
        gdf[stat] = [s[stat] for s in stats]
        #print(stat)

    gdf = gdf.drop(columns='geometry')
    print(f"Geodataframe: {gdf}")  

    #Saving statistics like csv file
    gdf.to_csv(csv_output, index=False)

    return stats_vals

def hourly_job():
    current_date = datetime.now()

    year  = current_date.strftime('%Y')
    month = current_date.strftime('%m')
    day   = current_date.strftime('%d')
    hour  = current_date.strftime('%H')
    mins  = current_date.strftime('%M')

    print("Executing Hourly Job => ", year,"-",month,"-",day," ",hour,":",mins)

    current_hourly_dir = project_folder + inpe_hourly_endpoint +str(year)+"/"+str(month)+"/"+str(day)+"/*"
    merge_files = glob.glob(current_hourly_dir)

    for merge_file in merge_files:
        if merge_file.endswith(".grib2"):
            filename   = os.path.splitext(os.path.basename(merge_file))[0]
            file_year  = filename[12:16]
            file_month = filename[16:18]
            file_day   = filename[18:20]
            file_hour  = filename[20:22]

            print("File => "+file_year+"-"+file_month+"-"+file_day+" "+file_hour)

            destiny_folder = project_folder + "/rainfalls/hourly/"+file_year+"-"+file_month+"-"+file_day
            date_time_id = file_year+"-"+file_month+"-"+file_day+"-"+file_hour

            if not os.path.exists(destiny_folder):
                os.makedirs(destiny_folder)
            
            # Resampling 10km to 2.5km
            merge_1km = resampling_merge_file(merge_file, destiny_folder+"/"+date_time_id+".tif", 0.025)

            # Cut tif file using shape
            merge_1km_cut = cut_tif_using_mask(merge_1km, uf_sp_layer, destiny_folder+"/uf_"+date_time_id+".tif")

            # Calculate statistics
            ugrhis_stats_vals = calculate_statistics(merge_1km_cut, ugrhis_layer, 'codigo', 'mean min max sum std median', destiny_folder+"/ugrhi_"+date_time_id+".csv")
            cities_stats_vals = calculate_statistics(merge_1km_cut, cities_layer, 'cd_mun', 'mean min max sum std median', destiny_folder+"/cities_"+date_time_id+".csv")

            for zone_id, stats in ugrhis_stats_vals.items():
                print(f'Ugrhi {zone_id} =>  Chuva Média: {stats['mean']}')
            
            for zone_id, stats in cities_stats_vals.items():
                print(f'City: {zone_id} => Chuva Média: {stats['mean']}')
            
hourly_job()