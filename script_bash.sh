#!/bin/bash
conda activate base

current_date=$(date +"%Y-%m-%d")

echo "Executing: $current_date"

year=$(date +"%Y")
month=$(date +"%m")
day=$(date +"%d")

#wget -r -np -N -A '.grib2' 

url="https://ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/HOURLY_NOW/${year}/${month}/${day}/"

echo "Getting file from: $url"

wget -r -np -N -A '.grib2' "$url"

# After download files run Script to Handle files
/bin/bash -c "source /home/diego/miniconda3/etc/profile.d/conda.sh && conda activate base && python /home/diego/apps/python-projects/inpe-merge/script.py"